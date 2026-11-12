"""Flask application factory for the restaurant POS.

Credentials are read from the environment, then from /etc/pos/pos.env
(readable by the posapp system user), then from the legacy root-only file.
Passwords are never written into source code.
"""
import hmac
import os
import secrets
from urllib.parse import quote

from dotenv import dotenv_values
from flask import Flask, abort, render_template, request, session
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
migrate = Migrate()

LEGACY_CREDENTIALS = "/root/project-db-credentials.env"
APP_CREDENTIALS = "/etc/pos/pos.env"
REQUIRED_DATABASE = "retail_pos_db"

# Requests that do not change state, so they need no form token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _reject_unexpected_database(dbapi_connection, _connection_record):
    """Stop the POS app if a connection lands in another project database."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT current_database()")
        current = cursor.fetchone()[0]
    finally:
        cursor.close()
    if current != REQUIRED_DATABASE:
        raise RuntimeError("Refusing unexpected database: " + str(current))


def _configured_database():
    user = os.getenv("POS_DB_USER", "pos_app")
    host = os.getenv("POS_DB_HOST", "127.0.0.1")
    port = os.getenv("POS_DB_PORT", "5432")
    name = os.getenv("POS_DB_NAME", REQUIRED_DATABASE)
    password = os.getenv("POS_DB_PASSWORD")
    if name != REQUIRED_DATABASE:
        raise RuntimeError("POS_DB_NAME must be retail_pos_db")
    if password:
        return user, password, host, port, name
    for path in (APP_CREDENTIALS, LEGACY_CREDENTIALS):
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            continue
        values = dotenv_values(path)
        password = values.get("POS_DB_PASSWORD")
        if not password:
            continue
        user = values.get("POS_DB_USER", user)
        host = values.get("POS_DB_HOST", host)
        port = str(values.get("POS_DB_PORT", port))
        name = values.get("POS_DB_NAME", name)
        if name != REQUIRED_DATABASE:
            raise RuntimeError("Refusing non-POS database name in " + path)
        return user, password, host, port, name
    raise RuntimeError(
        "POS_DB_PASSWORD is missing. Configure /etc/pos/pos.env "
        "or the legacy credentials file before starting the app."
    )


def database_uri():
    user, password, host, port, name = _configured_database()
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@{host}:{port}/{name}"
    )


def load_credentials_into_environment():
    """Copy names from an env file into os.environ without overwriting real values."""
    for path in (APP_CREDENTIALS, LEGACY_CREDENTIALS):
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            continue
        for key, value in dotenv_values(path).items():
            if value:
                os.environ.setdefault(key, value)


def _secret_key(app):
    """Stable session key. Read from the environment, else persisted 0600 in instance/."""
    configured = os.getenv("POS_SECRET_KEY")
    if configured:
        return configured
    os.makedirs(app.instance_path, exist_ok=True)
    path = os.path.join(app.instance_path, "secret_key")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            stored = handle.read().strip()
        if stored:
            return stored
    key = secrets.token_hex(32)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(key)
    return key


def csrf_token():
    """One token per browser session, regenerated only when missing."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def create_app():
    load_credentials_into_environment()
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = _secret_key(app)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("POS_SESSION_COOKIE_SECURE", "1") == "1"
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 12
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["PAGE_SIZE"] = 25
    # Set POS_SIGNUP_ENABLED=0 to close public registration on a shared server.
    app.config["SIGNUP_ENABLED"] = os.getenv("POS_SIGNUP_ENABLED", "1") == "1"

    # Nginx terminates TLS; trust its forwarded protocol and host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    db.init_app(app)
    from app import models  # noqa: F401 - register every model on metadata
    migrate.init_app(app, db)
    with app.app_context():
        if not event.contains(db.engine, "connect", _reject_unexpected_database):
            event.listen(db.engine, "connect", _reject_unexpected_database)

    _register_template_helpers(app)
    _register_request_hooks(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    return app


def _register_template_helpers(app):
    from app.filters import register_filters
    from app.security import branch_options, can, context, has_permission

    register_filters(app)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["current_context"] = context
    app.jinja_env.globals["can"] = can
    app.jinja_env.globals["has_permission"] = has_permission
    app.jinja_env.globals["branch_options"] = branch_options


def _register_request_hooks(app):
    from app.security import load_context

    @app.before_request
    def _enforce_csrf():
        """Reject state changes without the session form token."""
        if request.method in SAFE_METHODS:
            return None
        expected = session.get("_csrf")
        supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="Your form session expired. Reload the page and try again.")
        return None

    @app.before_request
    def _attach_context():
        load_context()

    @app.after_request
    def _no_store_private_pages(response):
        """Do not let a shared browser cache another user's till pages."""
        if response.status_code == 200 and response.content_type.startswith("text/html"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_blueprints(app):
    from app.blueprints import (
        admin,
        auth,
        catalog,
        dashboard,
        insights,
        inventory,
        kitchen,
        orders,
        platform,
        pos,
        reports,
        restaurants,
        suppliers,
    )

    for module in (
        auth,
        dashboard,
        pos,
        orders,
        kitchen,
        catalog,
        inventory,
        reports,
        insights,
        restaurants,
        suppliers,
        admin,
        platform,
    ):
        app.register_blueprint(module.bp)


def _register_error_handlers(app):
    def render_error(code, heading, message):
        return render_template("errors/error.html", code=code, heading=heading, message=message), code

    @app.errorhandler(400)
    def bad_request(error):
        return render_error(
            400, "Bad request", getattr(error, "description", "The request was not understood.")
        )

    @app.errorhandler(403)
    def forbidden(error):
        return render_error(
            403, "Not allowed", getattr(error, "description", "You do not have access to this page.")
        )

    @app.errorhandler(404)
    def not_found(error):
        return render_error(404, "Page not found", "That page does not exist.")

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled error: %s", error)
        return render_error(500, "Something went wrong", "The server could not complete that request.")
