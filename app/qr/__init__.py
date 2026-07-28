import secrets
import hashlib
from datetime import datetime, timezone
from flask import Blueprint, send_file, abort, request, jsonify, current_app
from app import db
from app.models import QRCode, User
from app.utils import generate_qr_image, generate_qr_svg

qr_bp = Blueprint('qr', __name__)

TEMP_TOKENS = {}


@qr_bp.route('/<slug>/download')
def download_qr(slug, token=None):
    qr = QRCode.query.filter_by(slug=slug, is_deleted=False).first()
    if not qr:
        abort(404)
    if not qr.is_active:
        abort(410)

    fmt = request.args.get('format', 'png').lower()
    token = request.args.get('token')
    if token:
        expected = TEMP_TOKENS.get(slug)
        if not expected or expected != token:
            abort(401)
        TEMP_TOKENS.pop(slug, None)

    size = request.args.get('size', 400, type=int)
    logo_path = None

    style = request.args.get('style') or qr.qr_style or 'square'
    outer_shape = request.args.get('outer_shape') or qr.qr_outer_shape or 'square'
    fg = request.args.get('fg') or qr.qr_fg_color or '#000000'
    bg = request.args.get('bg') or qr.qr_bg_color or '#ffffff'

    data = qr.get_qr_data()
    if not data:
        abort(400)

    if fmt == 'svg':
        output = generate_qr_svg(data, fill_color=fg, back_color=bg)
        mimetype = 'image/svg+xml'
        filename = f'{slug}.svg'
    else:
        output = generate_qr_image(data, size=size, logo_path=logo_path,
                                   fill_color=fg, back_color=bg,
                                   style=style, outer_shape=outer_shape)
        mimetype = 'image/png'
        filename = f'{slug}.png'

    return send_file(output, mimetype=mimetype, download_name=filename)


@qr_bp.route('/<slug>/download-svg')
def download_qr_svg(slug):
    return download_qr(slug, fmt='svg')


@qr_bp.route('/temp-token/<slug>')
def get_temp_token(slug):
    auth = request.headers.get('Authorization', '').replace('Bearer ', '')
    api_key_obj = None
    from app.models import ApiKey
    for ak in ApiKey.query.filter_by(is_active=True):
        if ApiKey.hash_key(auth) == ak.key_hash:
            api_key_obj = ak
            break
    if not api_key_obj:
        abort(401)

    qr = QRCode.query.filter_by(slug=slug).first()
    if not qr or qr.user_id != api_key_obj.user_id:
        abort(404)

    token = secrets.token_urlsafe(16)
    ttl = current_app.config.get('QR_TEMP_TOKEN_TTL', 300)
    TEMP_TOKENS[slug] = token
    from threading import Timer
    Timer(ttl, lambda: TEMP_TOKENS.pop(slug, None)).start()

    return jsonify({'token': token, 'ttl': ttl})
