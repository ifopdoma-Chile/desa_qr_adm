from functools import wraps
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, abort
from sqlalchemy import func
from app import db
from app.models import QRCode, Tag, ApiKey, ScanLog, User

api_bp = Blueprint('api', __name__)


def authenticate(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        api_key_str = auth_header.replace('Bearer ', '')
        if not api_key_str:
            return jsonify({'error': 'API key requerida'}), 401

        api_key = None
        for ak in ApiKey.query.filter_by(is_active=True):
            if ApiKey.hash_key(api_key_str) == ak.key_hash:
                api_key = ak
                break

        if not api_key:
            return jsonify({'error': 'API key invalida'}), 401

        api_key.last_used = datetime.now(timezone.utc)
        db.session.commit()
        kwargs['user'] = api_key.user
        return f(*args, **kwargs)
    return decorated


def paginate(query, page, per_page=25):
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'data': [item.to_dict() for item in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    }


def qr_to_dict(qr):
    return {
        'id': qr.id,
        'uid': qr.uid,
        'slug': qr.slug,
        'title': qr.title,
        'description': qr.description,
        'qr_type': qr.qr_type,
        'is_active': qr.is_active,
        'is_deleted': qr.is_deleted,
        'scan_count': qr.scan_count,
        'max_scans': qr.max_scans,
        'expires_at': qr.expires_at.isoformat() if qr.expires_at else None,
        'created_at': qr.created_at.isoformat() if qr.created_at else None,
        'updated_at': qr.updated_at.isoformat() if qr.updated_at else None,
        'url': qr.get_qr_data(),
        'short_url': qr.full_url,
        'tags': [{'id': t.id, 'name': t.name} for t in qr.tags],
        'domain': qr.domain.domain if qr.domain else None,
    }


# ─── QR CRUD API ───

@api_bp.route('/qrs', methods=['GET'])
@authenticate
def list_qrs(user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    q = request.args.get('q', '')
    qr_type = request.args.get('type', '')
    tag = request.args.get('tag', '')

    query = QRCode.query.filter_by(is_deleted=False)
    if not user.is_admin:
        query = query.filter_by(user_id=user.id)
    if q:
        query = query.filter(QRCode.title.ilike(f'%{q}%'))
    if qr_type:
        query = query.filter(QRCode.qr_type == qr_type)
    if tag:
        query = query.filter(QRCode.tags.any(Tag.name == tag))

    query = query.order_by(QRCode.updated_at.desc())
    result = paginate(query, page, per_page)
    return jsonify(result)


@api_bp.route('/qrs', methods=['POST'])
@authenticate
def create_qr(user):
    if not user.can_edit:
        return jsonify({'error': 'No tienes permisos de edicion'}), 403
    data = request.get_json() or {}
    qr = QRCode()
    qr.user_id = user.id
    qr.title = data.get('title', 'Sin titulo')[:200]
    qr.qr_type = data.get('qr_type', 'url')
    qr.slug = data.get('slug', '').strip() or QRCode.generate_slug()
    qr.description = data.get('description', '')
    qr.content_url = data.get('content_url', '')
    qr.content_text = data.get('content_text', '')
    qr.is_active = data.get('is_active', True)

    if qr.qr_type == 'wifi':
        qr.wifi_ssid = data.get('wifi_ssid', '')
        qr.wifi_password = data.get('wifi_password', '')
        qr.wifi_encryption = data.get('wifi_encryption', 'WPA')
    elif qr.qr_type == 'vcard':
        qr.vcard_name = data.get('vcard_name', '')
        qr.vcard_first_name = data.get('vcard_first_name', '')
        qr.vcard_phone = data.get('vcard_phone', '')
        qr.vcard_email = data.get('vcard_email', '')
        qr.vcard_org = data.get('vcard_org', '')
        qr.vcard_title = data.get('vcard_title', '')
        qr.vcard_url = data.get('vcard_url', '')
    elif qr.qr_type == 'map':
        qr.map_lat = data.get('map_lat')
        qr.map_lon = data.get('map_lon')
        qr.map_label = data.get('map_label', '')
    elif qr.qr_type == 'email':
        qr.email_address = data.get('email_address', '')
        qr.email_subject = data.get('email_subject', '')
        qr.email_body = data.get('email_body', '')
    elif qr.qr_type in ('phone', 'sms'):
        qr.phone_number = data.get('phone_number', '')
        if qr.qr_type == 'sms':
            qr.sms_message = data.get('sms_message', '')
    elif qr.qr_type == 'json':
        qr.content_jsonb = data.get('content_jsonb', {})

    expires_at = data.get('expires_at')
    qr.expires_at = datetime.fromisoformat(expires_at) if expires_at else None
    qr.max_scans = data.get('max_scans', type=int)

    tag_names = data.get('tags', [])
    if tag_names:
        existing = Tag.query.filter(Tag.name.in_(tag_names), Tag.user_id == user.id).all()
        existing_names = {t.name for t in existing}
        for name in tag_names:
            if name not in existing_names:
                t = Tag(name=name, user_id=user.id)
                db.session.add(t)
                existing.append(t)
                existing_names.add(name)
        qr.tags = existing

    db.session.add(qr)
    db.session.commit()
    return jsonify(qr_to_dict(qr)), 201


@api_bp.route('/qrs/<slug>', methods=['GET'])
@authenticate
def get_qr(slug, user):
    qr = QRCode.query.filter_by(slug=slug, is_deleted=False).first()
    if not qr:
        return jsonify({'error': 'No encontrado'}), 404
    if not user.is_admin and qr.user_id != user.id:
        return jsonify({'error': 'No tienes permiso'}), 403
    return jsonify(qr_to_dict(qr))


@api_bp.route('/qrs/<slug>', methods=['PUT'])
@authenticate
def update_qr(slug, user):
    if not user.can_edit:
        return jsonify({'error': 'No tienes permisos de edicion'}), 403
    qr = QRCode.query.filter_by(slug=slug, is_deleted=False).first()
    if not qr:
        return jsonify({'error': 'No encontrado'}), 404
    if not user.is_admin and qr.user_id != user.id:
        return jsonify({'error': 'No tienes permiso'}), 403

    data = request.get_json() or {}
    for field in ('title', 'description', 'content_url', 'content_text', 'is_active',
                  'wifi_ssid', 'wifi_password', 'wifi_encryption',
                  'vcard_name', 'vcard_first_name', 'vcard_phone', 'vcard_email',
                  'vcard_org', 'vcard_title', 'vcard_url',
                  'map_label', 'email_address', 'email_subject', 'email_body',
                  'phone_number', 'sms_message', 'inactive_redirect_url'):
        if field in data:
            setattr(qr, field, data[field])
    if 'map_lat' in data:
        qr.map_lat = data['map_lat']
    if 'map_lon' in data:
        qr.map_lon = data['map_lon']
    if 'content_jsonb' in data:
        qr.content_jsonb = data['content_jsonb']
    if 'expires_at' in data:
        qr.expires_at = datetime.fromisoformat(data['expires_at']) if data['expires_at'] else None
    if 'max_scans' in data:
        qr.max_scans = data['max_scans']
    if 'tags' in data:
        tag_names = data['tags']
        existing = Tag.query.filter(Tag.name.in_(tag_names), Tag.user_id == user.id).all()
        existing_names = {t.name for t in existing}
        for name in tag_names:
            if name not in existing_names:
                t = Tag(name=name, user_id=user.id)
                db.session.add(t)
                existing.append(t)
                existing_names.add(name)
        qr.tags = existing

    qr.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(qr_to_dict(qr))


@api_bp.route('/qrs/<slug>', methods=['DELETE'])
@authenticate
def delete_qr(slug, user):
    if not user.can_edit:
        return jsonify({'error': 'No tienes permisos de edicion'}), 403
    qr = QRCode.query.filter_by(slug=slug).first()
    if not qr:
        return jsonify({'error': 'No encontrado'}), 404
    if not user.is_admin and qr.user_id != user.id:
        return jsonify({'error': 'No tienes permiso'}), 403

    hard = request.args.get('hard') == 'true'
    if hard and user.is_admin:
        db.session.delete(qr)
    else:
        qr.soft_delete()
    db.session.commit()
    return jsonify({'message': 'Eliminado'}), 200


@api_bp.route('/qrs/<slug>/restore', methods=['POST'])
@authenticate
def restore_qr(slug, user):
    if not user.can_edit:
        return jsonify({'error': 'No tienes permisos'}), 403
    qr = QRCode.query.filter_by(slug=slug, is_deleted=True).first()
    if not qr:
        return jsonify({'error': 'No encontrado'}), 404
    if not user.is_admin and qr.user_id != user.id:
        return jsonify({'error': 'No tienes permiso'}), 403
    qr.restore()
    db.session.commit()
    return jsonify(qr_to_dict(qr))


# ─── Analytics API ───

@api_bp.route('/analytics/overview')
@authenticate
def analytics_overview(user):
    query = QRCode.query.filter_by(is_deleted=False)
    if not user.is_admin:
        query = query.filter_by(user_id=user.id)

    total_qrs = query.count()
    active_qrs = query.filter(QRCode.is_active == True).count()
    total_scans = db.session.query(func.sum(QRCode.scan_count)).filter(
        QRCode.is_deleted == False
    )
    if not user.is_admin:
        total_scans = total_scans.filter(QRCode.user_id == user.id)
    total_scans = total_scans.scalar() or 0

    return jsonify({
        'total_qrs': total_qrs,
        'active_qrs': active_qrs,
        'total_scans': total_scans,
    })


@api_bp.route('/analytics/scans-by-day')
@authenticate
def analytics_scans_by_day(user):
    days = request.args.get('days', 30, type=int)
    query = db.session.query(
        func.date_trunc('day', ScanLog.scanned_at).label('day'),
        func.count(ScanLog.id).label('count')
    ).join(QRCode).filter(
        QRCode.is_deleted == False,
        ScanLog.scanned_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=days)
    )
    if not user.is_admin:
        query = query.filter(QRCode.user_id == user.id)
    query = query.group_by('day').order_by('day')
    return jsonify([{'date': r.day.isoformat() if r.day else None, 'count': r.count} for r in query.all()])


@api_bp.route('/analytics/top-qrs')
@authenticate
def analytics_top_qrs(user):
    limit = request.args.get('limit', 10, type=int)
    query = QRCode.query.filter_by(is_deleted=False, is_active=True)\
        .order_by(QRCode.scan_count.desc())
    if not user.is_admin:
        query = query.filter_by(user_id=user.id)
    qrs = query.limit(limit).all()
    return jsonify([qr_to_dict(qr) for qr in qrs])


@api_bp.route('/qrs/<slug>/scans')
@authenticate
def qr_scans(slug, user):
    qr = QRCode.query.filter_by(slug=slug).first()
    if not qr:
        return jsonify({'error': 'No encontrado'}), 404
    if not user.is_admin and qr.user_id != user.id:
        return jsonify({'error': 'No tienes permiso'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    scans = qr.scans.order_by(ScanLog.scanned_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'data': [{
            'id': s.id,
            'scanned_at': s.scanned_at.isoformat() if s.scanned_at else None,
            'ip_address': s.ip_address,
            'device_type': s.device_type,
            'browser': s.browser,
            'os_name': s.os_name,
            'country': s.country,
            'city': s.city,
            'region': s.region,
            'is_proxy': s.is_proxy,
            'proxy_type': s.proxy_type,
        } for s in scans.items],
        'page': scans.page,
        'per_page': scans.per_page,
        'total': scans.total,
        'pages': scans.pages,
    })


# ─── Tags API ───

@api_bp.route('/tags', methods=['GET'])
@authenticate
def list_tags(user):
    if user.is_admin:
        tags = Tag.query.all()
    else:
        tags = Tag.query.filter_by(user_id=user.id).all()
    return jsonify([{'id': t.id, 'name': t.name, 'color': t.color} for t in tags])
