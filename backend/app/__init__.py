import os
from pathlib import Path

from flask import Flask

from .config import CONFIGS
from .extensions import csrf, db, login_manager, migrate
from .timeutils import utcnow

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


def create_app(env: str | None = None) -> Flask:
    env = env or os.environ.get("APP_ENV", "development")
    config = CONFIGS[env]
    if hasattr(config, "validate"):
        config.validate()

    app = Flask(
        __name__,
        instance_path=str(BACKEND_DIR / "instance"),
        template_folder=str(FRONTEND_DIR / "templates"),
        static_folder=str(FRONTEND_DIR / "static"),
    )
    app.config.from_object(config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(BACKEND_DIR / "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so they are registered with SQLAlchemy and Alembic.
    from . import models  # noqa: F401
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.booking import bp as booking_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.shops import bp as shops_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(shops_bp, url_prefix="/shops")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    # Public booking pages live at /s/<shop-slug>.
    app.register_blueprint(booking_bp, url_prefix="/s")

    @app.context_processor
    def inject_globals():
        return {"now_year": utcnow().year}

    return app
