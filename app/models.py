import uuid
import hashlib
import secrets
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import JSON as JSONType
from app import db


# ─── Association table: QR <-> Tag ───
qr_tags = db.Table(
    'qr_tags',
    db.Column('qr_id', db.Integer, db.ForeignKey('qr_codes.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
)


# ─── User ───
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    ROLE_ADMIN = 'admin'
    ROLE_EDITOR = 'editor'
    ROLE_VIEWER = 'viewer'
    ROLES = [(ROLE_ADMIN, 'Administrador'), (ROLE_EDITOR, 'Editor'), (ROLE_VIEWER, 'Solo lectura')]

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(200))
    role = db.Column(db.String(20), nullable=False, default=ROLE_EDITOR)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    qr_codes = db.relationship('QRCode', backref='owner', lazy='dynamic',
                               cascade='all, delete-orphan')
    api_keys = db.relationship('ApiKey', backref='user', lazy='dynamic',
                               cascade='all, delete-orphan')

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def can_edit(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_EDITOR)

    @property
    def qr_count(self):
        return self.qr_codes.count()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


# ─── Domain (multi-dominio) ───
class Domain(db.Model):
    __tablename__ = 'domains'

    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(253), unique=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Domain {self.domain}>'


# ─── QR Code ───
class QRCode(db.Model):
    __tablename__ = 'qr_codes'

    TYPE_URL = 'url'
    TYPE_WIFI = 'wifi'
    TYPE_VCARD = 'vcard'
    TYPE_MAP = 'map'
    TYPE_TEXT = 'text'
    TYPE_EMAIL = 'email'
    TYPE_PHONE = 'phone'
    TYPE_SMS = 'sms'
    TYPE_JSON = 'json'

    QR_TYPES = [
        (TYPE_URL, 'Enlace URL'),
        (TYPE_WIFI, 'WiFi'),
        (TYPE_VCARD, 'Contacto (vCard)'),
        (TYPE_MAP, 'Ubicacion / Mapa'),
        (TYPE_TEXT, 'Texto libre'),
        (TYPE_EMAIL, 'Correo electronico'),
        (TYPE_PHONE, 'Telefono'),
        (TYPE_SMS, 'SMS'),
        (TYPE_JSON, 'JSON personalizado'),
    ]

    STYLE_SQUARE = 'square'
    STYLE_GAPPED = 'gapped-square'
    STYLE_CIRCLE = 'circle'
    STYLE_ROUNDED = 'rounded'
    STYLE_VERTICAL = 'vertical-bars'
    STYLE_HORIZONTAL = 'horizontal-bars'
    STYLE_DIAMOND = 'diamond'
    STYLE_STAR = 'star'
    STYLE_CROSS = 'cross'
    STYLE_DROP = 'drop'
    STYLE_TRIANGLE = 'triangle'
    STYLE_CLOVER = 'clover'
    STYLE_SHIELD = 'shield'
    STYLE_CLOUD = 'cloud'
    STYLE_FISH = 'fish'

    QR_STYLES = [
        (STYLE_SQUARE, 'Cuadrados'),
        (STYLE_GAPPED, 'Cuadrados separados'),
        (STYLE_CIRCLE, 'Circulos'),
        (STYLE_ROUNDED, 'Esquinas redondeadas'),
        (STYLE_VERTICAL, 'Barras verticales'),
        (STYLE_HORIZONTAL, 'Barras horizontales'),
        (STYLE_DIAMOND, 'Diamante'),
        (STYLE_STAR, 'Estrella'),
        (STYLE_CROSS, 'Cruz'),
        (STYLE_DROP, 'Gota'),
        (STYLE_TRIANGLE, 'Triangulo'),
        (STYLE_CLOVER, 'Trebol'),
        (STYLE_SHIELD, 'Escudo'),
        (STYLE_CLOUD, 'Nube'),
        (STYLE_FISH, 'Pez'),
    ]

    OUTER_SQUARE = 'square'
    OUTER_CIRCLE = 'circle'
    OUTER_ROUNDED = 'rounded-rect'
    OUTER_HEART = 'heart'
    OUTER_CLOUD = 'cloud'
    OUTER_FISH = 'fish'
    OUTER_DIAMOND = 'diamond'
    OUTER_SHIELD = 'shield'
    OUTER_DROP = 'drop'
    OUTER_LEAF = 'leaf'
    OUTER_STAR = 'star'

    QR_OUTER_SHAPES = [
        (OUTER_SQUARE, 'Cuadrado'),
        (OUTER_CIRCLE, 'Circulo'),
        (OUTER_ROUNDED, 'Rectangulo redondeado'),
        (OUTER_HEART, 'Corazon'),
        (OUTER_CLOUD, 'Nube'),
        (OUTER_FISH, 'Pez'),
        (OUTER_DIAMOND, 'Diamante'),
        (OUTER_SHIELD, 'Escudo'),
        (OUTER_DROP, 'Gota'),
        (OUTER_LEAF, 'Hoja'),
        (OUTER_STAR, 'Estrella'),
    ]

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(36), unique=True, nullable=False,
                    default=lambda: str(uuid.uuid4()), index=True)

    # ── Core fields ──
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    qr_type = db.Column(db.String(20), nullable=False, index=True)

    # ── URL / Text content ──
    content_url = db.Column(db.Text)
    content_text = db.Column(db.Text)

    # ── WiFi ──
    wifi_ssid = db.Column(db.String(100))
    wifi_password = db.Column(db.String(100))
    wifi_encryption = db.Column(db.String(20), default='WPA')

    # ── vCard ──
    vcard_name = db.Column(db.String(200))
    vcard_first_name = db.Column(db.String(100))
    vcard_phone = db.Column(db.String(50))
    vcard_email = db.Column(db.String(120))
    vcard_org = db.Column(db.String(200))
    vcard_title = db.Column(db.String(200))
    vcard_url = db.Column(db.Text)

    # ── Map ──
    map_lat = db.Column(db.Float)
    map_lon = db.Column(db.Float)
    map_label = db.Column(db.String(200))

    # ── Email ──
    email_address = db.Column(db.String(120))
    email_subject = db.Column(db.String(200))
    email_body = db.Column(db.Text)

    # ── Phone / SMS ──
    phone_number = db.Column(db.String(50))
    sms_message = db.Column(db.Text)

    # ── Custom JSONB ──
    content_jsonb = db.Column(JSONType, default={})

    # ── QR Styling ──
    qr_style = db.Column(db.String(30), nullable=False, default='square')
    qr_fg_color = db.Column(db.String(7), nullable=False, default='#000000')
    qr_bg_color = db.Column(db.String(7), nullable=False, default='#ffffff')
    qr_outer_shape = db.Column(db.String(30), nullable=False, default='square')

    # ── Status & lifecycle ──
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    max_scans = db.Column(db.Integer)       # None = unlimited
    scan_count = db.Column(db.Integer, default=0, nullable=False)

    # ── Inactive redirect ──
    inactive_redirect_url = db.Column(db.Text, default='')

    # ── Domain ──
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'))
    domain = db.relationship('Domain', backref='qr_codes')

    # ── Ownership ──
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # ── Timestamps ──
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # ── Tags (many-to-many) ──
    tags = db.relationship('Tag', secondary=qr_tags, backref=db.backref('qr_codes', lazy='dynamic'))
    conditional_redirects = db.relationship('ConditionalRedirect', backref='qr_code',
                                            lazy='dynamic', cascade='all, delete-orphan')

    @staticmethod
    def generate_slug(length=8):
        while True:
            slug = secrets.token_urlsafe(length)[:length]
            if not QRCode.query.filter_by(slug=slug).first():
                return slug

    @property
    def is_expired(self):
        if self.expires_at:
            return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)
        if self.max_scans and self.scan_count >= self.max_scans:
            return True
        return False

    @property
    def full_url(self):
        base = self.domain.domain if self.domain else 'qr.ifop.cl'
        return f'https://{base}/{self.slug}'

    @property
    def domain_obj(self):
        return self.domain

    def get_qr_data(self):
        if self.qr_type == self.TYPE_URL:
            return self.content_url
        elif self.qr_type == self.TYPE_WIFI:
            return f'WIFI:T:{self.wifi_encryption};S:{self.wifi_ssid};P:{self.wifi_password};;'
        elif self.qr_type == self.TYPE_VCARD:
            return (
                f'BEGIN:VCARD\nVERSION:3.0\n'
                f'N:{self.vcard_name};{self.vcard_first_name}\n'
                f'FN:{self.vcard_first_name} {self.vcard_name}\n'
                f'ORG:{self.vcard_org or ""}\n'
                f'TITLE:{self.vcard_title or ""}\n'
                f'TEL:{self.vcard_phone or ""}\n'
                f'EMAIL:{self.vcard_email or ""}\n'
                f'URL:{self.vcard_url or ""}\n'
                f'END:VCARD'
            )
        elif self.qr_type == self.TYPE_MAP:
            return f'https://www.google.com/maps?q={self.map_lat},{self.map_lon}'
        elif self.qr_type == self.TYPE_EMAIL:
            return f'MAILTO:{self.email_address}?subject={self.email_subject or ""}&body={self.email_body or ""}'
        elif self.qr_type == self.TYPE_PHONE:
            return f'TEL:{self.phone_number}'
        elif self.qr_type == self.TYPE_SMS:
            return f'SMSTO:{self.phone_number}:{self.sms_message or ""}'
        elif self.qr_type == self.TYPE_JSON:
            import json
            return json.dumps(self.content_jsonb or {}, ensure_ascii=False)
        else:
            return self.content_text or ''

    def soft_delete(self):
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self):
        self.is_deleted = False
        self.is_active = True
        self.deleted_at = None

    def __repr__(self):
        return f'<QRCode {self.slug}: {self.title}>'


# ─── Tag ───
class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    color = db.Column(db.String(7), default='#2c6b9e')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', backref='tags')

    __table_args__ = (
        db.UniqueConstraint('name', 'user_id', name='uq_tag_name_user'),
    )

    def __repr__(self):
        return f'<Tag {self.name}>'


# ─── Conditional Redirect ───
class ConditionalRedirect(db.Model):
    __tablename__ = 'conditional_redirects'

    id = db.Column(db.Integer, primary_key=True)
    qr_id = db.Column(db.Integer, db.ForeignKey('qr_codes.id', ondelete='CASCADE'), nullable=False)
    device_type = db.Column(db.String(20))       # mobile, desktop, tablet
    user_agent_pattern = db.Column(db.String(200))  # regex-like pattern
    target_url = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<ConditionalRedirect {self.device_type} -> {self.target_url}>'


# ─── Scan Log ───
class ScanLog(db.Model):
    __tablename__ = 'scan_logs'

    id = db.Column(db.Integer, primary_key=True)
    qr_id = db.Column(db.Integer, db.ForeignKey('qr_codes.id', ondelete='CASCADE'), nullable=False, index=True)
    scanned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Network
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)

    # Parsed device info
    device_type = db.Column(db.String(20))     # mobile, desktop, tablet
    browser = db.Column(db.String(50))
    os_name = db.Column(db.String(50))

    # Geolocation (cached)
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))

    # Proxy detection
    is_proxy = db.Column(db.Boolean, default=False)
    proxy_type = db.Column(db.String(50))  # icloud_private_relay, cloudflare, etc.

    # Response info
    redirect_url = db.Column(db.Text)
    hit_conditional = db.Column(db.Boolean, default=False)

    qr_code = db.relationship('QRCode', backref=db.backref('scans', lazy='dynamic'))

    def __repr__(self):
        return f'<ScanLog qr={self.qr_id} at {self.scanned_at}>'


# ─── API Key ───
class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    key_prefix = db.Column(db.String(8), nullable=False)  # first 8 chars for display
    key_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used = db.Column(db.DateTime)

    @staticmethod
    def generate_key():
        raw = f'qr_{secrets.token_hex(32)}'
        return raw

    @staticmethod
    def hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def __repr__(self):
        return f'<ApiKey {self.name} ({self.key_prefix}...)>'
