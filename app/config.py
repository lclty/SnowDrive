"""Application configuration."""

import os
import secrets


class Config:
    """Base configuration."""

    # Secret key for JWT signing
    SECRET_KEY = os.environ.get("SNOWDRIVE_SECRET_KEY", secrets.token_hex(32))

    # Session lifetime in days
    SESSION_DAYS = int(os.environ.get("SNOWDRIVE_SESSION_DAYS", "7"))

    # Paths
    DATA_DIR = "/data"
    USERDATA_DIR = "/userdata"
    DB_PATH = os.path.join(USERDATA_DIR, "snowdrive.db")
    AVATAR_DIR = os.path.join(USERDATA_DIR, "avatars")

    # Upload limits (unset = no enforced limit)
    MAX_CONTENT_LENGTH = None

    # Allowed archive formats
    ARCHIVE_FORMATS = ["zip"]

    # TOTP settings
    TOTP_ISSUER = "SnowDrive"

    # WebAuthn settings
    WEBAUTHN_RP_NAME = "SnowDrive"
    # RP_ID is derived from request host at runtime
