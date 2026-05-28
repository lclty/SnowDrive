"""SnowDrive - Main Application Entry Point."""

import os
import sys
import atexit

from flask import Flask

from app.config import Config
from app.models import init_db, cleanup_expired_sessions


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    # Flask session requires secret_key to be set
    app.secret_key = Config.SECRET_KEY

    # Ensure userdata directories exist
    os.makedirs(Config.USERDATA_DIR, exist_ok=True)
    os.makedirs(Config.AVATAR_DIR, exist_ok=True)
    os.makedirs(Config.DATA_DIR, exist_ok=True)

    # Initialize database
    init_db()

    # Import and register blueprints
    from app.auth import auth_bp
    from app.files import files_bp
    from app.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(settings_bp)

    # Health check endpoint
    @app.route("/api/health")
    def health_check():
        return {"status": "ok", "app": "SnowDrive"}

    # Cleanup expired sessions periodically
    cleanup_expired_sessions()

    return app


app = create_app()

if __name__ == "__main__":
    # For development only; production uses the Dockerfile CMD
    debug = os.environ.get("SNOWDRIVE_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8080, debug=debug)
