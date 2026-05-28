"""File management module for SnowDrive."""

import os, io, re, shutil, zipfile, tempfile, mimetypes, threading
from datetime import datetime

from flask import Blueprint, request, jsonify, render_template, send_file, g
from app.config import Config
from app.utils import (
    login_required, login_required_page, safe_join_path,
    get_file_info, get_file_icon_class, format_file_size, hash_token,
)
from app.models import (
    create_download_task, get_download_tasks, get_download_task,
    update_download_progress, complete_download, delete_download_task,
    get_user_2fa_methods, require_totp_reset,
)
from app.utils import start_background_download, stop_background_download

files_bp = Blueprint("files", __name__)


# ─── Page Route ────────────────────────────────────────────────────

@files_bp.route("/files")
@login_required_page
def file_manager():
    user = g.current_user
    # Force 2FA setup if no methods exist
    if not user.get("totp_required_reset") and len(get_user_2fa_methods(user["id"])) == 0:
        require_totp_reset(user["id"])
        from flask import redirect, url_for
        return redirect(url_for("auth.reset_2fa_page"))
    return render_template("index.html", username=user["username"], has_avatar=bool(user.get("avatar_path")))


# ─── File Listing ──────────────────────────────────────────────────

@files_bp.route("/api/files/list", methods=["GET"])
@login_required
def list_files():
    subpath = request.args.get("path", "").strip()
    sort_by = request.args.get("sort", "name")
    sort_order = request.args.get("order", "asc")
    search = request.args.get("search", "").strip()
    if subpath:
        full_path = safe_join_path(Config.DATA_DIR, subpath)
        if full_path is None: return jsonify({"error": "Invalid path."}), 400
    else:
        full_path = Config.DATA_DIR

    if not os.path.exists(full_path):
        return jsonify({"error": f"Directory not found: {full_path}"}), 404
    if not os.path.isdir(full_path):
        return jsonify({"error": f"Not a directory: {full_path}"}), 400

    parent = os.path.dirname(subpath) if subpath else None
    if parent == ".": parent = ""

    breadcrumbs = []
    if subpath:
        parts = subpath.replace("\\", "/").strip("/").split("/")
        accumulated = ""
        breadcrumbs.append({"name": "/", "path": ""})
        for part in parts:
            if not part: continue
            accumulated = os.path.join(accumulated, part).replace("\\", "/")
            breadcrumbs.append({"name": part, "path": accumulated})
    else:
        breadcrumbs.append({"name": "/", "path": ""})

    try:
        items = os.listdir(full_path)
    except PermissionError:
        return jsonify({"error": "Permission denied."}), 403
    except Exception as e:
        return jsonify({"error": f"Failed to list directory: {str(e)}"}), 500

    file_list = []
    for item_name in items:
        if search and search.lower() not in item_name.lower(): continue
        item_path = os.path.join(full_path, item_name)
        try:
            info = get_file_info(item_path, Config.DATA_DIR)
            info["icon"] = get_file_icon_class(item_name, info["is_dir"], info["extension"])
            file_list.append(info)
        except (OSError, PermissionError): continue

    reverse = sort_order.lower() == "desc"
    if sort_by == "name":
        file_list.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)
    elif sort_by == "size":
        file_list.sort(key=lambda x: (not x["is_dir"], x["size"]), reverse=reverse)
    elif sort_by == "modified":
        file_list.sort(key=lambda x: (not x["is_dir"], x["modified"]), reverse=reverse)
    elif sort_by == "type":
        file_list.sort(key=lambda x: (not x["is_dir"], x["extension"].lower()), reverse=reverse)
    else:
        file_list.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    return jsonify({
        "path": subpath, "parent": parent, "breadcrumbs": breadcrumbs,
        "files": file_list,
        "dir_count": sum(1 for f in file_list if f["is_dir"]),
        "file_count": sum(1 for f in file_list if not f["is_dir"]),
        "sort": sort_by, "order": sort_order,
    })


# ─── Directory Operations ─────────────────────────────────────────

@files_bp.route("/api/files/mkdir", methods=["POST"])
@login_required
def create_directory():
    data = request.get_json() or {}
    subpath = data.get("path", "").strip()
    dirname = (data.get("name") or "").strip()
    if not dirname: return jsonify({"error": "Directory name required."}), 400
    if re.search(r'[<>:"/\\|?*]', dirname): return jsonify({"error": "Invalid characters."}), 400
    base_path = Config.DATA_DIR
    if subpath:
        base_path = safe_join_path(Config.DATA_DIR, subpath)
        if base_path is None: return jsonify({"error": "Invalid path."}), 400
    new_dir = os.path.join(base_path, dirname)
    if os.path.exists(new_dir): return jsonify({"error": "Already exists."}), 409
    try:
        os.makedirs(new_dir, exist_ok=False)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route("/api/files/create-file", methods=["POST"])
@login_required
def create_file():
    data = request.get_json() or {}
    subpath = data.get("path", "").strip()
    filename = (data.get("name") or "").strip()
    content = data.get("content", "")
    if not filename: return jsonify({"error": "File name required."}), 400
    if re.search(r'[<>:"/\\|?*]', filename): return jsonify({"error": "Invalid characters."}), 400
    base_path = Config.DATA_DIR
    if subpath:
        base_path = safe_join_path(Config.DATA_DIR, subpath)
        if base_path is None: return jsonify({"error": "Invalid path."}), 400
    new_file = os.path.join(base_path, filename)
    if os.path.exists(new_file): return jsonify({"error": "Already exists."}), 409
    try:
        with open(new_file, "w", encoding="utf-8") as f: f.write(content)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


# ─── Delete / Rename / Move ───────────────────────────────────────

@files_bp.route("/api/files/delete", methods=["POST"])
@login_required
def delete_item():
    data = request.get_json() or {}
    subpath = data.get("path", "").strip()
    if not subpath: return jsonify({"error": "Path required."}), 400
    full_path = safe_join_path(Config.DATA_DIR, subpath)
    if full_path is None or not os.path.exists(full_path): return jsonify({"error": "Not found."}), 404
    if os.path.normpath(full_path) == os.path.normpath(Config.DATA_DIR): return jsonify({"error": "Cannot delete root."}), 400
    try:
        if os.path.isdir(full_path): shutil.rmtree(full_path)
        else: os.remove(full_path)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route("/api/files/rename", methods=["POST"])
@login_required
def rename_item():
    data = request.get_json() or {}
    subpath = data.get("path", "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not subpath or not new_name: return jsonify({"error": "Path and new name required."}), 400
    if re.search(r'[<>:"/\\|?*]', new_name): return jsonify({"error": "Invalid characters."}), 400
    full_path = safe_join_path(Config.DATA_DIR, subpath)
    if full_path is None or not os.path.exists(full_path): return jsonify({"error": "Not found."}), 404
    parent_dir = os.path.dirname(full_path)
    new_path = os.path.join(parent_dir, new_name)
    if os.path.exists(new_path): return jsonify({"error": "Already exists."}), 409
    try:
        os.rename(full_path, new_path)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


# ─── Download (GET single / POST zip) ──────────────────────────────

@files_bp.route("/api/files/download", methods=["GET", "POST"])
@login_required
def download_items():
    """GET: download single file directly. POST: download selected files as ZIP."""
    # GET - single file direct download
    if request.method == "GET":
        subpath = request.args.get("path", "").strip()
        if not subpath:
            return jsonify({"error": "Path is required."}), 400
        full_path = safe_join_path(Config.DATA_DIR, subpath)
        if full_path is None or not os.path.exists(full_path):
            return jsonify({"error": "File not found."}), 404
        if os.path.isdir(full_path):
            return jsonify({"error": "Cannot download a directory. Use POST for ZIP."}), 400
        return send_file(
            full_path, as_attachment=True,
            download_name=os.path.basename(full_path),
            mimetype=mimetypes.guess_type(full_path)[0] or "application/octet-stream",
        )

    # POST - ZIP download for selected files
    data = request.get_json() or {}
    paths = data.get("paths", [])
    zip_name = data.get("zip_name", "download.zip")
    if not paths: return jsonify({"error": "No files selected."}), 400

    full_paths = []
    for p in paths:
        full = safe_join_path(Config.DATA_DIR, p.strip())
        if full is None or not os.path.exists(full): return jsonify({"error": f"Not found: {p}"}), 404
        full_paths.append(full)

    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(temp_fd)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full_path in full_paths:
                base_name = os.path.basename(full_path)
                if os.path.isdir(full_path):
                    for root, dirs, files in os.walk(full_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.join(base_name, os.path.relpath(file_path, full_path))
                            zf.write(file_path, arcname)
                else:
                    zf.write(full_path, base_name)
        return send_file(temp_path, as_attachment=True, download_name=zip_name, mimetype="application/zip")
    except Exception as e:
        if os.path.exists(temp_path): os.unlink(temp_path)
        return jsonify({"error": str(e)}), 500


# ─── Upload ───────────────────────────────────────────────────────

@files_bp.route("/api/files/upload", methods=["POST"])
@login_required
def upload_file():
    subpath = request.form.get("path", "").strip()
    base_path = Config.DATA_DIR
    if subpath:
        base_path = safe_join_path(Config.DATA_DIR, subpath)
        if base_path is None: return jsonify({"error": "Invalid path."}), 400
    if "files" not in request.files: return jsonify({"error": "No files."}), 400
    uploaded_files = request.files.getlist("files")
    if not uploaded_files: return jsonify({"error": "No files."}), 400
    results, errors = [], []
    for file in uploaded_files:
        if not file.filename: continue
        filename = re.sub(r'[<>:"/\\|?*]', "_", os.path.basename(file.filename))
        dest_path = os.path.join(base_path, filename)
        if os.path.exists(dest_path):
            name, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(base_path, f"{name} ({counter}){ext}")): counter += 1
            filename = f"{name} ({counter}){ext}"
            dest_path = os.path.join(base_path, filename)
        try:
            file.save(dest_path)
            results.append(filename)
        except OSError as e:
            errors.append(f"{file.filename}: {str(e)}")
    return jsonify({"success": len(errors) == 0, "uploaded": results, "errors": errors,
                    "message": f"Uploaded {len(results)} file(s)." + (f" {len(errors)} failed." if errors else "")})


# ─── Remote Download (Background) ─────────────────────────────────

@files_bp.route("/api/files/remote-download", methods=["POST"])
@login_required
def remote_download():
    """Start a background remote download."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    subpath = data.get("path", "").strip()
    custom_filename = (data.get("filename") or "").strip()
    if not url: return jsonify({"error": "URL required."}), 400
    if not url.startswith(("http://", "https://")): return jsonify({"error": "Invalid URL."}), 400

    base_path = Config.DATA_DIR
    if subpath:
        base_path = safe_join_path(Config.DATA_DIR, subpath)
        if base_path is None: return jsonify({"error": "Invalid path."}), 400

    # Determine filename
    if custom_filename:
        filename = custom_filename
    else:
        filename = os.path.basename(url.split("?")[0]) or "downloaded_file"
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

    dest_path = os.path.join(base_path, filename)
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(base_path, f"{name} ({counter}){ext}")): counter += 1
        filename = f"{name} ({counter}){ext}"
        dest_path = os.path.join(base_path, filename)

    user = g.current_user
    task_id = create_download_task(user["id"], url, dest_path, filename)
    start_background_download(task_id, url, dest_path, user["id"])

    return jsonify({"success": True, "task_id": task_id, "filename": filename, "message": f"Download started: {filename}"})


@files_bp.route("/api/files/download-tasks", methods=["GET"])
@login_required
def list_download_tasks():
    tasks = get_download_tasks(g.current_user["id"])
    return jsonify({"tasks": [dict(t) for t in tasks]})


@files_bp.route("/api/files/download-task/<int:task_id>", methods=["GET"])
@login_required
def get_download_task_status(task_id):
    task = get_download_task(task_id)
    if not task or task["user_id"] != g.current_user["id"]:
        return jsonify({"error": "Not found."}), 404
    return jsonify(dict(task))


@files_bp.route("/api/files/download-task/<int:task_id>", methods=["DELETE"])
@login_required
def remove_download_task(task_id):
    task = get_download_task(task_id)
    if not task or task["user_id"] != g.current_user["id"]:
        return jsonify({"error": "Not found."}), 404
    # Stop any running background worker and remove partial file
    try:
        stop_background_download(task_id)
    except Exception:
        pass
    delete_download_task(task_id)
    return jsonify({"success": True})


# ─── Directory Status ─────────────────────────────────────────────

@files_bp.route("/api/files/dirstat", methods=["GET"])
@login_required
def directory_status():
    try:
        stat = os.stat(Config.DATA_DIR)
        total_files, total_dirs, total_size = 0, 0, 0
        for root, dirs, files in os.walk(Config.DATA_DIR):
            total_dirs += len(dirs)
            total_files += len(files)
            for f in files:
                try: total_size += os.path.getsize(os.path.join(root, f))
                except OSError: pass
        return jsonify({
            "path": Config.DATA_DIR, "owner": str(stat.st_uid),
            "permissions": oct(stat.st_mode)[-3:],
            "total_files": total_files, "total_dirs": total_dirs,
            "total_size": total_size, "total_size_display": format_file_size(total_size),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Debug Endpoint ──────────────────────────────────────────────

@files_bp.route("/api/files/debug", methods=["GET"])
def debug_info():
    # Debug endpoint disabled in production builds - return 404
    return jsonify({"error": "Not found."}), 404
