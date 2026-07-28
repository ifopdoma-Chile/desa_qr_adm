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
    MAX_SLUG_LENGTH = 50

    # QR Generation
    QR_DEFAULT_SIZE = 400
    QR_LOGO_MAX_SIZE = 120
    QR_TEMP_TOKEN_TTL = 300  # seconds

    # Limits
    QR_MAX_PER_USER = 500
    RATE_LIMIT_DEFAULT = '200/hour'
    RATE_LIMIT_SCAN = '60/minute'
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')

    # Geolocation cache
    GEO_CACHE_TTL = 86400  # 24h

    # Pagination
    PER_PAGE = 25


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
