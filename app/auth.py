"""Authentication module for SnowDrive.
Supports mandatory 2FA with multiple methods: TOTP, WebAuthn (Windows Hello/macOS)."""

import io
import json
import base64
import secrets
import hashlib
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from flask import (
    Blueprint, request, jsonify, render_template, make_response,
    redirect, url_for, g, session as flask_session,
)

from app.config import Config
from app.models import (
    get_user_count, get_user_by_username, get_user_by_id,
    create_user, create_session, delete_session, delete_user_sessions,
    require_totp_reset, clear_totp_reset,
    get_user_2fa_methods, count_2fa_methods, get_2fa_method,
    add_totp_method, add_webauthn_method, get_webauthn_credential,
    update_webauthn_sign_count, update_2fa_last_used, delete_2fa_method,
)
from app.utils import (
    hash_password, verify_password, create_jwt, decode_jwt, hash_token,
    login_required, login_required_page,
    get_rp_id, get_origin, bytes_to_b64url, b64_to_bytes,
)

auth_bp = Blueprint("auth", __name__)


# ─── Page Routes ────────────────────────────────────────────────────

@auth_bp.route("/")
def index():
    token = request.cookies.get("snowdrive_token")
    if token:
        token_hash = hash_token(token)
        from app.models import get_session
        session = get_session(token_hash)
        if session:
            user = get_user_by_id(session["user_id"])
            if user:
                if user["totp_required_reset"]:
                    return redirect(url_for("auth.reset_2fa_page"))
                # Check if user has any 2FA methods
                if len(get_user_2fa_methods(user["id"])) == 0:
                    require_totp_reset(user["id"])
                    return redirect(url_for("auth.reset_2fa_page"))
                return redirect(url_for("files.file_manager"))
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/login")
def login_page():
    user_count = get_user_count()
    if user_count == 0:
        return redirect(url_for("auth.register_page"))
    return render_template("login.html")


@auth_bp.route("/register")
def register_page():
    user_count = get_user_count()
    if user_count > 0:
        return redirect(url_for("auth.login_page"))
    return render_template("register.html")


@auth_bp.route("/setup-2fa")
def setup_2fa_page():
    reg_token = request.cookies.get("snowdrive_reg_token")
    if not reg_token:
        return redirect(url_for("auth.register_page"))
    payload = decode_jwt(reg_token)
    if not payload:
        return redirect(url_for("auth.register_page"))
    user = get_user_by_id(payload["user_id"])
    if not user:
        return redirect(url_for("auth.register_page"))
    return render_template("setup_2fa.html", username=user["username"])


@auth_bp.route("/reset-2fa")
def reset_2fa_page():
    token = request.cookies.get("snowdrive_token")
    if not token:
        return redirect(url_for("auth.login_page"))
    token_hash = hash_token(token)
    from app.models import get_session
    session = get_session(token_hash)
    if not session:
        return redirect(url_for("auth.login_page"))
    user = get_user_by_id(session["user_id"])
    if not user or not user["totp_required_reset"]:
        return redirect(url_for("files.file_manager"))
    return render_template("reset_2fa.html", username=user["username"])


# ─── API: Auth Status ───────────────────────────────────────────────

@auth_bp.route("/api/auth/status", methods=["GET"])
def auth_status():
    user_count = get_user_count()
    token = request.cookies.get("snowdrive_token")
    logged_in = False
    username = None
    needs_2fa_reset = False
    has_avatar = False
    if token:
        token_hash = hash_token(token)
        from app.models import get_session
        session = get_session(token_hash)
        if session:
            user = get_user_by_id(session["user_id"])
            if user:
                logged_in = True
                username = user["username"]
                needs_2fa_reset = bool(user["totp_required_reset"])
                has_avatar = bool(user.get("avatar_path"))
    return jsonify({"has_users": user_count > 0, "logged_in": logged_in, "username": username, "needs_2fa_reset": needs_2fa_reset, "has_avatar": has_avatar})


# ─── API: Register ──────────────────────────────────────────────────

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    user_count = get_user_count()
    if user_count > 0:
        return jsonify({"error": "A user already exists."}), 400
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or len(username) < 2 or len(username) > 32:
        return jsonify({"error": "Username must be 2-32 characters."}), 400
    if not username.replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, hyphens, and underscores."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    password_hash = hash_password(password)
    user_id = create_user(username, password_hash)
    reg_token = create_jwt(user_id, expiry_seconds=600)
    resp = make_response(jsonify({"success": True, "message": "User registered. Set up 2FA.", "user_id": user_id}))
    resp.set_cookie("snowdrive_reg_token", reg_token, max_age=600, httponly=True, samesite="Lax", secure=False)
    return resp


# ─── API: Setup 2FA ─────────────────────────────────────────────────

@auth_bp.route("/api/auth/setup-2fa", methods=["POST"])
def setup_2fa():
    reg_token = request.cookies.get("snowdrive_reg_token")
    if not reg_token:
        return jsonify({"error": "Registration session expired."}), 400
    payload = decode_jwt(reg_token)
    if not payload:
        return jsonify({"error": "Registration session expired."}), 400
    user = get_user_by_id(payload["user_id"])
    if not user:
        return jsonify({"error": "User not found."}), 400
    data = request.get_json() or {}
    action = data.get("action", "")

    if action == "totp_generate":
        secret = pyotp.random_base32()
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=Config.TOTP_ISSUER)
        qr_img = qrcode.make(totp_uri)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        resp = make_response(jsonify({"success": True, "secret": secret, "qr_code": f"data:image/png;base64,{qr_b64}"}))
        resp.set_cookie("snowdrive_pending_totp", secret, max_age=600, httponly=True, samesite="Lax", secure=False)
        return resp

    elif action == "totp_verify":
        code = (data.get("code") or "").strip()
        pending_secret = request.cookies.get("snowdrive_pending_totp")
        if not pending_secret:
            return jsonify({"error": "No pending TOTP setup."}), 400
        totp = pyotp.TOTP(pending_secret)
        if not totp.verify(code, valid_window=1):
            return jsonify({"error": "Invalid verification code."}), 400
        add_totp_method(user["id"], pending_secret)
        return _complete_2fa_setup(user)

    elif action == "webauthn_register_begin":
        try:
            from webauthn import generate_registration_options
            from webauthn.helpers import options_to_json
            from webauthn.helpers.structs import (
                AuthenticatorSelectionCriteria, AuthenticatorAttachment,
                ResidentKeyRequirement, UserVerificationRequirement,
            )
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
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

    elif action == "webauthn_register_verify":
        try:
            from webauthn import verify_registration_response
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
        credential_data = data.get("credential", {})
        challenge = flask_session.get("webauthn_reg_challenge", "")
        rp_id = get_rp_id()
        origin = get_origin()
        if not credential_data or not challenge:
            return jsonify({"error": "Invalid registration data."}), 400
        try:
            verification = verify_registration_response(
                credential=credential_data,
                expected_challenge=challenge.encode(),
                expected_rp_id=rp_id, expected_origin=origin,
            )
        except Exception as e:
            return jsonify({"error": f"Verification failed: {str(e)}"}), 400
        add_webauthn_method(user["id"], bytes_to_b64url(verification.credential_id),
                           verification.credential_public_key,
                           verification.sign_count, rp_id,
                           "Windows Hello / Passkey")
        flask_session.pop("webauthn_reg_challenge", None)
        flask_session.pop("webauthn_reg_user_id", None)
        return _complete_2fa_setup(user)

    return jsonify({"error": "Invalid action."}), 400


def _complete_2fa_setup(user: dict):
    jwt_token = create_jwt(user["id"])
    token_hash = hash_token(jwt_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=Config.SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    create_session(user["id"], token_hash, expires_at)
    resp = make_response(jsonify({"success": True, "message": "2FA setup complete. Welcome!"}))
    resp.set_cookie("snowdrive_token", jwt_token, max_age=Config.SESSION_DAYS * 86400, httponly=True, samesite="Lax", secure=False)
    resp.delete_cookie("snowdrive_reg_token")
    resp.delete_cookie("snowdrive_pending_totp")
    return resp


# ─── API: Login ─────────────────────────────────────────────────────

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid username or password."}), 401
    if user["totp_required_reset"]:
        jwt_token = create_jwt(user["id"])
        token_hash = hash_token(jwt_token)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=Config.SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        create_session(user["id"], token_hash, expires_at)
        resp = make_response(jsonify({"require_2fa_reset": True, "message": "2FA reset required."}))
        resp.set_cookie("snowdrive_token", jwt_token, max_age=Config.SESSION_DAYS * 86400, httponly=True, samesite="Lax", secure=False)
        return resp
    methods = get_user_2fa_methods(user["id"])
    if not methods:
        # No 2FA configured - force setup
        require_totp_reset(user["id"])
        jwt_token = create_jwt(user["id"])
        token_hash = hash_token(jwt_token)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=Config.SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        create_session(user["id"], token_hash, expires_at)
        resp = make_response(jsonify({"require_2fa_reset": True, "message": "2FA setup required."}))
        resp.set_cookie("snowdrive_token", jwt_token, max_age=Config.SESSION_DAYS * 86400, httponly=True, samesite="Lax", secure=False)
        return resp
    available_methods = [{"id": m["id"], "type": m["method_type"], "name": m["method_name"]} for m in methods]
    flask_session["pending_login_user_id"] = user["id"]
    return jsonify({"require_2fa": True, "methods": available_methods})


@auth_bp.route("/api/auth/login-2fa", methods=["POST"])
def login_2fa():
    user_id = flask_session.get("pending_login_user_id")
    if not user_id:
        return jsonify({"error": "Login session expired."}), 400
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 400
    data = request.get_json() or {}
    method_type = (data.get("method_type") or "").strip()
    method_id = data.get("method_id")
    code = (data.get("code") or "").strip()
    credential_data = data.get("credential")

    # TOTP
    if method_type == "totp":
        if not code or not method_id:
            return jsonify({"error": "TOTP code required."}), 400
        method = get_2fa_method(method_id)
        if not method or method["user_id"] != user["id"]:
            return jsonify({"error": "Invalid 2FA method."}), 400
        totp = pyotp.TOTP(method["totp_secret"])
        if totp.verify(code, valid_window=1):
            update_2fa_last_used(method_id)
            return _complete_login(user)
        return jsonify({"error": "Invalid TOTP code."}), 401

    # WebAuthn
    if method_type == "webauthn":
        if not credential_data:
            return jsonify({"error": "WebAuthn credential required."}), 400
        try:
            from webauthn import verify_authentication_response
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
        challenge = flask_session.get("webauthn_auth_challenge", "")
        rp_id = get_rp_id()
        origin = get_origin()
        cred_id = credential_data.get("id") or credential_data.get("rawId")
        if not cred_id:
            return jsonify({"error": "Invalid credential."}), 400
        stored = get_webauthn_credential(cred_id)
        if not stored or stored["user_id"] != user["id"]:
            return jsonify({"error": "Unknown credential."}), 400
        try:
            verification = verify_authentication_response(
                credential=credential_data,
                expected_challenge=challenge.encode() if challenge else b"",
                expected_rp_id=rp_id, expected_origin=origin,
                credential_public_key=stored["credential_public_key"],
                credential_current_sign_count=stored["sign_count"],
            )
        except Exception as e:
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 401
        update_webauthn_sign_count(stored["id"], verification.new_sign_count)
        flask_session.pop("webauthn_auth_challenge", None)
        return _complete_login(user)

    return jsonify({"error": "Invalid 2FA method."}), 400


@auth_bp.route("/api/auth/webauthn-auth-begin", methods=["POST"])
def webauthn_auth_begin():
    user_id = flask_session.get("pending_login_user_id")
    if not user_id:
        return jsonify({"error": "Login session expired."}), 400
    try:
        from webauthn import generate_authentication_options
        from webauthn.helpers import options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    except ImportError:
        return jsonify({"error": "WebAuthn not available."}), 500
    methods = get_user_2fa_methods(user_id)
    webauthn_methods = [m for m in methods if m["method_type"] == "webauthn"]
    if not webauthn_methods:
        return jsonify({"error": "No WebAuthn methods."}), 400
    challenge = secrets.token_hex(32)
    flask_session["webauthn_auth_challenge"] = challenge
    rp_id = get_rp_id()
    allow_credentials = [PublicKeyCredentialDescriptor(id=b64_to_bytes(m["credential_id"])) for m in webauthn_methods]
    options = generate_authentication_options(rp_id=rp_id, challenge=challenge.encode(), allow_credentials=allow_credentials)
    # options_to_json expects credential.type to be an Enum-like with a .value attribute
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


def _complete_login(user: dict):
    jwt_token = create_jwt(user["id"])
    token_hash = hash_token(jwt_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=Config.SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    create_session(user["id"], token_hash, expires_at)
    flask_session.pop("pending_login_user_id", None)
    flask_session.pop("webauthn_auth_challenge", None)
    resp = make_response(jsonify({"success": True, "message": "Login successful."}))
    resp.set_cookie("snowdrive_token", jwt_token, max_age=Config.SESSION_DAYS * 86400, httponly=True, samesite="Lax", secure=False)
    return resp


# ─── API: Logout ────────────────────────────────────────────────────

@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    token_hash = hash_token(g.session_token)
    delete_session(token_hash)
    resp = make_response(jsonify({"success": True}))
    resp.delete_cookie("snowdrive_token")
    return resp


# ─── API: Reset 2FA ─────────────────────────────────────────────────

@auth_bp.route("/api/auth/reset-2fa", methods=["POST"])
@login_required
def reset_2fa():
    user = g.current_user
    if not user["totp_required_reset"]:
        return jsonify({"error": "2FA reset not required."}), 400
    data = request.get_json() or {}
    action = data.get("action", "")

    if action == "totp_generate":
        secret = pyotp.random_base32()
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=Config.TOTP_ISSUER)
        qr_img = qrcode.make(totp_uri)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        resp = make_response(jsonify({"success": True, "secret": secret, "qr_code": f"data:image/png;base64,{qr_b64}"}))
        resp.set_cookie("snowdrive_pending_totp", secret, max_age=600, httponly=True, samesite="Lax", secure=False)
        return resp

    elif action == "totp_verify":
        code = (data.get("code") or "").strip()
        pending_secret = request.cookies.get("snowdrive_pending_totp")
        if not pending_secret:
            return jsonify({"error": "No pending TOTP."}), 400
        totp = pyotp.TOTP(pending_secret)
        if not totp.verify(code, valid_window=1):
            return jsonify({"error": "Invalid code."}), 400
        add_totp_method(user["id"], pending_secret)
        clear_totp_reset(user["id"])
        resp = make_response(jsonify({"success": True, "message": "2FA set up."}))
        resp.delete_cookie("snowdrive_pending_totp")
        return resp

    elif action == "webauthn_register_begin":
        try:
            from webauthn import generate_registration_options
            from webauthn.helpers import options_to_json
            from webauthn.helpers.structs import (
                AuthenticatorSelectionCriteria, AuthenticatorAttachment,
                ResidentKeyRequirement, UserVerificationRequirement,
            )
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
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
        return jsonify({"success": True, "options": json.loads(options_to_json(options)), "challenge": challenge, "rp_id": rp_id})

    elif action == "webauthn_register_verify":
        try:
            from webauthn import verify_registration_response
        except ImportError:
            return jsonify({"error": "WebAuthn not available."}), 500
        credential_data = data.get("credential", {})
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
        add_webauthn_method(user["id"], bytes_to_b64url(verification.credential_id),
                           verification.credential_public_key,
                           verification.sign_count, rp_id,
                           "Windows Hello / Passkey")
        clear_totp_reset(user["id"])
        flask_session.pop("webauthn_reg_challenge", None)
        flask_session.pop("webauthn_reg_user_id", None)
        return jsonify({"success": True, "message": "2FA set up via Passkey."})

    return jsonify({"error": "Invalid action."}), 400
