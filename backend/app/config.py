import os


def _database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        # Relative SQLite paths resolve to the app's instance folder (backend/instance/).
        return "sqlite:///barbershop.db"
    # Render and Heroku hand out postgres:// URLs; SQLAlchemy needs the driver name.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # How long a guest's unpaid deposit booking holds its slot.
    BOOKING_HOLD_MINUTES = 15
    # How long a barber invite link stays valid.
    INVITE_EXPIRY_DAYS = 7

    # Links in emails sent outside a web request (reminders) start with this.
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000").rstrip("/")

    # Email. MAIL_BACKEND: "smtp" sends for real; "file" saves each email as an
    # .eml file in backend/instance/outbox/ (the default when SMTP_HOST is unset);
    # "console" prints it; "memory" keeps it in a list (tests).
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND") or ("smtp" if SMTP_HOST else "file")
    MAIL_FROM = os.environ.get("MAIL_FROM", "Barbershop Appointments <no-reply@localhost>")

    # How often the reminders worker looks for appointments to remind about.
    REMINDER_CHECK_MINUTES = 5

    # The interface is English for now; emails use each shop's language.
    BABEL_DEFAULT_LOCALE = "en"

    # Cookies are not sent along when another site links or posts here.
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True

    # Limits on login, sign-up and booking attempts, counted per visitor IP.
    # In-memory counters are per process; fine for one web instance.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Production runs behind Render's proxy over HTTPS (see ProductionConfig).
    TRUST_PROXY = False
    HSTS = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    # CI also runs the tests on PostgreSQL by setting TEST_DATABASE_URL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    WTF_CSRF_ENABLED = False
    MAIL_BACKEND = "memory"


class ProductionConfig(Config):
    DEBUG = False  # even though .flaskenv sets FLASK_DEBUG=1 for local flask commands
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    # Without SMTP, emails go to the log: the host's disk is wiped on each deploy.
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND") or ("smtp" if Config.SMTP_HOST else "console")
    TRUST_PROXY = _env_bool("TRUST_PROXY", True)
    HSTS = True

    @classmethod
    def validate(cls):
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY must be set in production")
        if cls.MAIL_BACKEND == "smtp" and not cls.SMTP_HOST:
            raise RuntimeError("SMTP_HOST must be set when MAIL_BACKEND is smtp")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
