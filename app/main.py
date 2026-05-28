"""SnowDrive - Main Application Entry Point (Demo Mode)."""

from flask import Flask
import os
from app.config import Config


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

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
        return {"status": "ok", "app": "SnowDrive", "demo_mode": Config.DEMO_MODE}

    # Demo mode information
    @app.route("/api/demo-info")
    def demo_info():
        return {
            "is_demo": Config.DEMO_MODE,
            "message": Config.DEMO_BANNER_MESSAGE,
        }

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("SNOWDRIVE_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8080, debug=debug)
