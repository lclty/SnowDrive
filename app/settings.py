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
    update_2fa_last_used, delete_2fa_method,
    get_user_by_id, delete_user_sessions, require_totp_reset,
)
from app.utils import (
    hash_password, verify_password, hash_token,
    login_required, login_required_page,
    get_rp_id, get_origin, bytes_to_b64url,
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
    """Delete a 2FA method. Requires password + another 2FA verification."""
    user = g.current_user
    data = request.get_json() or {}
    method_id = data.get("method_id")
    password = data.get("password", "")
    verify_method_id = data.get("verify_method_id")
    verify_code = data.get("verify_code", "")

    if not method_id:
        return jsonify({"error": "Method ID required."}), 400

    # Must keep at least one method
    if count_2fa_methods(user["id"]) <= 1:
        return jsonify({"error": "Cannot delete the last 2FA method."}), 400

    # Verify password
    if not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Incorrect password."}), 401

    # Verify with another 2FA method
    if verify_method_id and verify_method_id != method_id:
        verify_method = get_2fa_method(verify_method_id)
        if verify_method and verify_method["user_id"] == user["id"]:
            if verify_method["method_type"] == "totp":
                totp = pyotp.TOTP(verify_method["totp_secret"])
                if not totp.verify(verify_code, valid_window=1):
                    return jsonify({"error": "Invalid 2FA verification code."}), 401
            else:
                return jsonify({"error": "Use TOTP to verify deletion."}), 400
        else:
            return jsonify({"error": "Invalid verification method."}), 400
    else:
        return jsonify({"error": "Must provide a different 2FA method to verify."}), 400

    delete_2fa_method(method_id)
    return jsonify({"success": True, "message": "2FA method removed."})
