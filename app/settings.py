"""User settings module for SnowDrive - DEMO MODE (Cookie-based settings)."""

import os
import json
import base64

from flask import Blueprint, request, jsonify, render_template, g, make_response

from app.utils import login_required, login_required_page

settings_bp = Blueprint("settings", __name__)


# ─── Cookie Helpers ──────────────────────────────────────────────────

def get_settings_cookie():
    """Read settings from cookie."""
    cookie = request.cookies.get("snowdrive_settings")
    if not cookie:
        return {}
    try:
        return json.loads(base64.b64decode(cookie))
    except Exception:
        return {}


def make_settings_response(data, status=200):
    """Make a response that saves settings to cookie."""
    resp = make_response(jsonify(data), status)
    settings = get_settings_cookie()
    # Merge with existing settings
    settings.update(data)
    try:
        cookie_data = base64.b64encode(json.dumps(settings).encode()).decode()
        resp.set_cookie("snowdrive_settings", cookie_data, max_age=30*24*3600, httponly=True, samesite="Lax")
    except Exception:
        pass
    return resp


def get_site_settings_from_cookie():
    """Get site display settings from cookie."""
    s = get_settings_cookie()
    return {
        "site_title": s.get("site_title", ""),
        "logo_url": s.get("logo_url"),
        "icp_enabled": s.get("icp_enabled", False),
        "icp_number": s.get("icp_number", ""),
        "theme": s.get("theme", "light"),
    }


# ─── Page Route ─────────────────────────────────────────────────────

@settings_bp.route("/settings")
@login_required_page
def settings_page():
    return render_template("settings.html", username="DemoUser", has_avatar=False, twofa_methods=[], has_recovery_codes=False)


# ─── Profile API (Cookie-based) ─────────────────────────────────────

@settings_bp.route("/api/settings/profile", methods=["GET"])
@login_required
def get_profile():
    settings = get_settings_cookie()
    return jsonify({
        "username": "DemoUser",
        "has_avatar": False,
        "avatar_url": None,
        "twofa_methods": [],
        "created_at": None,
        "display_name": settings.get("display_name", "DemoUser"),
    })


@settings_bp.route("/api/settings/avatar", methods=["GET"])
@login_required
def get_avatar():
    default_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect width="128" height="128" fill="#4a6cf7" rx="64"/><text x="64" y="80" text-anchor="middle" font-size="56" font-family="Arial,sans-serif" fill="white">D</text></svg>'
    from flask import Response
    return Response(default_svg, mimetype="image/svg+xml")


@settings_bp.route("/api/settings/avatar", methods=["POST"])
@login_required
def upload_avatar():
    """Demo mode: avatar upload simulated via cookie."""
    return make_settings_response({"success": True, "message": "Demo mode - avatar not saved to server"})


@settings_bp.route("/api/settings/avatar", methods=["DELETE"])
@login_required
def remove_avatar():
    return make_settings_response({"success": True})


# ─── Password (Demo - disabled) ─────────────────────────────────────

@settings_bp.route("/api/settings/password", methods=["PUT"])
@login_required
def change_password():
    return jsonify({"error": "Demo 无法修改服务器内容，请自行部署查看"}), 403


# ─── 2FA (Demo - disabled) ─────────────────────────────────────────

@settings_bp.route("/api/settings/2fa/methods", methods=["GET"])
@login_required
def list_2fa_methods():
    return jsonify({"methods": []})


@settings_bp.route("/api/settings/2fa/totp/generate", methods=["POST"])
@login_required
def settings_totp_generate():
    return jsonify({"error": "2FA disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/totp/verify", methods=["POST"])
@login_required
def settings_totp_verify():
    return jsonify({"error": "2FA disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/webauthn/register-begin", methods=["POST"])
@login_required
def settings_webauthn_register_begin():
    return jsonify({"error": "WebAuthn disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/webauthn/register-verify", methods=["POST"])
@login_required
def settings_webauthn_register_verify():
    return jsonify({"error": "WebAuthn disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/delete", methods=["POST"])
@login_required
def delete_2fa_endpoint():
    return jsonify({"error": "2FA disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/webauthn/auth-begin", methods=["POST"])
@login_required
def settings_webauthn_auth_begin():
    return jsonify({"error": "WebAuthn disabled in demo mode."}), 403


@settings_bp.route("/api/settings/2fa/rename", methods=["POST"])
@login_required
def rename_2fa_endpoint():
    return jsonify({"error": "2FA disabled in demo mode."}), 403


# ─── Site Settings API (Cookie-based) ───────────────────────────────

@settings_bp.route("/api/settings/site", methods=["GET"])
def get_site_settings():
    return jsonify(get_site_settings_from_cookie())


@settings_bp.route("/api/settings/site", methods=["POST"])
@login_required
def save_site_settings():
    data = request.get_json() or {}
    settings = get_settings_cookie()
    settings.update({k: v for k, v in data.items() if k in ("site_title", "icp_enabled", "icp_number", "logo_url", "theme")})
    resp = make_response(jsonify({"success": True}))
    try:
        cookie_data = base64.b64encode(json.dumps(settings).encode()).decode()
        resp.set_cookie("snowdrive_settings", cookie_data, max_age=30*24*3600, httponly=True, samesite="Lax")
    except Exception:
        pass
    return resp


@settings_bp.route("/api/settings/site/logo", methods=["GET"])
def get_site_logo():
    return jsonify({"error": "No logo."}), 404


@settings_bp.route("/api/settings/site/logo", methods=["POST"])
@login_required
def upload_site_logo():
    return jsonify({"error": "Demo mode: logo upload disabled."}), 403


@settings_bp.route("/api/settings/site/logo", methods=["DELETE"])
@login_required
def remove_site_logo():
    return jsonify({"success": True})
