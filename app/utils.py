"""Utility functions for SnowDrive."""

import os
import re
import hashlib
import secrets
import time
import json
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import bcrypt
import jwt
import requests
from base64 import urlsafe_b64encode
from flask import request, jsonify, g

from app.config import Config
from app.models import get_session, get_user_by_id
from app.models import (
    create_download_task,
    update_download_progress,
    complete_download,
)

# ─── Password utilities ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

# ─── JWT utilities ──────────────────────────────────────────────────

def create_jwt(user_id: int, expiry_seconds: int = None) -> str:
    if expiry_seconds is None:
        expiry_seconds = Config.SESSION_DAYS * 86400
    payload = {
        "user_id": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + expiry_seconds,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")

def decode_jwt(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ─── Token hashing (for DB storage) ─────────────────────────────────

def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def b64_to_bytes(s: str) -> bytes:
    """Convert base64url string to bytes."""
    import base64
    s = s.replace('-', '+').replace('_', '/')
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.b64decode(s)


def bytes_to_b64url(b: bytes) -> str:
    """Convert bytes to base64url string (no padding)."""
    return urlsafe_b64encode(b).rstrip(b'=').decode('ascii')


# ─── Auth decorator ─────────────────────────────────────────────────

def login_required(f):
    """Decorator to require authentication.
    In demo mode, always use DemoUser without actual session checks.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # DEMO MODE: Always allow access with DemoUser
        from app.auth import get_demo_user
        g.current_user = get_demo_user()
        g.session_token = "demo_token"
        return f(*args, **kwargs)

    return decorated


def login_required_page(f):
    """Decorator for page routes - redirects to login instead of JSON.
    In demo mode, always use DemoUser without actual session checks.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # DEMO MODE: Always allow access with DemoUser
        from app.auth import get_demo_user
        g.current_user = get_demo_user()
        g.session_token = "demo_token"
        return f(*args, **kwargs)

    return decorated


def redirect_to_login():
    """Redirect to login page."""
    from flask import redirect, url_for

    return redirect(url_for("auth.login_page"))


# ─── File utilities ─────────────────────────────────────────────────

def safe_join_path(base: str, relative: str) -> str | None:
    """Safely join paths, preventing directory traversal."""
    # Normalize the path
    normalized = os.path.normpath(os.path.join(base, relative))
    # Ensure it's within the base directory
    if not normalized.startswith(os.path.normpath(base) + os.sep) and normalized != os.path.normpath(
        base
    ):
        return None
    return normalized


def get_file_info(filepath: str, base_dir: str) -> dict:
    """Get file information as a dictionary."""
    stat = os.stat(filepath)
    rel_path = os.path.relpath(filepath, base_dir)
    is_dir = os.path.isdir(filepath)
    name = os.path.basename(filepath)

    # Determine file type/extension
    if is_dir:
        file_type = "folder"
        extension = ""
    else:
        _, extension = os.path.splitext(name)
        extension = extension.lower()
        file_type = get_file_type_description(extension)

    # Format size
    size = stat.st_size if not is_dir else 0
    size_display = format_file_size(size) if not is_dir else "—"

    return {
        "name": name,
        "path": rel_path.replace("\\", "/"),
        "is_dir": is_dir,
        "size": size,
        "size_display": size_display,
        "extension": extension,
        "file_type": file_type,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "modified_display": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "permissions": oct(stat.st_mode)[-3:],
        "owner": get_file_owner(filepath),
    }


def get_file_owner(filepath: str) -> str:
    """Get file owner name."""
    try:
        import pwd

        stat = os.stat(filepath)
        return pwd.getpwuid(stat.st_uid).pw_name
    except (ImportError, KeyError):
        return str(os.stat(filepath).st_uid)


def get_file_type_description(ext: str) -> str:
    """Get a human-readable file type description."""
    type_map = {
        # Documents
        ".txt": "Text Document",
        ".md": "Markdown",
        ".pdf": "PDF Document",
        ".doc": "Word Document",
        ".docx": "Word Document",
        ".xls": "Excel Spreadsheet",
        ".xlsx": "Excel Spreadsheet",
        ".ppt": "PowerPoint",
        ".pptx": "PowerPoint",
        ".csv": "CSV File",
        # Images
        ".jpg": "JPEG Image",
        ".jpeg": "JPEG Image",
        ".png": "PNG Image",
        ".gif": "GIF Image",
        ".bmp": "Bitmap Image",
        ".svg": "SVG Image",
        ".webp": "WebP Image",
        ".ico": "Icon",
        # Archives
        ".zip": "ZIP Archive",
        ".rar": "RAR Archive",
        ".7z": "7-Zip Archive",
        ".tar": "TAR Archive",
        ".gz": "GZip Archive",
        ".bz2": "BZip2 Archive",
        # Code
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".xml": "XML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".c": "C Source",
        ".cpp": "C++ Source",
        ".h": "C Header",
        ".java": "Java",
        ".rs": "Rust",
        ".go": "Go",
        ".rb": "Ruby",
        ".php": "PHP",
        ".sql": "SQL",
        ".sh": "Shell Script",
        ".bat": "Batch File",
        # Media
        ".mp3": "MP3 Audio",
        ".wav": "WAV Audio",
        ".flac": "FLAC Audio",
        ".mp4": "MP4 Video",
        ".avi": "AVI Video",
        ".mkv": "MKV Video",
        ".mov": "QuickTime Video",
        ".wmv": "WMV Video",
        # Other
        ".iso": "ISO Image",
        ".exe": "Executable",
        ".dll": "Dynamic Library",
        ".apk": "Android Package",
        ".ttf": "Font",
        ".otf": "Font",
        ".woff": "Web Font",
        ".woff2": "Web Font",
    }
    ext_lower = ext.lower()
    return type_map.get(ext_lower, f"{ext[1:].upper() if ext else 'Unknown'} File")


def format_file_size(size: int) -> str:
    """Format file size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def get_file_icon_class(name: str, is_dir: bool, ext: str) -> str:
    """Get Font Awesome icon class for a file/folder."""
    if is_dir:
        return "fa-folder"

    ext_lower = ext.lower()
    icon_map = {
        # Images
        ".jpg": "fa-file-image",
        ".jpeg": "fa-file-image",
        ".png": "fa-file-image",
        ".gif": "fa-file-image",
        ".bmp": "fa-file-image",
        ".svg": "fa-file-image",
        ".webp": "fa-file-image",
        ".ico": "fa-file-image",
        # Archives
        ".zip": "fa-file-zipper",
        ".rar": "fa-file-zipper",
        ".7z": "fa-file-zipper",
        ".tar": "fa-file-zipper",
        ".gz": "fa-file-zipper",
        ".bz2": "fa-file-zipper",
        # Audio
        ".mp3": "fa-file-audio",
        ".wav": "fa-file-audio",
        ".flac": "fa-file-audio",
        ".aac": "fa-file-audio",
        ".ogg": "fa-file-audio",
        # Video
        ".mp4": "fa-file-video",
        ".avi": "fa-file-video",
        ".mkv": "fa-file-video",
        ".mov": "fa-file-video",
        ".wmv": "fa-file-video",
        # Code
        ".py": "fa-file-code",
        ".js": "fa-file-code",
        ".ts": "fa-file-code",
        ".html": "fa-file-code",
        ".css": "fa-file-code",
        ".json": "fa-file-code",
        ".xml": "fa-file-code",
        ".yaml": "fa-file-code",
        ".yml": "fa-file-code",
        ".c": "fa-file-code",
        ".cpp": "fa-file-code",
        ".h": "fa-file-code",
        ".java": "fa-file-code",
        ".rs": "fa-file-code",
        ".go": "fa-file-code",
        ".rb": "fa-file-code",
        ".php": "fa-file-code",
        ".sql": "fa-file-code",
        ".sh": "fa-file-code",
        ".bat": "fa-file-code",
        # Documents
        ".pdf": "fa-file-pdf",
        ".doc": "fa-file-word",
        ".docx": "fa-file-word",
        ".xls": "fa-file-excel",
        ".xlsx": "fa-file-excel",
        ".ppt": "fa-file-powerpoint",
        ".pptx": "fa-file-powerpoint",
        ".txt": "fa-file-lines",
        ".md": "fa-file-lines",
        ".csv": "fa-file-csv",
        # Fonts
        ".ttf": "fa-file",
        ".otf": "fa-file",
        ".woff": "fa-file",
        ".woff2": "fa-file",
    }

    return icon_map.get(ext_lower, "fa-file")


# ─── WebAuthn Helpers ──────────────────────────────────────────────

def get_rp_id() -> str:
    """Derive RP ID from request host."""
    host = request.host.split(":")[0] if request.host else "localhost"
    return host

def get_origin() -> str:
    """Derive origin from request."""
    scheme = "https" if request.headers.get("X-Forwarded-Proto") == "https" else request.scheme
    return f"{scheme}://{request.host}"


# ─── Background Download ───────────────────────────────────────────

_download_workers: dict[int, dict] = {}

def start_background_download(task_id: int, url: str, dest_path: str, user_id: int):
    """Start a background download thread with cancel support."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_do_download,
        args=(task_id, url, dest_path, stop_event),
        daemon=True,
    )
    _download_workers[task_id] = {"thread": thread, "stop_event": stop_event, "dest_path": dest_path}
    thread.start()

def _do_download(task_id: int, url: str, dest_path: str, stop_event: threading.Event):
    """Execute a download in background."""
    try:
        proxies = {}
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy

        resp = requests.get(
            url,
            stream=True,
            timeout=300,
            proxies=proxies if proxies else None,
            headers={"User-Agent": "SnowDrive/1.0"},
        )
        resp.raise_for_status()

        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if stop_event.is_set():
                    raise Exception("Cancelled")
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    update_download_progress(task_id, downloaded, total_size)

        complete_download(task_id, True)
        # Remove task record after successful completion (keep the downloaded file)
        try:
            from app.models import delete_download_task
            delete_download_task(task_id)
        except Exception:
            pass

    except Exception as e:
        # Mark as failed and clean partial file
        try:
            complete_download(task_id, False, str(e))
        except Exception:
            pass
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
    finally:
        _download_workers.pop(task_id, None)

def stop_background_download(task_id: int) -> bool:
    """Request cancellation of a background download and remove partial file."""
    worker = _download_workers.get(task_id)
    if not worker:
        return False
    try:
        stop_event = worker.get('stop_event')
        if stop_event:
            stop_event.set()
        thread = worker.get('thread')
        if thread and thread.is_alive():
            thread.join(timeout=1)
        dest = worker.get('dest_path')
        if dest and os.path.exists(dest):
            os.remove(dest)
    except Exception:
        pass
    _download_workers.pop(task_id, None)
    return True
