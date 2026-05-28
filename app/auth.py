"""Authentication module for SnowDrive - DEMO MODE.
Simplified authentication that bypasses login/2FA for demo purposes.
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, g

auth_bp = Blueprint("auth", __name__)

# Demo configuration
DEMO_USERNAME = "DemoUser"
DEMO_USER_ID = 1


# ─── Page Routes ────────────────────────────────────────────────────

@auth_bp.route("/")
def index():
    """Redirect to file manager for demo."""
    return redirect(url_for("files.file_manager"))


@auth_bp.route("/login")
def login_page():
    """Demo mode - redirect to file manager."""
    return redirect(url_for("files.file_manager"))


@auth_bp.route("/register")
def register_page():
    """Demo mode - redirect to file manager."""
    return redirect(url_for("files.file_manager"))


@auth_bp.route("/setup-2fa")
def setup_2fa_page():
    """Demo mode - redirect to file manager."""
    return redirect(url_for("files.file_manager"))


@auth_bp.route("/reset-2fa")
def reset_2fa_page():
    """Demo mode - redirect to file manager."""
    return redirect(url_for("files.file_manager"))


# ─── API: Auth Status ───────────────────────────────────────────────

@auth_bp.route("/api/auth/status", methods=["GET"])
def auth_status():
    """Return demo user status - always logged in."""
    return jsonify({
        "has_users": True,
        "logged_in": True,
        "username": DEMO_USERNAME,
        "needs_2fa_reset": False,
        "has_avatar": False,
        "is_demo": True,
    })


# ─── API: Login (Demo - always succeeds) ─────────────────────────────

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """Demo mode - always login as DemoUser."""
    return jsonify({
        "success": True,
        "message": "Demo mode - logged in as DemoUser",
        "username": DEMO_USERNAME,
    })


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    """Demo mode - logout."""
    return jsonify({
        "success": True,
        "message": "Logged out",
    })


# ─── Dummy endpoints that do nothing in demo mode ─────────────────────

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    """Demo mode - not available."""
    return jsonify({"error": "Registration disabled in demo mode."}), 403


@auth_bp.route("/api/auth/setup-2fa", methods=["POST"])
def setup_2fa():
    """Demo mode - not available."""
    return jsonify({"error": "2FA setup disabled in demo mode."}), 403


@auth_bp.route("/api/auth/login-2fa", methods=["POST"])
def login_2fa():
    """Demo mode - not available."""
    return jsonify({"error": "2FA disabled in demo mode."}), 403


@auth_bp.route("/api/auth/webauthn-auth-begin", methods=["POST"])
def webauthn_auth_begin():
    """Demo mode - not available."""
    return jsonify({"error": "WebAuthn disabled in demo mode."}), 403


# ─── Middleware helper ────────────────────────────────────────────────

def get_demo_user():
    """Get demo user info for use in other modules."""
    return {
        "id": DEMO_USER_ID,
        "username": DEMO_USERNAME,
        "avatar_path": None,
        "totp_required_reset": False,
    }
