"""
app/__init__.py — iCal Flask Application Factory
"""
import os
from flask import Flask
from flask_cors import CORS


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # ── Config ──────────────────────────────────────
    app.config.update(
        SECRET_KEY        = os.getenv("JWT_SECRET", "ical-secret-change-in-production"),
        DATABASE_URL      = os.getenv("DATABASE_URL", "postgresql://localhost/ical"),
        OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", ""),
        FOOD_DB_PATH      = os.getenv("FOOD_DB_PATH", "food_data.json"),
        MAX_CONTENT_LENGTH= 10 * 1024 * 1024,  # 10 MB
    )

    # ── CORS ─────────────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Init DB on startup ────────────────────────────
    from app.services.database import init_db
    with app.app_context():
        init_db()

    # ── Register blueprints ───────────────────────────
    from app.routes.auth    import auth_bp
    from app.routes.meals   import meals_bp
    from app.routes.social  import social_bp
    from app.routes.pages   import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp,   url_prefix="/api")
    app.register_blueprint(meals_bp,  url_prefix="/api")
    app.register_blueprint(social_bp, url_prefix="/api")

    # ── Health ────────────────────────────────────────
    @app.get("/api/health")
    def health():
        from app.services.database import get_db
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return {"status": "healthy", "db": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 503

    @app.get("/api/")
    def root():
        return {"status": "ok", "service": "iCal API", "version": "4.0.0"}

    return app
