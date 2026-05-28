#!/usr/bin/env python3
"""SnowDrive CLI - Administrative tools.

Usage:
    docker exec -it snowdrive reset-2fa <username> <password>
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import init_db, get_user_by_username, require_totp_reset
from app.utils import verify_password


def cmd_reset_2fa():
    if len(sys.argv) < 4:
        print("Usage: docker exec -it snowdrive reset-2fa <username> <password>")
        print("       python -m app.cli reset-2fa <username> <password>")
        sys.exit(1)

    username = sys.argv[2]
    password = sys.argv[3]

    init_db()
    user = get_user_by_username(username)
    if not user:
        print(f"Error: User '{username}' not found.")
        sys.exit(1)

    if not verify_password(password, user["password_hash"]):
        print("Error: Incorrect password.")
        sys.exit(1)

    require_totp_reset(user["id"])
    print(f"2FA has been reset for user '{username}'.")
    print("The user will be prompted to set up 2FA on next login.")


def main():
    if len(sys.argv) < 2:
        print("SnowDrive CLI")
        print("Usage: docker exec -it snowdrive reset-2fa <username> <password>")
        sys.exit(0)

    command = sys.argv[1].lower()
    if command == "reset-2fa":
        cmd_reset_2fa()
    else:
        print(f"Unknown command: {command}")
        print("Usage: docker exec -it snowdrive reset-2fa <username> <password>")
        sys.exit(1)


if __name__ == "__main__":
    main()
