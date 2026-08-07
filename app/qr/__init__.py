import secrets
import os
from datetime import datetime, timezone, timedelta
from flask import Blueprint, send_file, abort, request, jsonify, current_app
from app import db, limiter
from app.models import QRCode, ApiKey, TempToken
from app.utils import generate_qr_image, generate_qr_svg

qr_bp = Blueprint('qr', __name__)


def _resolve_logo_path(qr):
    """Devuelve la ruta del logo subido del QR si existe."""
    if not qr or not qr.logo_filename:
        return None
    path = os.path.join(current_app.root_path, 'static', 'uploads', os.path.basename(qr.logo_filename))
    if os.path.exists(path):
        return path
    return None


@qr_bp.route('/<slug>/download')
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_DOWNLOAD', '60/minute'))
def download_qr(slug, token=None, fmt=None):
    qr = QRCode.query.filter_by(slug=slug, is_deleted=False).first()
    if not qr:
        abort(404)
    if not qr.is_active:
        abort(410)

    fmt = (fmt or request.args.get('format', 'png')).lower()
    token = request.args.get('token')
    if token:
        # Token temporal en BD (multi-worker safe)
        tok = TempToken.query.filter_by(slug=slug, token=token).first()
        if not tok or not tok.is_valid:
            abort(401)
        db.session.delete(tok)
        db.session.commit()

    size = min(request.args.get('size', 400, type=int) or 400, 4096)
    logo_path = _resolve_logo_path(qr)

    style = request.args.get('style') or qr.qr_style or 'square'
    outer_shape = request.args.get('outer_shape') or qr.qr_outer_shape or 'square'
    fg = request.args.get('fg') or qr.qr_fg_color or '#000000'
    bg = request.args.get('bg') or qr.qr_bg_color or '#ffffff'
    gradient = request.args.get('gradient') or qr.qr_gradient or 'none'
    gradient_to = request.args.get('gradient_to') or qr.qr_gradient_to or '#1954A2'
    sticker = request.args.get('sticker') or qr.qr_sticker or 'none'
    transparent_bg = request.args.get('transparent') in ('1', 'true', 'on') or bool(qr.qr_transparent_bg)

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
                                   style=style, outer_shape=outer_shape,
                                   gradient=gradient, gradient_to=gradient_to,
                                   transparent_bg=transparent_bg, sticker=sticker)
        mimetype = 'image/png'
        filename = f'{slug}.png'

    return send_file(output, mimetype=mimetype, download_name=filename)


@qr_bp.route('/<slug>/download-svg')
def download_qr_svg(slug):
    return download_qr(slug, fmt='svg')


@qr_bp.route('/temp-token/<slug>')
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_TEMP_TOKEN', '30/minute'))
def get_temp_token(slug):
    auth = request.headers.get('Authorization', '').replace('Bearer ', '')
    api_key_obj = ApiKey.find_by_key(auth) if auth else None
    if not api_key_obj:
        abort(401)

    qr = QRCode.query.filter_by(slug=slug).first()
    if not qr or qr.user_id != api_key_obj.user_id:
        abort(404)

    token = secrets.token_urlsafe(16)
    ttl = current_app.config.get('QR_TEMP_TOKEN_TTL', 300)
    # Limpieza de tokens viejos del slug
    TempToken.query.filter(
        (TempToken.slug == slug) & (TempToken.expires_at < datetime.now(timezone.utc))
    ).delete()
    db.session.add(TempToken(
        slug=slug,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
    ))
    db.session.commit()

    return jsonify({'token': token, 'ttl': ttl})
