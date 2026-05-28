"""User settings module for SnowDrive - Multi-2FA management."""

import os
import io
import base64
import secrets
import json

import pyotp
import qrcode
from flask import Blueprint, request, jsonify, render_template, g, make_response, session as flask_session

from app.config import Config
from app.models import (
    update_user_password, update_user_avatar,
    get_user_2fa_methods, count_2fa_methods, get_2fa_method,
    add_totp_method, add_webauthn_method, get_webauthn_credential,
    update_2fa_last_used, delete_2fa_method, rename_2fa_method,
    update_webauthn_sign_count,
    get_user_by_id, delete_user_sessions, require_totp_reset,
)
from app.utils import (
    hash_password, verify_password, hash_token,
    login_required, login_required_page,
    get_rp_id, get_origin, bytes_to_b64url, b64_to_bytes,
)

settings_bp = Blueprint("settings", __name__)


# ─── Page Route ─────────────────────────────────────────────────────

@settings_bp.route("/settings")
@login_required_page
def settings_page():
    user = g.current_user
    # Force 2FA setup if no methods exist
    if not user.get("totp_required_reset") and len(get_user_2fa_methods(user["id"])) == 0:
        require_totp_reset(user["id"])
        from flask import redirect, url_for
        return redirect(url_for("auth.reset_2fa_page"))
    methods = get_user_2fa_methods(user["id"])
    return render_template("settings.html",
        username=user["username"],
        has_avatar=bool(user.get("avatar_path")),
        twofa_methods=methods,
        has_recovery_codes=False,
    )


# ─── Profile API ────────────────────────────────────────────────────

@settings_bp.route("/api/settings/profile", methods=["GET"])
@login_required
def get_profile():
    user = g.current_user
    methods = get_user_2fa_methods(user["id"])
    return jsonify({
        "username": user["username"],
        "has_avatar": bool(user.get("avatar_path")),
        "avatar_url": "/api/settings/avatar" if user.get("avatar_path") else None,
        "twofa_methods": [{"id": m["id"], "type": m["method_type"], "name": m["method_name"]} for m in methods],
        "created_at": user.get("created_at"),
    })


@settings_bp.route("/api/settings/avatar", methods=["GET"])
@login_required
def get_avatar():
    user = g.current_user
    avatar_path = user.get("avatar_path")
    if avatar_path and os.path.exists(avatar_path):
        from flask import send_file
        return send_file(avatar_path, mimetype="image/png")
    default_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect width="128" height="128" fill="#4a6cf7" rx="64"/><text x="64" y="80" text-anchor="middle" font-size="56" font-family="Arial,sans-serif" fill="white">{user["username"][0].upper()}</text></svg>'
    from flask import Response
    return Response(default_svg, mimetype="image/svg+xml")


@settings_bp.route("/api/settings/avatar", methods=["POST"])
@login_required
def upload_avatar():
    if "avatar" not in request.files:
        return jsonify({"error": "No file."}), 400
    file = request.files["avatar"]
    if not file.filename:
        return jsonify({"error": "No file."}), 400
    allowed = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    if file.mimetype not in allowed and not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return jsonify({"error": "Only PNG, JPEG, GIF, WebP allowed."}), 400
    file.seek(0, os.SEEK_END)
    if file.tell() > 2 * 1024 * 1024:
        return jsonify({"error": "Max 2MB."}), 400
    file.seek(0)
    user = g.current_user
    os.makedirs(Config.AVATAR_DIR, exist_ok=True)
    old = user.get("avatar_path")
    if old and os.path.exists(old):
        try: os.remove(old)
        except OSError: pass
    ext = os.path.splitext(file.filename)[1].lower() or ".png"
    avatar_path = os.path.join(Config.AVATAR_DIR, f"avatar_{user['id']}{ext}")
    file.save(avatar_path)
    update_user_avatar(user["id"], avatar_path)
    return jsonify({"success": True})


@settings_bp.route("/api/settings/avatar", methods=["DELETE"])
@login_required
def remove_avatar():
    user = g.current_user
    old = user.get("avatar_path")
    if old and os.path.exists(old):
        try: os.remove(old)
        except OSError: pass
    update_user_avatar(user["id"], None)
    return jsonify({"success": True})


# ─── Password ───────────────────────────────────────────────────────

@settings_bp.route("/api/settings/password", methods=["PUT"])
@login_required
def change_password():
    data = request.get_json() or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    if not current_password or not new_password:
        return jsonify({"error": "Both passwords required."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Min 8 characters."}), 400
    user = g.current_user
    if not verify_password(current_password, user["password_hash"]):
        return jsonify({"error": "Incorrect current password."}), 401
    new_hash = hash_password(new_password)
    update_user_password(user["id"], new_hash)
    token_hash = hash_token(g.session_token)
    from app.models import get_db
    db = get_db()
    db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user["id"], token_hash))
    db.commit()
    return jsonify({"success": True})


# ─── 2FA Methods Management ────────────────────────────────────────

@settings_bp.route("/api/settings/2fa/methods", methods=["GET"])
@login_required
def list_2fa_methods():
    methods = get_user_2fa_methods(g.current_user["id"])
    return jsonify({"methods": [{"id": m["id"], "type": m["method_type"], "name": m["method_name"], "created_at": m["created_at"]} for m in methods]})


@settings_bp.route("/api/settings/2fa/totp/generate", methods=["POST"])
@login_required
def settings_totp_generate():
    user = g.current_user
    secret = pyotp.random_base32()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=Config.TOTP_ISSUER)
    qr_img = qrcode.make(totp_uri)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    resp = make_response(jsonify({"success": True, "secret": secret, "qr_code": f"data:image/png;base64,{qr_b64}"}))
    resp.set_cookie("snowdrive_pending_totp", secret, max_age=600, httponly=True, samesite="Lax", secure=False)
    return resp


@settings_bp.route("/api/settings/2fa/totp/verify", methods=["POST"])
@login_required
def settings_totp_verify():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip()
    method_name = (data.get("name") or "Authenticator").strip()
    pending_secret = request.cookies.get("snowdrive_pending_totp")
    if not pending_secret:
        return jsonify({"error": "No pending setup."}), 400
    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({"error": "Invalid code."}), 400
    user = g.current_user
    add_totp_method(user["id"], pending_secret, method_name)
    resp = make_response(jsonify({"success": True, "message": "TOTP added."}))
    resp.delete_cookie("snowdrive_pending_totp")
    return resp


@settings_bp.route("/api/settings/2fa/webauthn/register-begin", methods=["POST"])
@login_required
def settings_webauthn_register_begin():
    try:
        from webauthn import generate_registration_options
        from webauthn.helpers import options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria, AuthenticatorAttachment,
            ResidentKeyRequirement, UserVerificationRequirement,
        )
    except ImportError:
        return jsonify({"error": "WebAuthn not available."}), 500
    user = g.current_user
    rp_id = get_rp_id()
    challenge = secrets.token_hex(32)
    flask_session["webauthn_reg_challenge"] = challenge
    flask_session["webauthn_reg_user_id"] = user["id"]
    options = generate_registration_options(
        rp_id=rp_id, rp_name=Config.WEBAUTHN_RP_NAME,
        user_id=str(user["id"]).encode(), user_name=user["username"],
        user_display_name=user["username"],
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        challenge=challenge.encode(),
    )
    try:
        opts_json = json.loads(options_to_json(options))
    except Exception as e:
        return jsonify({"error": f"Failed to serialize WebAuthn options: {str(e)}"}), 500
    return jsonify({"success": True, "options": opts_json, "challenge": challenge, "rp_id": rp_id})


@settings_bp.route("/api/settings/2fa/webauthn/register-verify", methods=["POST"])
@login_required
def settings_webauthn_register_verify():
    try:
        from webauthn import verify_registration_response
    except ImportError:
        return jsonify({"error": "WebAuthn not available."}), 500
    data = request.get_json() or {}
    credential_data = data.get("credential", {})
    method_name = (data.get("name") or "Passkey").strip()
    challenge = flask_session.get("webauthn_reg_challenge", "")
    rp_id = get_rp_id()
    origin = get_origin()
    if not credential_data or not challenge:
        return jsonify({"error": "Invalid data."}), 400
    try:
        verification = verify_registration_response(
            credential=credential_data,
            expected_challenge=challenge.encode(),
            expected_rp_id=rp_id, expected_origin=origin,
        )
    except Exception as e:
        return jsonify({"error": f"Verification failed: {str(e)}"}), 400
    user = g.current_user
    add_webauthn_method(user["id"], bytes_to_b64url(verification.credential_id),
                        verification.credential_public_key,
                        verification.sign_count, rp_id, method_name)
    flask_session.pop("webauthn_reg_challenge", None)
    flask_session.pop("webauthn_reg_user_id", None)
    return jsonify({"success": True, "message": "Passkey added."})


@settings_bp.route("/api/settings/2fa/delete", methods=["POST"])
@login_required
def delete_2fa_endpoint():
    """Delete a 2FA method. Requires password + 2FA verification (any existing method, including the one being deleted)."""
    user = g.current_user
    data = request.get_json() or {}
    method_id = data.get("method_id")
    password = data.get("password", "")
    verify_method_id = data.get("verify_method_id")
    verify_code = data.get("verify_code", "")
    verify_credential = data.get("verify_credential")

    if not method_id:
        return jsonify({"error": "Method ID required."}), 400

    # Must keep at least one method
    if count_2fa_methods(user["id"]) <= 1:
        return jsonify({"error": "Cannot delete the last 2FA method."}), 400

    # Verify password
    if not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Incorrect password."}), 401

    # Verify with any existing 2FA method (including the one being deleted)
    if not verify_method_id:
        return jsonify({"error": "Must provide a 2FA method to verify."}), 400

    verify_method = get_2fa_method(verify_method_id)
    if not verify_method or verify_method["user_id"] != user["id"]:
        return jsonify({"error": "Invalid verification method."}), 400

    if verify_method["method_type"] == "totp":
        if not verify_code:
            return jsonify({"error": "TOTP code required."}), 400
        totp = pyotp.TOTP(verify_method["totp_secret"])
        if not totp.verify(verify_code, valid_window=1):
            return jsonify({"error": "Invalid 2FA verification code."}), 401
    elif verify_method["method_type"] == "webauthn":
        if not verify_credential:
            return jsonify({"error": "WebAuthn credential required."}), 400
        try:
            from webauthn import verify_authentication_response
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
        challenge = flask_session.get("webauthn_del_challenge", "")
        rp_id = get_rp_id()
        origin = get_origin()
        cred_id = verify_credential.get("id") or verify_credential.get("rawId")
        if not cred_id:
            return jsonify({"error": "Invalid credential."}), 400
        stored = get_webauthn_credential(cred_id)
        if not stored or stored["user_id"] != user["id"]:
            return jsonify({"error": "Unknown credential."}), 400
        try:
            verification_result = verify_authentication_response(
                credential=verify_credential,
                expected_challenge=challenge.encode() if challenge else b"",
                expected_rp_id=rp_id, expected_origin=origin,
                credential_public_key=stored["credential_public_key"],
                credential_current_sign_count=stored["sign_count"],
            )
        except Exception as e:
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 401
        update_webauthn_sign_count(stored["id"], verification_result.new_sign_count)
        flask_session.pop("webauthn_del_challenge", None)
    else:
        return jsonify({"error": "Unknown verification method type."}), 400

    delete_2fa_method(method_id)
    return jsonify({"success": True, "message": "2FA method removed."})


@settings_bp.route("/api/settings/2fa/webauthn/auth-begin", methods=["POST"])
@login_required
def settings_webauthn_auth_begin():
    """Begin WebAuthn authentication for 2FA delete verification."""
    user = g.current_user
    try:
        from webauthn import generate_authentication_options
        from webauthn.helpers import options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    except ImportError:
        return jsonify({"error": "WebAuthn not available."}), 500
    methods = get_user_2fa_methods(user["id"])
    webauthn_methods = [m for m in methods if m["method_type"] == "webauthn"]
    if not webauthn_methods:
        return jsonify({"error": "No WebAuthn methods."}), 400
    challenge = secrets.token_hex(32)
    flask_session["webauthn_del_challenge"] = challenge
    rp_id = get_rp_id()
    allow_credentials = [PublicKeyCredentialDescriptor(id=b64_to_bytes(m["credential_id"])) for m in webauthn_methods]
    options = generate_authentication_options(rp_id=rp_id, challenge=challenge.encode(), allow_credentials=allow_credentials)
    try:
        from types import SimpleNamespace
        if hasattr(options, 'allow_credentials') and options.allow_credentials:
            for cred in options.allow_credentials:
                if not hasattr(getattr(cred, 'type', None), 'value'):
                    cred.type = SimpleNamespace(value='public-key')
    except Exception:
        pass
    try:
        opts_json = json.loads(options_to_json(options))
    except Exception as e:
        return jsonify({"error": f"Failed to serialize WebAuthn options: {str(e)}"}), 500
    return jsonify({"success": True, "options": opts_json, "challenge": challenge, "rp_id": rp_id})


@settings_bp.route("/api/settings/2fa/rename", methods=["POST"])
@login_required
def rename_2fa_endpoint():
    """Rename a 2FA method."""
    user = g.current_user
    data = request.get_json() or {}
    method_id = data.get("method_id")
    name = (data.get("name") or "").strip()
    if not method_id or not name:
        return jsonify({"error": "Method ID and name required."}), 400
    if len(name) > 64:
        return jsonify({"error": "Name too long (max 64)."}), 400
    method = get_2fa_method(method_id)
    if not method or method["user_id"] != user["id"]:
        return jsonify({"error": "Method not found."}), 404
    rename_2fa_method(method_id, name)
    return jsonify({"success": True, "message": "Renamed."})


# ─── Site Settings API ─────────────────────────────────────────────

@settings_bp.route("/api/settings/site", methods=["GET"])
def get_site_settings():
    from app.models import get_site_setting
    title = get_site_setting("site_title") or ""
    icp_enabled = get_site_setting("icp_enabled") or "0"
    icp_number = get_site_setting("icp_number") or ""
    logo_url = None
    logo_path = get_site_setting("logo_path")
    if logo_path and os.path.exists(logo_path):
        logo_url = "/api/settings/site/logo"
    return jsonify({
        "site_title": title,
        "logo_url": logo_url,
        "icp_enabled": icp_enabled == "1",
        "icp_number": icp_number,
    })


@settings_bp.route("/api/settings/site", methods=["POST"])
@login_required
def save_site_settings():
    from app.models import set_site_setting, delete_site_setting
    data = request.get_json() or {}
    title = (data.get("site_title") or "").strip()
    icp_enabled = "1" if data.get("icp_enabled") else "0"
    icp_number = (data.get("icp_number") or "").strip()
    if icp_number:
        import re
        if not re.match(r'^[^ICP备]*ICP备\d+号(-\d+)?$', icp_number) and not re.match(r'^\d+$', icp_number):
            pass  # Allow flexible input; user can type whatever
    set_site_setting("site_title", title)
    set_site_setting("icp_enabled", icp_enabled)
    set_site_setting("icp_number", icp_number)
    return jsonify({"success": True})


@settings_bp.route("/api/settings/site/logo", methods=["GET"])
def get_site_logo():
    from app.models import get_site_setting
    logo_path = get_site_setting("logo_path")
    if logo_path and os.path.exists(logo_path):
        from flask import send_file
        return send_file(logo_path)
    return jsonify({"error": "No logo."}), 404


@settings_bp.route("/api/settings/site/logo", methods=["POST"])
@login_required
def upload_site_logo():
    from app.models import set_site_setting, get_site_setting
    if "logo" not in request.files:
        return jsonify({"error": "No file."}), 400
    file = request.files["logo"]
    if not file.filename:
        return jsonify({"error": "No file."}), 400
    allowed = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
    if file.mimetype not in allowed and not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return jsonify({"error": "Only image files allowed."}), 400
    file.seek(0, os.SEEK_END)
    if file.tell() > 2 * 1024 * 1024:
        return jsonify({"error": "Max 2MB."}), 400
    file.seek(0)
    os.makedirs(Config.LOGO_DIR, exist_ok=True)
    old = get_site_setting("logo_path")
    if old and os.path.exists(old):
        try: os.remove(old)
        except OSError: pass
    ext = os.path.splitext(file.filename)[1].lower() or ".png"
    logo_path = os.path.join(Config.LOGO_DIR, f"site_logo{ext}")
    file.save(logo_path)
    set_site_setting("logo_path", logo_path)
    return jsonify({"success": True})


@settings_bp.route("/api/settings/site/logo", methods=["DELETE"])
@login_required
def remove_site_logo():
    from app.models import get_site_setting, delete_site_setting
    old = get_site_setting("logo_path")
    if old and os.path.exists(old):
        try: os.remove(old)
        except OSError: pass
    delete_site_setting("logo_path")
    return jsonify({"success": True})
