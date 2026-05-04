from __future__ import annotations

from flask import Flask

from .config import Config
from .security import csrf_token, validate_csrf, current_user, mask_email, mask_phone
from .election import status as election_status


def create_app() -> Flask:
    Config.ensure_dirs()
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.before_request
    def _csrf_guard() -> None:
        validate_csrf()


    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.context_processor
    def _globals():
        return {
            "csrf_token": csrf_token,
            "current_user": current_user(),
            "election_status": election_status(),
            "app_name": Config.APP_NAME,
            "mask_email": mask_email,
            "mask_phone": mask_phone,
            "assistant_enabled": True,
        }

    from .routes.public import public_bp
    from .routes.auth import auth_bp
    from .routes.voter import voter_bp
    from .routes.candidate import candidate_bp
    from .routes.admin import admin_bp
    from .routes.assistant import assistant_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(voter_bp, url_prefix="/voter")
    app.register_blueprint(candidate_bp, url_prefix="/candidate")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(assistant_bp)
    return app
