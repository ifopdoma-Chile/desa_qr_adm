import csv
import io
import secrets
from datetime import datetime, timezone
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, jsonify, Response, send_file, session
)
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import User, QRCode, Tag, Domain, ApiKey, ScanLog, ConditionalRedirect
from app.utils import generate_qr_image, generate_qr_svg

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')




def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.can_edit:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── Helpers ───

def get_user_qrs(query=None):
    base = QRCode.query.filter_by(is_deleted=False)
    if not current_user.is_admin:
        base = base.filter_by(user_id=current_user.id)
    if query:
        base = base.filter(
            QRCode.title.ilike(f'%{query}%') |
            QRCode.slug.ilike(f'%{query}%')
        )
    return base.order_by(QRCode.updated_at.desc())


def get_trashed_qrs():
    base = QRCode.query.filter_by(is_deleted=True)
    if not current_user.is_admin:
        base = base.filter_by(user_id=current_user.id)
    return base.order_by(QRCode.deleted_at.desc())


# ─── Dashboard ───

@admin_bp.route('/')
@login_required
def dashboard():
    total_qrs = get_user_qrs().count()
    active_qrs = get_user_qrs().filter(QRCode.is_active == True).count()
    total_scans = db.session.query(func.sum(QRCode.scan_count)).filter(
        QRCode.is_deleted == False
    )
    if not current_user.is_admin:
        total_scans = total_scans.filter(QRCode.user_id == current_user.id)
    total_scans = total_scans.scalar() or 0

    recent_qrs = get_user_qrs().limit(10).all()

    scans_by_day = db.session.query(
        func.date_trunc('day', ScanLog.scanned_at).label('day'),
        func.count(ScanLog.id).label('count')
    ).join(QRCode).filter(
        QRCode.is_deleted == False,
        ScanLog.scanned_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=30)
    )
    if not current_user.is_admin:
        scans_by_day = scans_by_day.filter(QRCode.user_id == current_user.id)
    scans_by_day = scans_by_day.group_by('day').order_by('day').all()

    top_qrs = get_user_qrs().filter(QRCode.is_active == True).order_by(QRCode.scan_count.desc()).limit(10).all()

    return render_template('dashboard.html',
                         total_qrs=total_qrs,
                         active_qrs=active_qrs,
                         total_scans=total_scans,
                         recent_qrs=recent_qrs,
                         scans_by_day=scans_by_day,
                         top_qrs=top_qrs)


# ─── QR CRUD ───

@admin_bp.route('/qr')
@login_required
def qr_list():
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '')
    tag_id = request.args.get('tag', type=int)
    qr_type = request.args.get('type', '')

    base = get_user_qrs(query)
    if tag_id:
        base = base.filter(QRCode.tags.any(id=tag_id))
    if qr_type:
        base = base.filter(QRCode.qr_type == qr_type)

    pagination = base.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 25), error_out=False)
    qrs = pagination.items
    tags = Tag.query.order_by(Tag.name).all()
    return render_template('qr_list.html', qrs=qrs, pagination=pagination, tags=tags,
                         query=query, tag_id=tag_id, qr_type=qr_type,
                         qr_types=QRCode.QR_TYPES)


@admin_bp.route('/qr/nuevo', methods=['GET', 'POST'])
@editor_required
def qr_create():
    if current_user.qr_count >= current_app.config.get('QR_MAX_PER_USER', 500) and not current_user.is_admin:
        flash(f'Has alcanzado el limite de {current_app.config.get("QR_MAX_PER_USER")} QR.', 'warning')
        return redirect(url_for('admin.qr_list'))

    tags = Tag.query.order_by(Tag.name).all()
    domains = Domain.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        qr = QRCode()
        qr.user_id = current_user.id
        _populate_qr_from_form(qr)
        db.session.add(qr)
        db.session.commit()
        flash('QR creado exitosamente.', 'success')
        return redirect(url_for('admin.qr_detail', qr_id=qr.id))

    return render_template('qr_form.html', qr=None, tags=tags, domains=domains,
                         qr_types=QRCode.QR_TYPES, qr_styles=QRCode.QR_STYLES,
                         qr_outer_shapes=QRCode.QR_OUTER_SHAPES)


@admin_bp.route('/qr/<int:qr_id>')
@login_required
def qr_detail(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)

    page = request.args.get('page', 1, type=int)
    scans = qr.scans.order_by(ScanLog.scanned_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    scans_by_device = db.session.query(
        ScanLog.device_type, func.count(ScanLog.id)
    ).filter(ScanLog.qr_id == qr_id).group_by(ScanLog.device_type).all()

    scans_by_day = db.session.query(
        func.date_trunc('day', ScanLog.scanned_at).label('day'),
        func.count(ScanLog.id).label('count')
    ).filter(ScanLog.qr_id == qr_id).group_by('day').order_by('day').all()

    return render_template('qr_detail.html', qr=qr, scans=scans,
                         scans_by_device=scans_by_device, scans_by_day=scans_by_day)


@admin_bp.route('/qr/<int:qr_id>/editar', methods=['GET', 'POST'])
@editor_required
def qr_edit(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    tags = Tag.query.order_by(Tag.name).all()
    domains = Domain.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        _populate_qr_from_form(qr)
        qr.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('QR actualizado exitosamente.', 'success')
        return redirect(url_for('admin.qr_detail', qr_id=qr.id))

    return render_template('qr_form.html', qr=qr, tags=tags, domains=domains,
                         qr_types=QRCode.QR_TYPES, qr_styles=QRCode.QR_STYLES,
                         qr_outer_shapes=QRCode.QR_OUTER_SHAPES)


@admin_bp.route('/qr/<int:qr_id>/toggle', methods=['POST'])
@editor_required
def qr_toggle(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.is_active = not qr.is_active
    db.session.commit()
    estado = 'activado' if qr.is_active else 'desactivado'
    flash(f'QR {estado}.', 'success')
    return redirect(url_for('admin.qr_detail', qr_id=qr.id))


@admin_bp.route('/qr/<int:qr_id>/delete', methods=['POST'])
@editor_required
def qr_delete(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.soft_delete()
    db.session.commit()
    flash('QR enviado a la papelera.', 'warning')
    return redirect(url_for('admin.qr_list'))


@admin_bp.route('/qr/<int:qr_id>/restore', methods=['POST'])
@editor_required
def qr_restore(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.restore()
    db.session.commit()
    flash('QR restaurado.', 'success')
    return redirect(url_for('admin.qr_detail', qr_id=qr.id))


@admin_bp.route('/qr/<int:qr_id>/destroy', methods=['POST'])
@admin_required
def qr_destroy(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    db.session.delete(qr)
    db.session.commit()
    flash('QR eliminado permanentemente.', 'info')
    return redirect(url_for('admin.qr_trash'))


# ─── Papelera ───

@admin_bp.route('/papelera')
@login_required
def qr_trash():
    page = request.args.get('page', 1, type=int)
    pagination = get_trashed_qrs().paginate(page=page, per_page=25, error_out=False)
    return render_template('qr_trash.html', qrs=pagination.items, pagination=pagination)


@admin_bp.route('/papelera/vaciar', methods=['POST'])
@admin_required
def qr_trash_empty():
    qrs = get_trashed_qrs().all()
    for qr in qrs:
        db.session.delete(qr)
    db.session.commit()
    flash('Papelera vaciada.', 'info')
    return redirect(url_for('admin.qr_trash'))


# ─── Tags ───

@admin_bp.route('/tags')
@login_required
def tag_list():
    if current_user.is_admin:
        tags = Tag.query.order_by(Tag.name).all()
    else:
        tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name).all()
    return render_template('tags.html', tags=tags)


@admin_bp.route('/tags/nuevo', methods=['POST'])
@editor_required
def tag_create():
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#2c6b9e')
    if not name:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('admin.tag_list'))
    existing = Tag.query.filter_by(name=name, user_id=current_user.id).first()
    if existing:
        flash('Ya existe un tag con ese nombre.', 'warning')
        return redirect(url_for('admin.tag_list'))
    tag = Tag(name=name, color=color, user_id=current_user.id)
    db.session.add(tag)
    db.session.commit()
    flash('Tag creado.', 'success')
    return redirect(url_for('admin.tag_list'))


@admin_bp.route('/tags/<int:tag_id>/editar', methods=['POST'])
@editor_required
def tag_edit(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    if not current_user.is_admin and tag.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.tag_list'))
    tag.name = request.form.get('name', tag.name).strip()
    tag.color = request.form.get('color', tag.color)
    db.session.commit()
    flash('Tag actualizado.', 'success')
    return redirect(url_for('admin.tag_list'))


@admin_bp.route('/tags/<int:tag_id>/eliminar', methods=['POST'])
@editor_required
def tag_delete(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    if not current_user.is_admin and tag.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.tag_list'))
    db.session.delete(tag)
    db.session.commit()
    flash('Tag eliminado.', 'info')
    return redirect(url_for('admin.tag_list'))


# ─── Usuarios (solo admin) ───

@admin_bp.route('/usuarios')
@admin_required
def user_list():
    users = User.query.order_by(User.username).all()
    return render_template('users.html', users=users)


@admin_bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@admin_required
def user_create():
    if request.method == 'POST':
        user = User()
        user.username = request.form.get('username', '').strip()
        user.email = request.form.get('email', '').strip()
        user.full_name = request.form.get('full_name', '').strip()
        user.role = request.form.get('role', User.ROLE_EDITOR)
        user.set_password(request.form.get('password', ''))
        if not user.username or not user.email:
            flash('Usuario y email son obligatorios.', 'danger')
            return render_template('user_form.html', user=None)
        db.session.add(user)
        db.session.commit()
        flash('Usuario creado.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('user_form.html', user=None)


@admin_bp.route('/usuarios/<int:user_id>/editar', methods=['GET', 'POST'])
@admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form.get('username', user.username).strip()
        user.email = request.form.get('email', user.email).strip()
        user.full_name = request.form.get('full_name', user.full_name).strip()
        user.role = request.form.get('role', user.role)
        user.is_active_user = request.form.get('is_active') == 'on'
        password = request.form.get('password', '')
        if password:
            user.set_password(password)
        db.session.commit()
        flash('Usuario actualizado.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('user_form.html', user=user)


# ─── API Keys ───

@admin_bp.route('/api-keys')
@login_required
def api_key_list():
    keys = ApiKey.query.filter_by(user_id=current_user.id).all()
    return render_template('api_keys.html', keys=keys)


@admin_bp.route('/api-keys/nueva', methods=['POST'])
@login_required
def api_key_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('admin.api_key_list'))
    raw_key = ApiKey.generate_key()
    key_hash = ApiKey.hash_key(raw_key)
    api_key = ApiKey(
        user_id=current_user.id,
        name=name,
        key_prefix=raw_key[:8],
        key_hash=key_hash,
    )
    db.session.add(api_key)
    db.session.commit()
    session['new_api_key'] = raw_key
    session['new_api_key_name'] = name
    flash('API Key creada. Copiala ahora, no se mostrara de nuevo.', 'success')
    return redirect(url_for('admin.api_key_list'))


@admin_bp.route('/api-keys/clear-session', methods=['POST'])
@login_required
def api_key_clear_session():
    session.pop('new_api_key', None)
    session.pop('new_api_key_name', None)
    return redirect(url_for('admin.api_key_list'))


@admin_bp.route('/api-keys/<int:key_id>/eliminar', methods=['POST'])
@login_required
def api_key_delete(key_id):
    key = ApiKey.query.get_or_404(key_id)
    if key.user_id != current_user.id and not current_user.is_admin:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.api_key_list'))
    db.session.delete(key)
    db.session.commit()
    flash('API Key eliminada.', 'info')
    return redirect(url_for('admin.api_key_list'))


# ─── Dominios ───

@admin_bp.route('/dominios')
@admin_required
def domain_list():
    domains = Domain.query.order_by(Domain.domain).all()
    return render_template('domains.html', domains=domains)


@admin_bp.route('/dominios/nuevo', methods=['POST'])
@admin_required
def domain_create():
    domain_name = request.form.get('domain', '').strip().lower()
    if not domain_name:
        flash('El dominio es obligatorio.', 'danger')
        return redirect(url_for('admin.domain_list'))
    domain = Domain(domain=domain_name)
    db.session.add(domain)
    db.session.commit()
    flash('Dominio agregado.', 'success')
    return redirect(url_for('admin.domain_list'))


@admin_bp.route('/dominios/<int:domain_id>/toggle', methods=['POST'])
@admin_required
def domain_toggle(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    domain.is_active = not domain.is_active
    db.session.commit()
    flash('Dominio actualizado.', 'success')
    return redirect(url_for('admin.domain_list'))


# ─── Import / Export ───

@admin_bp.route('/import-export', methods=['GET', 'POST'])
@editor_required
def import_export():
    if request.method == 'POST' and 'csv_file' in request.files:
        f = request.files['csv_file']
        if not f.filename.endswith('.csv'):
            flash('El archivo debe ser CSV.', 'danger')
            return redirect(url_for('admin.import_export'))
        stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        created = 0
        errors = 0
        for row in reader:
            try:
                qr = QRCode()
                qr.user_id = current_user.id
                qr.title = row.get('title', 'Sin titulo')[:200]
                qr.qr_type = row.get('qr_type', 'url')
                qr.slug = row.get('slug', QRCode.generate_slug())
                qr.content_url = row.get('content_url', '')
                qr.content_text = row.get('content_text', '')
                qr.description = row.get('description', '')
                qr.is_active = row.get('is_active', '1') in ('1', 'true', 'yes')
                db.session.add(qr)
                created += 1
            except Exception:
                errors += 1
        db.session.commit()
        flash(f'Importados {created} QR. Errores: {errors}.', 'success')
        return redirect(url_for('admin.import_export'))

    return render_template('import_export.html')


@admin_bp.route('/exportar/csv')
@login_required
def export_csv():
    qrs = get_user_qrs().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['slug', 'title', 'qr_type', 'content_url', 'content_text',
                     'description', 'is_active', 'scan_count', 'created_at'])
    for qr in qrs:
        writer.writerow([
            qr.slug, qr.title, qr.qr_type, qr.content_url, qr.content_text,
            qr.description, qr.is_active, qr.scan_count,
            qr.created_at.isoformat() if qr.created_at else ''
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=qrs.csv'}
    )


# ─── Redirecciones condicionales ───

@admin_bp.route('/qr/<int:qr_id>/conditional-redirects', methods=['GET', 'POST'])
@editor_required
def conditional_redirects(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    if request.method == 'POST':
        cr = ConditionalRedirect(
            qr_id=qr.id,
            device_type=request.form.get('device_type', ''),
            user_agent_pattern=request.form.get('user_agent_pattern', ''),
            target_url=request.form.get('target_url', ''),
            priority=request.form.get('priority', 0, type=int),
        )
        db.session.add(cr)
        db.session.commit()
        flash('Redireccion condicional agregada.', 'success')
        return redirect(url_for('admin.conditional_redirects', qr_id=qr.id))
    redirects = qr.conditional_redirects.order_by(ConditionalRedirect.priority.desc()).all()
    return render_template('conditional_redirects.html', qr=qr, redirects=redirects)


@admin_bp.route('/conditional-redirects/<int:cr_id>/eliminar', methods=['POST'])
@editor_required
def conditional_redirect_delete(cr_id):
    cr = ConditionalRedirect.query.get_or_404(cr_id)
    qr = QRCode.query.get(cr.qr_id)
    if qr:
        _check_owner(qr)
    db.session.delete(cr)
    db.session.commit()
    flash('Redireccion condicional eliminada.', 'info')
    return redirect(url_for('admin.conditional_redirects', qr_id=cr.qr_id))


# ─── Helpers internos ───

def _check_owner(qr):
    if not current_user.is_admin and qr.user_id != current_user.id:
        from flask import abort as flask_abort
        flask_abort(403)


def _populate_qr_from_form(qr):
    qr.title = request.form.get('title', 'Sin titulo')[:200]
    qr.description = request.form.get('description', '')
    qr.qr_type = request.form.get('qr_type', 'url')
    slug = request.form.get('slug', '').strip()
    qr.slug = slug or QRCode.generate_slug()
    while QRCode.query.filter(QRCode.slug == qr.slug, QRCode.id != (qr.id or 0)).first():
        qr.slug = QRCode.generate_slug()
    qr.is_active = request.form.get('is_active') == 'on'

    qr.content_url = request.form.get('content_url', '')
    qr.content_text = request.form.get('content_text', '')

    qr.wifi_ssid = request.form.get('wifi_ssid', '')
    qr.wifi_password = request.form.get('wifi_password', '')
    qr.wifi_encryption = request.form.get('wifi_encryption', 'WPA')

    qr.vcard_name = request.form.get('vcard_name', '')
    qr.vcard_first_name = request.form.get('vcard_first_name', '')
    qr.vcard_phone = request.form.get('vcard_phone', '')
    qr.vcard_email = request.form.get('vcard_email', '')
    qr.vcard_org = request.form.get('vcard_org', '')
    qr.vcard_title = request.form.get('vcard_title', '')
    qr.vcard_url = request.form.get('vcard_url', '')

    qr.map_lat = request.form.get('map_lat', type=float)
    qr.map_lon = request.form.get('map_lon', type=float)
    qr.map_label = request.form.get('map_label', '')

    qr.email_address = request.form.get('email_address', '')
    qr.email_subject = request.form.get('email_subject', '')
    qr.email_body = request.form.get('email_body', '')

    qr.phone_number = request.form.get('phone_number', '')
    qr.sms_message = request.form.get('sms_message', '')

    import json
    try:
        json_raw = request.form.get('content_jsonb', '{}')
        qr.content_jsonb = json.loads(json_raw) if json_raw else {}
    except (json.JSONDecodeError, TypeError):
        qr.content_jsonb = {}

    domain_id = request.form.get('domain_id', type=int)
    qr.domain_id = domain_id if domain_id else None

    expires_at = request.form.get('expires_at', '')
    qr.expires_at = datetime.fromisoformat(expires_at) if expires_at else None

    qr.max_scans = request.form.get('max_scans', type=int)
    if qr.max_scans == 0:
        qr.max_scans = None

    qr.inactive_redirect_url = request.form.get('inactive_redirect_url', '')

    qr.qr_style = request.form.get('qr_style', 'square')
    qr.qr_fg_color = request.form.get('qr_fg_color', '#000000')
    qr.qr_bg_color = request.form.get('qr_bg_color', '#ffffff')
    qr.qr_outer_shape = request.form.get('qr_outer_shape', 'square')

    tag_ids = request.form.getlist('tags')
    qr.tags = []
    if tag_ids:
        qr.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

    qr.updated_at = datetime.now(timezone.utc)
