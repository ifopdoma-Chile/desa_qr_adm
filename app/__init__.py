import os
from flask import Flask
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


def create_app(config_name='default'):
    app = Flask(__name__)

    from config import config as config_dict
    app.config.from_object(config_dict[config_name])

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.wsgi_app = ReverseProxyPrefix(app.wsgi_app)

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicie sesion para acceder.'
    login_manager.login_message_category = 'warning'
    migrate.init_app(app, db)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Template globals
    @app.context_processor
    def inject_globals():
        return dict(
            app_name=app.config.get('APP_NAME', 'QR Manager'),
            app_base_url=app.config.get('APP_BASE_URL', ''),
            current_year=__import__('datetime').datetime.now().year,
        )

    # Register blueprints
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.qr import qr_bp
    from app.api import api_bp
    from app.redirect import redirect_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(qr_bp, url_prefix='/qr')
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(redirect_bp)

    # Create tables
    with app.app_context():
        from app import models
        db.create_all()

    return app
