import csv
import io
import os
import re
import secrets
import requests
from datetime import datetime, timezone
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, jsonify, Response, send_file, session, abort
)
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from app import db
from app.models import User, QRCode, Tag, Domain, ApiKey, ScanLog, ConditionalRedirect, AuditLog, Webhook
from app.utils import generate_qr_image, generate_qr_svg, log_audit

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')




# Regex de hostname valido (etiquetas alfanumericas, guion medio, puntos)
DOMAIN_RE = re.compile(
    r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$'
)


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
        func.date_trunc('day', func.timezone('America/Santiago', ScanLog.scanned_at)).label('day'),
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
@login_required
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
        log_audit('create_qr', 'qr', qr.id, f'slug={qr.slug} title={qr.title}')
        flash('QR creado exitosamente.', 'success')
        return redirect(url_for('admin.qr_detail', qr_id=qr.id))

    return render_template('qr_form.html', qr=None, tags=tags, domains=domains,
                         qr_types=QRCode.QR_TYPES, qr_styles=QRCode.QR_STYLES,
                         qr_outer_shapes=QRCode.QR_OUTER_SHAPES,
                         qr_gradients=QRCode.QR_GRADIENTS,
                         qr_stickers=QRCode.QR_STICKERS)


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


@admin_bp.route('/qr/<int:qr_id>/enviar-email', methods=['POST'])
@login_required
def qr_send_email(qr_id):
    """Envia el QR por correo electronico al dueno del QR (o al usuario actual)."""
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)

    # Destinatario: por defecto el email del owner del QR, o input del form
    recipient = request.form.get('email', '').strip() or current_user.email
    subject = request.form.get('subject', '').strip() or f'Codigo QR: {qr.title}'

    from app.utils import send_qr_email
    success, msg = send_qr_email(recipient, qr, current_app.config['APP_BASE_URL'],
                                  subject=subject)
    if success:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('admin.qr_detail', qr_id=qr.id))


@admin_bp.route('/qr/<int:qr_id>/editar', methods=['GET', 'POST'])
@login_required
def qr_edit(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    tags = Tag.query.order_by(Tag.name).all()
    domains = Domain.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        _populate_qr_from_form(qr)
        qr.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        log_audit('update_qr', 'qr', qr.id, f'slug={qr.slug} title={qr.title}')
        flash('QR actualizado exitosamente.', 'success')
        return redirect(url_for('admin.qr_detail', qr_id=qr.id))

    return render_template('qr_form.html', qr=qr, tags=tags, domains=domains,
                         qr_types=QRCode.QR_TYPES, qr_styles=QRCode.QR_STYLES,
                         qr_outer_shapes=QRCode.QR_OUTER_SHAPES,
                         qr_gradients=QRCode.QR_GRADIENTS,
                         qr_stickers=QRCode.QR_STICKERS)


@admin_bp.route('/qr/preview')
@login_required
def qr_preview():
    """Genera un PNG de preview en vivo con los parametros del formulario."""
    data = request.args.get('data', 'https://siom.ifop.cl/')
    size = min(request.args.get('size', 300, type=int) or 300, 1024)
    style = request.args.get('style', 'square')
    outer_shape = request.args.get('outer_shape', 'square')
    fg = request.args.get('fg', '#000000')
    bg = request.args.get('bg', '#ffffff')
    gradient = request.args.get('gradient', 'none')
    gradient_to = request.args.get('gradient_to', '#1954A2')
    sticker = request.args.get('sticker', 'none')
    transparent = request.args.get('transparent', '0') == '1'
    logo = request.args.get('logo', '')

    logo_path = None
    if logo:
        logo_path = os.path.join(current_app.root_path, 'static', 'uploads', os.path.basename(logo))
        if not os.path.exists(logo_path):
            logo_path = None

    output = generate_qr_image(data, size=size, logo_path=logo_path,
                               fill_color=fg, back_color=bg,
                               style=style, outer_shape=outer_shape,
                               gradient=gradient, gradient_to=gradient_to,
                               transparent_bg=transparent, sticker=sticker)
    return send_file(output, mimetype='image/png')


@admin_bp.route('/qr/<int:qr_id>/toggle', methods=['POST'])
@login_required
def qr_toggle(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.is_active = not qr.is_active
    db.session.commit()
    log_audit('toggle_qr', 'qr', qr.id, f'slug={qr.slug} active={qr.is_active}')
    estado = 'activado' if qr.is_active else 'desactivado'
    flash(f'QR {estado}.', 'success')
    return redirect(url_for('admin.qr_detail', qr_id=qr.id))


@admin_bp.route('/qr/<int:qr_id>/delete', methods=['POST'])
@login_required
def qr_delete(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.soft_delete()
    db.session.commit()
    log_audit('delete_qr', 'qr', qr.id, f'slug={qr.slug}')
    flash('QR enviado a la papelera.', 'warning')
    return redirect(url_for('admin.qr_list'))


@admin_bp.route('/qr/<int:qr_id>/restore', methods=['POST'])
@login_required
def qr_restore(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    qr.restore()
    db.session.commit()
    log_audit('restore_qr', 'qr', qr.id, f'slug={qr.slug}')
    flash('QR restaurado.', 'success')
    return redirect(url_for('admin.qr_detail', qr_id=qr.id))


@admin_bp.route('/qr/<int:qr_id>/destroy', methods=['POST'])
@login_required
def qr_destroy(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)
    db.session.delete(qr)
    db.session.commit()
    log_audit('destroy_qr', 'qr', qr_id, f'slug={qr.slug}')
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
@login_required
def qr_trash_empty():
    qrs = get_trashed_qrs().all()
    for qr in qrs:
        db.session.delete(qr)
    db.session.commit()
    log_audit('empty_trash', 'qr', None, f'{len(qrs)} QR eliminados permanentemente')
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
@login_required
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
    log_audit('create_tag', 'tag', tag.id, name)
    flash('Tag creado.', 'success')
    return redirect(url_for('admin.tag_list'))


@admin_bp.route('/tags/<int:tag_id>/editar', methods=['POST'])
@login_required
def tag_edit(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    if not current_user.is_admin and tag.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.tag_list'))
    tag.name = request.form.get('name', tag.name).strip()
    tag.color = request.form.get('color', tag.color)
    db.session.commit()
    log_audit('update_tag', 'tag', tag.id, tag.name)
    flash('Tag actualizado.', 'success')
    return redirect(url_for('admin.tag_list'))


@admin_bp.route('/tags/<int:tag_id>/eliminar', methods=['POST'])
@login_required
def tag_delete(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    if not current_user.is_admin and tag.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.tag_list'))
    db.session.delete(tag)
    db.session.commit()
    log_audit('delete_tag', 'tag', tag_id, tag.name)
    flash('Tag eliminado.', 'info')
    return redirect(url_for('admin.tag_list'))


# ─── Usuarios (solo admin) ───

@admin_bp.route('/usuarios')
@admin_required
def user_list():
    # Busqueda + paginacion (20 por pagina)
    q = (request.args.get('q') or '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    query = User.query
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(
            User.username.ilike(like),
            User.email.ilike(like),
            User.full_name.ilike(like),
        ))
    users_p = query.order_by(User.username).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('users.html', users=users_p.items, pagination=users_p, q=q)


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
        if not user.username or not user.email or '@' not in user.email:
            flash('Usuario y email valido son obligatorios.', 'danger')
            return render_template('user_form.html', user=None)
        if User.query.filter_by(username=user.username).first():
            flash('Ese nombre de usuario ya existe.', 'danger')
            return render_template('user_form.html', user=None)
        # El admin ya dio el visto bueno al crear -> aprobado directo
        user.is_approved = True
        user.is_active_user = True
        db.session.add(user)
        db.session.commit()
        log_audit('create_user', 'user', user.id, f'username={user.username} role={user.role}')
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
        log_audit('update_user', 'user', user.id, f'username={user.username} role={user.role} active={user.is_active_user}')
        flash('Usuario actualizado.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('user_form.html', user=user)


@admin_bp.route('/usuarios/<int:user_id>/aprobar', methods=['POST'])
@admin_required
def user_approve(user_id):
    """Aprueba un usuario nuevo (por ejemplo, registrado via Google)."""
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    user.is_active_user = True
    db.session.commit()
    log_audit('approve_user', 'user', user.id, user.username)
    flash(f'Usuario {user.username} aprobado. Ya puede ingresar.', 'success')
    return redirect(url_for('admin.user_list'))


@admin_bp.route('/usuarios/<int:user_id>/rechazar', methods=['POST'])
@admin_required
def user_reject(user_id):
    """Rechaza/desactiva un usuario pendiente."""
    user = User.query.get_or_404(user_id)
    user.is_approved = False
    user.is_active_user = False
    db.session.commit()
    log_audit('reject_user', 'user', user.id, user.username)
    flash(f'Usuario {user.username} rechazado.', 'warning')
    return redirect(url_for('admin.user_list'))


@admin_bp.route('/usuarios/<int:user_id>/eliminar', methods=['POST'])
@admin_required
def user_delete(user_id):
    """Elimina un usuario.

    - Por defecto: sus QR se transfieren al admin que ejecuta la accion.
    - Con delete_qrs=1: sus QR (y todo lo asociado: escaneos, redirecciones, tags) se borran permanentemente.
    """
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('No puedes eliminar tu propia cuenta.', 'danger')
        return redirect(url_for('admin.user_list'))

    delete_qrs = request.form.get('delete_qrs') == '1'
    n_qrs = user.qr_codes.count()
    n_keys = user.api_keys.count()

    # Tags del usuario (FK a users.id sin cascade) -> se eliminan explicitamente
    for tag in list(user.tags):
        db.session.delete(tag)

    # Dominios creados por el usuario -> pasan al admin que elimina (recursos globales)
    Domain.query.filter_by(user_id=user.id).update({'user_id': current_user.id})

    if delete_qrs:
        # cascade 'all, delete-orphan' borra sus QR; escaneos/redirecciones cierran via ondelete=CASCADE
        db.session.delete(user)
        db.session.commit()
        log_audit('delete_user', 'user', user_id, f'username={user.username} delete_qrs=1 ({n_qrs} QR)')
        flash(f'Usuario {user.username} eliminado permanentemente junto con sus {n_qrs} QR y {n_keys} API keys.', 'info')
    else:
        # Transferir sus QR al admin que ejecuta la accion (conserva el historial de escaneos)
        user.qr_codes.update({'user_id': current_user.id})
        db.session.delete(user)  # api_keys via cascade
        db.session.commit()
        log_audit('delete_user', 'user', user_id, f'username={user.username} transfer={n_qrs} QR a {current_user.username}')
        flash(f'Usuario {user.username} eliminado. Sus {n_qrs} QR fueron transferidos a tu cuenta.', 'success')
    return redirect(url_for('admin.user_list'))


# ─── API Keys ───

@admin_bp.route('/api-keys')
@admin_required
def api_key_list():
    keys = ApiKey.query.filter_by(user_id=current_user.id).all()
    return render_template('api_keys.html', keys=keys)


@admin_bp.route('/api-keys/nueva', methods=['POST'])
@admin_required
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
    log_audit('create_api_key', 'api_key', api_key.id, name)
    session['new_api_key'] = raw_key
    session['new_api_key_name'] = name
    flash('API Key creada. Copiala ahora, no se mostrara de nuevo.', 'success')
    return redirect(url_for('admin.api_key_list'))


@admin_bp.route('/api-keys/clear-session', methods=['POST'])
@admin_required
def api_key_clear_session():
    session.pop('new_api_key', None)
    session.pop('new_api_key_name', None)
    return redirect(url_for('admin.api_key_list'))


@admin_bp.route('/api-keys/<int:key_id>/eliminar', methods=['POST'])
@admin_required
def api_key_delete(key_id):
    key = ApiKey.query.get_or_404(key_id)
    if key.user_id != current_user.id and not current_user.is_admin:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.api_key_list'))
    db.session.delete(key)
    db.session.commit()
    log_audit('delete_api_key', 'api_key', key_id, key.name)
    flash('API Key eliminada.', 'info')
    return redirect(url_for('admin.api_key_list'))


# ─── Dominios (multi-dominio; editores pueden crear) ───

@admin_bp.route('/dominios')
@editor_required
def domain_list():
    domains = Domain.query.order_by(Domain.domain).all()
    return render_template('domains.html', domains=domains,
                           can_toggle=current_user.is_admin)


@admin_bp.route('/dominios/nuevo', methods=['POST'])
@editor_required
def domain_create():
    domain_name = request.form.get('domain', '').strip().lower()
    domain_name = domain_name.replace('https://', '').replace('http://', '').rstrip('/')
    if not domain_name:
        flash('El dominio es obligatorio.', 'danger')
        return redirect(url_for('admin.domain_list'))
    if len(domain_name) > 253 or not DOMAIN_RE.match(domain_name):
        flash('Dominio invalido: usa un hostname valido (ej: qr.ifop.cl, misiones.ifop.cl).', 'danger')
        return redirect(url_for('admin.domain_list'))
    if Domain.query.filter_by(domain=domain_name).first():
        flash('Ese dominio ya existe.', 'warning')
        return redirect(url_for('admin.domain_list'))
    domain = Domain(domain=domain_name, user_id=current_user.id)
    db.session.add(domain)
    db.session.commit()
    log_audit('create_domain', 'domain', domain.id, domain_name)
    flash(f'Dominio {domain_name} agregado.', 'success')
    return redirect(url_for('admin.domain_list'))


@admin_bp.route('/dominios/<int:domain_id>/toggle', methods=['POST'])
@admin_required
def domain_toggle(domain_id):
    domain = Domain.query.get_or_404(domain_id)
    domain.is_active = not domain.is_active
    db.session.commit()
    log_audit('toggle_domain', 'domain', domain.id, f'{domain.domain} active={domain.is_active}')
    flash('Dominio actualizado.', 'success')
    return redirect(url_for('admin.domain_list'))


# ─── Import / Export ───

@admin_bp.route('/import-export', methods=['GET', 'POST'])
@admin_required
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
        log_audit('import_qr', 'qr', None, f'{created} importados, {errors} errores')
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
        log_audit('create_conditional_redirect', 'conditional_redirect', cr.id,
                  f'qr={qr.slug} device={cr.device_type} -> {cr.target_url}')
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
    log_audit('delete_conditional_redirect', 'conditional_redirect', cr_id, f'qr={qr.slug if qr else "?"}')
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
    if expires_at:
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo
            _parsed = _dt.fromisoformat(expires_at)
            if _parsed.tzinfo is None:
                _parsed = _parsed.replace(tzinfo=ZoneInfo('America/Santiago'))
            qr.expires_at = _parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            qr.expires_at = None
    else:
        qr.expires_at = None

    qr.max_scans = request.form.get('max_scans', type=int)
    if qr.max_scans == 0:
        qr.max_scans = None

    qr.inactive_redirect_url = request.form.get('inactive_redirect_url', '')

    qr.qr_style = request.form.get('qr_style', 'square')
    qr.qr_fg_color = request.form.get('qr_fg_color', '#000000')
    qr.qr_bg_color = request.form.get('qr_bg_color', '#ffffff')
    qr.qr_outer_shape = request.form.get('qr_outer_shape', 'square')
    qr.qr_gradient = request.form.get('qr_gradient', 'none')
    qr.qr_gradient_to = request.form.get('qr_gradient_to', '#1954A2')
    qr.qr_sticker = request.form.get('qr_sticker', 'none')
    qr.qr_transparent_bg = request.form.get('qr_transparent_bg') == 'on'

    # Logo upload
    logo_file = request.files.get('logo')
    if logo_file and logo_file.filename:
        ext = os.path.splitext(logo_file.filename)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            import uuid
            filename = f"{uuid.uuid4().hex}{ext}"
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            logo_file.save(os.path.join(upload_dir, filename))
            qr.logo_filename = filename
    elif request.form.get('remove_logo') == 'on':
        qr.logo_filename = None

    tag_ids = request.form.getlist('tags')
    qr.tags = []
    if tag_ids:
        qr.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

    qr.updated_at = datetime.now(timezone.utc)


# ─── Analytics avanzado (Fase 2) ───

@admin_bp.route('/analytics')
@login_required
def analytics():
    days = min(request.args.get('days', 30, type=int) or 30, 365)

    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=days)

    base_scans = ScanLog.query.join(QRCode).filter(
        QRCode.is_deleted == False,
        ScanLog.scanned_at >= since,
    )
    if not current_user.is_admin:
        base_scans = base_scans.filter(QRCode.user_id == current_user.id)

    # Por dia
    by_day = db.session.query(
        func.date_trunc('day', func.timezone('America/Santiago', ScanLog.scanned_at)).label('day'),
        func.count(ScanLog.id).label('count')
    ).join(QRCode).filter(
        QRCode.is_deleted == False,
        ScanLog.scanned_at >= since,
    )
    if not current_user.is_admin:
        by_day = by_day.filter(QRCode.user_id == current_user.id)
    by_day = by_day.group_by('day').order_by('day').all()

    # Por dispositivo / OS / navegador / hora
    def _grouped(col):
        q = db.session.query(col.label('k'), func.count(ScanLog.id).label('c')) \
            .join(QRCode).filter(
                QRCode.is_deleted == False,
                ScanLog.scanned_at >= since,
            )
        if not current_user.is_admin:
            q = q.filter(QRCode.user_id == current_user.id)
        return q.group_by('k').order_by(func.count(ScanLog.id).desc()).all()

    by_device = _grouped(ScanLog.device_type)
    by_os = _grouped(ScanLog.os_name)
    by_browser = _grouped(ScanLog.browser)

    # Por hora del dia
    by_hour = db.session.query(
        func.extract('hour', func.timezone('America/Santiago', ScanLog.scanned_at)).label('h'),
        func.count(ScanLog.id).label('c')
    ).join(QRCode).filter(
        QRCode.is_deleted == False,
        ScanLog.scanned_at >= since,
    )
    if not current_user.is_admin:
        by_hour = by_hour.filter(QRCode.user_id == current_user.id)
    by_hour = by_hour.group_by('h').order_by('h').all()
    hour_map = {int(r.h): r.c for r in by_hour}
    by_hour_series = [hour_map.get(h, 0) for h in range(24)]

    # Top QRs
    top_qrs = get_user_qrs().filter(QRCode.is_active == True) \
        .order_by(QRCode.scan_count.desc()).limit(10).all()

    # Escaneos con coordenadas para el mapa (ultimos 500)
    map_scans = base_scans.filter(
        ScanLog.latitude.isnot(None),
        ScanLog.longitude.isnot(None),
    ).order_by(ScanLog.scanned_at.desc()).limit(500).all()

    total_scans = base_scans.count()

    # Serie por dia alineada al rango [since, hoy] (para grafico comparativo)
    since_date = since.date() if hasattr(since, 'date') else since
    day_series_full = [0] * days
    for r in by_day:
        rd = r.day.date() if hasattr(r.day, 'date') else r.day
        idx = (rd - since_date).days if rd else None
        if idx is not None and 0 <= idx < days:
            day_series_full[idx] = r.count
    day_labels_full = [str((since_date + __import__('datetime').timedelta(days=i)).isoformat()) for i in range(days)]

    # ── Comparativa con el periodo anterior (misma duracion) ──
    compare = request.args.get('compare') == '1'
    prev_total = prev_by_day = prev_delta_pct = prev_day_series = None
    if compare:
        prev_since = since - __import__('datetime').timedelta(days=days)
        prev_base = ScanLog.query.join(QRCode).filter(
            QRCode.is_deleted == False,
            ScanLog.scanned_at >= prev_since,
            ScanLog.scanned_at < since,
        )
        if not current_user.is_admin:
            prev_base = prev_base.filter(QRCode.user_id == current_user.id)
        prev_total = prev_base.count()
        if prev_total:
            prev_delta_pct = round((total_scans - prev_total) / prev_total * 100, 1)
        else:
            prev_delta_pct = 100.0 if total_scans else 0.0

        prev_day_q = db.session.query(
            func.date_trunc('day', func.timezone('America/Santiago', ScanLog.scanned_at)).label('day'),
            func.count(ScanLog.id).label('count')
        ).join(QRCode).filter(
            QRCode.is_deleted == False,
            ScanLog.scanned_at >= prev_since,
            ScanLog.scanned_at < since,
        )
        if not current_user.is_admin:
            prev_day_q = prev_day_q.filter(QRCode.user_id == current_user.id)
        prev_day_q = prev_day_q.group_by('day').order_by('day').all()
        prev_day_series = [0] * days
        for r in prev_day_q:
            rd = r.day.date() if hasattr(r.day, 'date') else r.day
            idx = (rd - since_date).days + days if rd else None
            if idx is not None and 0 <= idx < days:
                prev_day_series[idx] = r.c

    return render_template('analytics.html',
                         days=days, total_scans=total_scans,
                         by_day=by_day, day_series_full=day_series_full, day_labels_full=day_labels_full,
                         by_device=by_device, by_os=by_os, by_browser=by_browser,
                         by_hour_series=by_hour_series,
                         top_qrs=top_qrs, map_scans=map_scans,
                         compare=compare, prev_total=prev_total,
                         prev_delta_pct=prev_delta_pct, prev_day_series=prev_day_series)


# ─── Auditoria (solo admin) ───

@admin_bp.route('/auditoria')
@admin_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action = request.args.get('action', '').strip()
    q = request.args.get('q', '').strip()

    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if action:
        query = query.filter(AuditLog.action == action)
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                AuditLog.username.ilike(like),
                AuditLog.details.ilike(like),
                AuditLog.entity_type.ilike(like),
            )
        )
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    return render_template('audit_logs.html', logs=pagination.items,
                         pagination=pagination, actions=actions,
                         action=action, q=q)


# ─── Documentacion API (pro) ───

@admin_bp.route('/api-docs')
@admin_required
def api_docs():
    return render_template('api_docs.html')


# ─── Export de escaneos de un QR a CSV ───

@admin_bp.route('/qr/<int:qr_id>/scans/export')
@login_required
def qr_scans_export(qr_id):
    qr = QRCode.query.get_or_404(qr_id)
    _check_owner(qr)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'scanned_at', 'ip_address', 'device_type', 'browser',
                     'os_name', 'country', 'city', 'region', 'latitude', 'longitude',
                     'is_proxy', 'proxy_type', 'redirect_url'])
    for s in qr.scans.order_by(ScanLog.scanned_at.desc()).all():
        writer.writerow([
            s.id,
            s.scanned_at.isoformat() if s.scanned_at else '',
            s.ip_address or '', s.device_type or '', s.browser or '', s.os_name or '',
            s.country or '', s.city or '', s.region or '',
            s.latitude if s.latitude is not None else '',
            s.longitude if s.longitude is not None else '',
            s.is_proxy, s.proxy_type or '', s.redirect_url or '',
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=scans_{qr.slug}.csv'}
    )


# ─── Webhooks (solo admin) ───

@admin_bp.route('/webhooks')
@admin_required
def webhook_list():
    webhooks = Webhook.query.order_by(Webhook.id.desc()).all()
    return render_template('webhooks.html', webhooks=webhooks)


@admin_bp.route('/webhooks/nuevo', methods=['POST'])
@admin_required
def webhook_create():
    url = (request.form.get('url') or '').strip()
    desc = (request.form.get('description') or '').strip()
    if not url.startswith(('http://', 'https://')):
        flash('URL de webhook invalida (debe empezar con http:// o https://).', 'danger')
        return redirect(url_for('admin.webhook_list'))
    wh = Webhook(url=url, description=desc or None, is_active=True)
    db.session.add(wh)
    db.session.commit()
    log_audit('create_webhook', 'webhook', wh.id, f'url={url}')
    flash('Webhook creado. Recibira un POST por cada escaneo.', 'success')
    return redirect(url_for('admin.webhook_list'))


@admin_bp.route('/webhooks/<int:wh_id>/toggle', methods=['POST'])
@admin_required
def webhook_toggle(wh_id):
    wh = Webhook.query.get_or_404(wh_id)
    wh.is_active = not wh.is_active
    db.session.commit()
    log_audit('toggle_webhook', 'webhook', wh.id, f'active={wh.is_active}')
    flash('Webhook {}'.format('activado' if wh.is_active else 'desactivado'), 'success')
    return redirect(url_for('admin.webhook_list'))


@admin_bp.route('/webhooks/<int:wh_id>/test', methods=['POST'])
@admin_required
def webhook_test(wh_id):
    wh = Webhook.query.get_or_404(wh_id)
    try:
        r = requests.post(wh.url, json={'event': 'test', 'message': 'Prueba de webhook desde QR Admin'},
                          timeout=5)
        wh.last_status = r.status_code
        wh.last_error = None if r.status_code < 400 else r.text[:250]
        wh.failures = 0
        flash(f'Webhook respondio HTTP {r.status_code}.', 'success' if r.status_code < 400 else 'danger')
    except Exception as e:
        wh.last_status = 0
        wh.last_error = str(e)[:250]
        wh.failures = (wh.failures or 0) + 1
        flash(f'Error al enviar: {e}', 'danger')
    wh.last_triggered_at = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for('admin.webhook_list'))


@admin_bp.route('/webhooks/<int:wh_id>/eliminar', methods=['POST'])
@admin_required
def webhook_delete(wh_id):
    wh = Webhook.query.get_or_404(wh_id)
    db.session.delete(wh)
    db.session.commit()
    log_audit('delete_webhook', 'webhook', wh.id, f'url={wh.url}')
    flash('Webhook eliminado.', 'success')
    return redirect(url_for('admin.webhook_list'))
