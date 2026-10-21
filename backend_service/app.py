"""Flask Application Entrypoint for AI Pothole Detection Municipal Service.

Configures:
  - Cross-Origin Resource Sharing (CORS) for external dashboards and edge clients.
  - Image snapshot serving under `/uploads/<filename>`.
  - Blueprinted REST API endpoints under `/api/v1`.
  - Optional static hosting for the municipal web dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend_service.config import config
from backend_service.routes import api_bp

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("backend_service.app")


def create_app() -> Flask:
    """Application factory initializing Flask, CORS, routes, and static assets."""
    app = Flask(__name__)

    # Enable CORS for cross-origin dashboard clients
    CORS(
        app,
        resources={
            r"/api/*": {"origins": "*"},
            r"/uploads/*": {"origins": "*"},
            r"/*": {"origins": "*"},
        },
    )

    # Register API blueprint
    app.register_blueprint(api_bp)

    # Static file serving for pothole snapshot images
    @app.route("/uploads/<path:filename>", methods=["GET"])
    def serve_upload(filename: str):
        """Serves recorded snapshot images from the uploads directory."""
        return send_from_directory(config.UPLOAD_FOLDER, filename)

    # Static file serving for web dashboard if accessed through backend port
    web_dashboard_dir = Path(__file__).resolve().parent.parent / "web_dashboard"

    @app.route("/", methods=["GET"])
    @app.route("/dashboard", methods=["GET"])
    def serve_dashboard():
        """Serves municipal web dashboard index.html."""
        if (web_dashboard_dir / "index.html").exists():
            return send_from_directory(web_dashboard_dir, "index.html")
        return jsonify(
            {
                "service": "AI Pothole Detection Backend Service",
                "version": "1.0.0",
                "api_docs": "/api/v1/potholes",
            }
        )

    @app.route("/<path:filename>", methods=["GET"])
    def serve_dashboard_asset(filename: str):
        """Serves dashboard assets (map.js, filters.js, mock_data.json) if requested."""
        if (web_dashboard_dir / filename).exists():
            return send_from_directory(web_dashboard_dir, filename)
        return jsonify({"error": f"Asset '{filename}' not found."}), 404

    # Standard JSON error handlers
    @app.errorhandler(400)
    def bad_request(error: Any):
        return jsonify({"error": "Bad request", "details": str(error)}), 400

    @app.errorhandler(404)
    def not_found(error: Any):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(error: Any):
        logger.error("Internal Server Error: %s", error)
        return jsonify({"error": "Internal server error"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    logger.info(
        "Starting AI Pothole Detection Backend on http://%s:%d",
        config.HOST,
        config.PORT,
    )
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
