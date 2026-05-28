"""File management module for SnowDrive - DEMO MODE (Cookie-based Virtual Filesystem).
All file operations are stored in cookies, not on the filesystem.
"""

import os, io, json, base64, zipfile, tempfile, mimetypes
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, render_template, send_file, g, make_response
from app.config import Config
from app.utils import (
    login_required, login_required_page, format_file_size, get_file_icon_class, get_file_type_description,
)

files_bp = Blueprint("files", __name__)

# ─── Demo File List ──────────────────────────────────────────────────

DEMO_FILES = [
    {"name": "C++.cpp", "is_dir": False, "path": "C++.cpp", "extension": ".cpp", "file_type": "C++ Source", "size": 0},
    {"name": "Excel.xlsx", "is_dir": False, "path": "Excel.xlsx", "extension": ".xlsx", "file_type": "Excel Spreadsheet", "size": 0},
    {"name": "Folder", "is_dir": True, "path": "Folder", "extension": "", "file_type": "folder", "size": 0,
     "children": [
         {"name": "CSS.css", "is_dir": False, "path": "Folder/CSS.css", "extension": ".css", "file_type": "CSS", "size": 0},
         {"name": "HTML.html", "is_dir": False, "path": "Folder/HTML.html", "extension": ".html", "file_type": "HTML", "size": 0},
         {"name": "JavaScript.js", "is_dir": False, "path": "Folder/JavaScript.js", "extension": ".js", "file_type": "JavaScript", "size": 0},
     ]},
    {"name": "MacInstaller.pkg", "is_dir": False, "path": "MacInstaller.pkg", "extension": ".pkg", "file_type": "Installer Package", "size": 0},
    {"name": "MarkDown.md", "is_dir": False, "path": "MarkDown.md", "extension": ".md", "file_type": "Markdown", "size": 0},
    {"name": "PowerPoint.pptx", "is_dir": False, "path": "PowerPoint.pptx", "extension": ".pptx", "file_type": "PowerPoint", "size": 0},
    {"name": "Python.py", "is_dir": False, "path": "Python.py", "extension": ".py", "file_type": "Python Script", "size": 0},
    {"name": "Text.txt", "is_dir": False, "path": "Text.txt", "extension": ".txt", "file_type": "Text Document", "size": 0},
    {"name": "WinInstaller.msi", "is_dir": False, "path": "WinInstaller.msi", "extension": ".msi", "file_type": "Installer", "size": 0},
    {"name": "Windows.exe", "is_dir": False, "path": "Windows.exe", "extension": ".exe", "file_type": "Executable", "size": 0},
    {"name": "Word.docx", "is_dir": False, "path": "Word.docx", "extension": ".docx", "file_type": "Word Document", "size": 0},
    {"name": "macOS.app", "is_dir": False, "path": "macOS.app", "extension": ".app", "file_type": "Application", "size": 0},
]


def get_all_demo_files():
    """Flatten the demo file tree into a list."""
    result = []
    for item in DEMO_FILES:
        children = item.pop("children", None) if isinstance(item.get("children"), list) else None
        entry = {k: v for k, v in item.items() if k != "children"}
        result.append(entry)
        if children:
            for child in children:
                result.append(child)
        if children is not None:
            item["children"] = children  # restore
    return result


# ─── Cookie Helpers ──────────────────────────────────────────────────

def get_virtual_state():
    """Get virtual file state from cookie. Returns dict with 'deleted' list and 'renamed' map."""
    cookie = request.cookies.get("snowdrive_vfs")
    if not cookie:
        return {"deleted": [], "renamed": {}}
    try:
        return json.loads(base64.b64decode(cookie))
    except Exception:
        return {"deleted": [], "renamed": {}}


def save_virtual_state(state, response):
    """Save virtual file state to cookie."""
    try:
        data = base64.b64encode(json.dumps(state).encode()).decode()
        response.set_cookie("snowdrive_vfs", data, max_age=30*24*3600, httponly=True, samesite="Lax")
    except Exception:
        pass


def apply_virtual_state(file_list, state):
    """Apply virtual state (deleted, renamed) to a file list. Returns modified list."""
    deleted_set = set(state.get("deleted", []))
    renamed_map = state.get("renamed", {})

    result = []
    for f in file_list:
        path = f["path"]

        # Check if renamed
        if path in renamed_map:
            new_path = renamed_map[path]
            f = dict(f)
            f["path"] = new_path
            f["name"] = new_path.split("/")[-1]
            path = new_path

        # Check if deleted
        if path in deleted_set:
            continue

        # Also skip if any parent was deleted
        parts = path.split("/")
        skip = False
        for i in range(1, len(parts)):
            parent_path = "/".join(parts[:i])
            if parent_path in deleted_set:
                skip = True
                break
            # Check renamed parent
            if parent_path in renamed_map:
                pass  # renamed parent is fine
        if skip:
            continue

        result.append(f)

    return result


def make_vfs_response(data, status=200):
    """Make a JSON response that can carry VFS cookie updates."""
    resp = make_response(jsonify(data), status)
    # Re-read state from request cookies (unchanged for GET)
    return resp


# ─── Page Route ────────────────────────────────────────────────────

@files_bp.route("/files")
@login_required_page
def file_manager():
    return render_template("index.html", username="DemoUser", has_avatar=False)


# ─── File Listing ──────────────────────────────────────────────────

@files_bp.route("/api/files/list", methods=["GET"])
@login_required
def list_files():
    """List files from virtual demo filesystem, with cookie-based modifications applied."""
    subpath = request.args.get("path", "").strip()
    sort_by = request.args.get("sort", "name")
    sort_order = request.args.get("order", "asc")
    search = request.args.get("search", "").strip()

    state = get_virtual_state()
    all_files = get_all_demo_files()
    all_files = apply_virtual_state(all_files, state)

    # Filter by path
    if subpath:
        prefix = subpath.rstrip("/") + "/"
        file_list = [f for f in all_files if f["path"].startswith(prefix)]
    else:
        file_list = [f for f in all_files if "/" not in f["path"]]

    # Add Folder children manually (from DEMO_FILES tree)
    if not subpath:
        for item in DEMO_FILES:
            if item.get("children") and item["name"] not in state.get("deleted", []):
                # Folder already in file_list
                pass

    # Apply search filter
    if search:
        file_list = [f for f in file_list if search.lower() in f["name"].lower()]

    # Add display fields
    now = datetime.now(timezone.utc)
    now_display = now.strftime("%Y-%m-%d %H:%M")
    for f in file_list:
        f["icon"] = get_file_icon_class(f["name"], f["is_dir"], f.get("extension", ""))
        f["size_display"] = "—" if f["is_dir"] else "0 B"
        f["modified"] = now.isoformat()
        f["modified_display"] = now_display
        f["permissions"] = "644"
        f["owner"] = "demo"

    # Build breadcrumbs
    breadcrumbs = [{"name": "/", "path": ""}]
    if subpath:
        parts = subpath.strip("/").split("/")
        accumulated = ""
        for part in parts:
            accumulated = (accumulated + "/" + part).strip("/")
            breadcrumbs.append({"name": part, "path": accumulated})

    # Sort
    reverse = sort_order.lower() == "desc"
    if sort_by == "name":
        file_list.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)
    elif sort_by == "size":
        file_list.sort(key=lambda x: (not x["is_dir"], x.get("size", 0)), reverse=reverse)
    elif sort_by == "modified":
        file_list.sort(key=lambda x: (not x["is_dir"], x.get("modified", "")), reverse=reverse)
    elif sort_by == "type":
        file_list.sort(key=lambda x: (not x["is_dir"], x.get("extension", "").lower()), reverse=reverse)
    else:
        file_list.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    parent = "/".join(subpath.split("/")[:-1]) if subpath else None
    if parent == "":
        parent = None

    return jsonify({
        "path": subpath, "parent": parent, "breadcrumbs": breadcrumbs,
        "files": file_list,
        "dir_count": sum(1 for f in file_list if f["is_dir"]),
        "file_count": sum(1 for f in file_list if not f["is_dir"]),
        "sort": sort_by, "order": sort_order,
    })


# ─── Directory Operations ────────────────────────────────────────

@files_bp.route("/api/files/mkdir", methods=["POST"])
@login_required
def create_directory():
    """Demo mode: Create directory disabled."""
    return make_response(jsonify({
        "error": "Demo 无法修改服务器内容，请自行部署查看"
    }), 403)


@files_bp.route("/api/files/create-file", methods=["POST"])
@login_required
def create_file():
    """Demo mode: Create file disabled."""
    return make_response(jsonify({
        "error": "Demo 无法修改服务器内容，请自行部署查看"
    }), 403)


# ─── Delete (Cookie-based) ─────────────────────────────────────────

@files_bp.route("/api/files/delete", methods=["POST"])
@login_required
def delete_item():
    """Delete files virtually via cookie."""
    data = request.get_json() or {}
    paths = data.get("paths", [])
    if not paths:
        path = data.get("path", "")
        if path:
            paths = [path]
    if not paths:
        return jsonify({"error": "No path specified."}), 400

    state = get_virtual_state()
    deleted = set(state.get("deleted", []))
    renamed = state.get("renamed", {})

    for p in paths:
        p = p.strip()
        if not p:
            continue
        # If it's a renamed path, delete the original
        original = None
        for old_path, new_path in renamed.items():
            if new_path == p:
                original = old_path
                break
        if original:
            deleted.add(original)
            del renamed[original]
        else:
            deleted.add(p)
        # Also remove from renamed if it exists as old key
        if p in renamed:
            del renamed[p]

    state["deleted"] = list(deleted)
    state["renamed"] = renamed
    resp = make_response(jsonify({"success": True, "message": "已删除"}))
    save_virtual_state(state, resp)
    return resp


# ─── Rename (Cookie-based) ─────────────────────────────────────────

@files_bp.route("/api/files/rename", methods=["POST"])
@login_required
def rename_item():
    """Rename files virtually via cookie."""
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not path or not new_name:
        return jsonify({"error": "Path and new_name required."}), 400

    state = get_virtual_state()
    renamed = state.get("renamed", {})

    # Compute new path
    parts = path.split("/")
    parts[-1] = new_name
    new_path = "/".join(parts)

    # Check if new_path already exists (in demo list or in renamed)
    all_files = get_all_demo_files()
    all_files = apply_virtual_state(all_files, state)
    existing_paths = {f["path"] for f in all_files}
    if new_path in existing_paths and new_path != path:
        return jsonify({"error": "目标名称已存在"}), 409

    renamed[path] = new_path
    state["renamed"] = renamed
    resp = make_response(jsonify({"success": True, "message": "重命名成功"}))
    save_virtual_state(state, resp)
    return resp


# ─── Download (Generate empty files on the fly) ────────────────────

@files_bp.route("/api/files/download", methods=["GET", "POST"])
@login_required
def download_items():
    """Download virtual files - generates empty content for demo."""
    if request.method == "GET":
        subpath = request.args.get("path", "").strip()
        if not subpath:
            return jsonify({"error": "Path is required."}), 400

        # Verify file exists in virtual filesystem
        state = get_virtual_state()
        all_files = get_all_demo_files()
        all_files = apply_virtual_state(all_files, state)
        valid_paths = {f["path"] for f in all_files if not f["is_dir"]}

        if subpath not in valid_paths:
            return jsonify({"error": "File not found."}), 404

        filename = subpath.split("/")[-1]
        # Send empty file
        buf = io.BytesIO(b"")
        return send_file(
            buf, as_attachment=True,
            download_name=filename,
            mimetype=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        )

    # POST - ZIP download for selected files
    data = request.get_json() or {}
    paths = data.get("paths", [])
    zip_name = data.get("zip_name", "download.zip")
    if not paths:
        return jsonify({"error": "No files selected."}), 400

    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(temp_fd)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                base_name = p.split("/")[-1]
                info = zipfile.ZipInfo(base_name)
                info.date_time = datetime.now().timetuple()[:6]
                zf.writestr(info, b"")
        return send_file(temp_path, as_attachment=True, download_name=zip_name, mimetype="application/zip")
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"error": str(e)}), 500


# ─── Upload - DISABLED IN DEMO MODE ────────────────────────────────

@files_bp.route("/api/files/upload", methods=["POST"])
@login_required
def upload_file():
    """Demo mode: Upload disabled."""
    return make_response(jsonify({
        "error": "Demo 无法修改服务器内容，请自行部署查看"
    }), 403)


# ─── Remote Download - DISABLED IN DEMO MODE ──────────────────────

@files_bp.route("/api/files/remote-download", methods=["POST"])
@login_required
def remote_download():
    """Demo mode: Remote download disabled."""
    return make_response(jsonify({
        "error": "Demo 无法修改服务器内容，请自行部署查看"
    }), 403)


@files_bp.route("/api/files/download-tasks", methods=["GET"])
@login_required
def list_download_tasks():
    return jsonify({"tasks": []})


@files_bp.route("/api/files/download-task/<int:task_id>", methods=["GET"])
@login_required
def get_download_task_status(task_id):
    return jsonify({"error": "Not found."}), 404


@files_bp.route("/api/files/download-task/<int:task_id>", methods=["DELETE"])
@login_required
def remove_download_task(task_id):
    return jsonify({"error": "Not found."}), 404


# ─── Directory Status ─────────────────────────────────────────────

@files_bp.route("/api/files/dirstat", methods=["GET"])
@login_required
def directory_status():
    """Get directory statistics for demo."""
    all_files = get_all_demo_files()
    state = get_virtual_state()
    all_files = apply_virtual_state(all_files, state)
    total_files = sum(1 for f in all_files if not f["is_dir"])
    total_dirs = sum(1 for f in all_files if f["is_dir"])
    return jsonify({
        "path": "/ (virtual demo)", "owner": "demo",
        "permissions": "755",
        "total_files": total_files, "total_dirs": total_dirs,
        "total_size": 0, "total_size_display": "0 B",
    })
