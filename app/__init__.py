import os
import re
import secrets
from datetime import datetime
from flask import Flask, request, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=['200/hour'],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URL', 'memory://'),
)


class ReverseProxyPrefix:
    def __init__(self, app, header='X-Forwarded-Prefix'):
        self.app = app
        self.header = header

    def __call__(self, environ, start_response):
        prefix = environ.get(f'HTTP_{self.header.upper().replace("-", "_")}')
        if prefix:
            environ['SCRIPT_NAME'] = prefix.rstrip('/')
        return self.app(environ, start_response)


# ─── CSRF (sin dependencias externas) ───

CSRF_FIELD = '_csrf_token'
_CSRF_FORM_RE = re.compile(r'(<form[^>]*method=["\']POST["\'][^>]*>)', re.IGNORECASE)
_CSRF_INPUT = '<input type="hidden" name="%s" value="%s">'


def generate_csrf_token():
    """Token CSRF estable por sesion."""
    if CSRF_FIELD not in session:
        session[CSRF_FIELD] = secrets.token_urlsafe(32)
    return session[CSRF_FIELD]


def validate_csrf():
    """Valida el token CSRF en toda mutacion que no sea API (Bearer)."""
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return
    if request.path.startswith('/api/v1'):
        return  # API autenticada por Bearer token
    if request.path.startswith('/qr/temp-token'):
        return  # requiere Authorization header propio
    token = request.form.get(CSRF_FIELD) or request.headers.get('X-CSRF-Token')
    expected = session.get(CSRF_FIELD)
    if not expected or not token or not secrets.compare_digest(token, expected):
        from flask import abort, jsonify
        if request.path.startswith('/api/'):
            return
        abort(400, description='Token CSRF invalido o faltante. Recarga la pagina e intenta de nuevo.')


def inject_csrf(response):
    """Inyecta el campo CSRF en todos los formularios POST de respuestas HTML."""
    if response.content_type != 'text/html; charset=utf-8' and not (
        response.content_type or '').startswith('text/html'):
        return response
    token = generate_csrf_token()
    field = _CSRF_INPUT % (CSRF_FIELD, token)

    def _replace(match):
        form_tag = match.group(1)
        # Evitar doble inyeccion si el form ya trae el campo
        tail = response.get_data(as_text=True)[match.end():match.end() + 300]
        if CSRF_FIELD in tail:
            return form_tag
        return form_tag + field

    try:
        body = response.get_data(as_text=True)
        new_body, n = _CSRF_FORM_RE.subn(_replace, body)
        if n:
            response.set_data(new_body)
    except Exception:
        pass
    return response


def create_app(config_name='default'):
    app = Flask(__name__)

    from config import config as config_dict
    app.config.from_object(config_dict[config_name])

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.wsgi_app = ReverseProxyPrefix(app.wsgi_app)

    # Seguridad de cookies de sesion
    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SECURE', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    app.config.setdefault('REMEMBER_COOKIE_SECURE', True)
    app.config.setdefault('REMEMBER_COOKIE_HTTPONLY', True)

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicie sesion para acceder.'
    login_manager.login_message_category = 'warning'
    migrate.init_app(app, db)
    limiter.init_app(app)

    # CSRF: validacion global + inyeccion en formularios
    app.before_request(validate_csrf)
    app.after_request(inject_csrf)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    @app.template_filter('localtime')
    def localtime_filter(dt, fmt='%d/%m/%Y %H:%M'):
        """Formatea datetime en hora local de Chile (America/Santiago)."""
        if dt is None:
            return ''
        try:
            if getattr(dt, 'tzinfo', None) is not None:
                dt = dt.astimezone()
            return dt.strftime(fmt)
        except Exception:
            return str(dt)

    # Template globals
    @app.context_processor
    def inject_globals():
        pending = 0
        try:
            from flask_login import current_user
            if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
                from app.models import User
                pending = User.query.filter_by(is_approved=False).count()
        except Exception:
            pending = 0
        return dict(
            app_name=app.config.get('APP_NAME', 'QR Manager'),
            app_base_url=app.config.get('APP_BASE_URL', ''),
            app_version=app.config.get('VERSION', '2.0.0'),
            current_year=datetime.now().year,
            pending_users_count=pending,
            csrf_token=generate_csrf_token,
        )

    # Register blueprints
    from app.auth import auth_bp, init_oauth
    from app.admin import admin_bp
    from app.qr import qr_bp
    from app.api import api_bp
    from app.redirect import redirect_bp

    # Google OAuth (si hay credenciales en env)
    init_oauth(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    # qr_bp se registra en raiz porque nginx /qr/ quita el prefijo al proxear
    # (url_for genera /qr/... via X-Forwarded-Prefix/SCRIPT_NAME)
    app.register_blueprint(qr_bp)
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(redirect_bp)

    # Create tables (nuevas tablas: temp_tokens, audit_logs)
    with app.app_context():
        from app import models
        db.create_all()

    return app
