import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://qr_adm:qr_adm_pass@localhost:5432/qr_adm'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'pool_recycle': 3600,
    }

    # App
    APP_NAME = 'IFOP QR Manager'
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://qr.ifop.cl')
    APP_PUBLIC_BASE = os.environ.get('APP_PUBLIC_BASE', 'https://sapogis.ifop.cl/qr')
    VERSION = '2.1.0'
    MAX_SLUG_LENGTH = 50

    # QR Generation
    QR_DEFAULT_SIZE = 400
    QR_LOGO_MAX_SIZE = 120
    QR_TEMP_TOKEN_TTL = 300  # seconds

    # Limits
    QR_MAX_PER_USER = 500
    RATE_LIMIT_DEFAULT = '200/hour'
    RATE_LIMIT_SCAN = '60/minute'
    RATE_LIMIT_LOGIN = '10/minute'      # intentos POST de login
    RATE_LIMIT_LOGIN_GET = '60/minute'  # ver la pagina de login
    RATE_LIMIT_TEMP_TOKEN = '30/minute'
    RATE_LIMIT_DOWNLOAD = '60/minute'
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')

    # Cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True

    # Geolocation cache
    GEO_CACHE_TTL = 86400  # 24h

    # Pagination
    PER_PAGE = 25

    # Mail (SMTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'ifopdoma@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'IFOP QR Manager <ifopdoma@gmail.com>')

    # Google OAuth (mismo esquema que modelacion_v2)
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    # Approval (usuarios nuevos requieren aprobacion del admin)
    NEW_USERS_NEED_APPROVAL = os.environ.get('NEW_USERS_NEED_APPROVAL', 'true').lower() == 'true'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    RATE_LIMIT_DEFAULT = '500/hour'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
