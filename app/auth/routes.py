from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone
import secrets
from app import db, limiter
from app.models import User
from app.auth import auth_bp
from authlib.integrations.flask_client import OAuth

oauth = OAuth()
google = None

# Email que siempre es admin (mismo criterio que modelacion_v2)
ADMIN_EMAIL = 'andres.garcia.fuentes@gmail.com'


def init_oauth(app):
    """Inicializa OAuth con Google si hay credenciales en env."""
    global google
    client_id = app.config.get('GOOGLE_CLIENT_ID', '')
    client_secret = app.config.get('GOOGLE_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        app.logger.warning('Google OAuth no configurado - autenticacion deshabilitada')
        return False

    oauth.init_app(app)
    google = oauth.register(
        name='google',
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'prompt': 'select_account',
        },
    )
    return True


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_LOGIN', '10/minute'))
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active_user:
            if not user.is_approved:
                flash('Tu cuenta esta pendiente de aprobacion del administrador.', 'warning')
                return render_template('login.html')
            login_user(user, remember=bool(remember))
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            nxt = request.args.get('next')
            return redirect(nxt or url_for('admin.dashboard'))
        flash('Usuario o contrasena incorrectos.', 'danger')
    return render_template('login.html')


@auth_bp.route('/login/google')
def google_login():
    """Inicia login con Google."""
    if google is None:
        flash('Google OAuth no configurado.', 'danger')
        return redirect(url_for('auth.login'))
    redirect_uri = url_for('auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route('/login/google/callback')
def google_callback():
    """Callback de Google OAuth."""
    if google is None:
        flash('Google OAuth no configurado.', 'danger')
        return redirect(url_for('auth.login'))

    try:
        token = google.authorize_access_token()
        userinfo = token.get('userinfo')
        if not userinfo:
            userinfo = google.parse_id_token(token)

        email = (userinfo.get('email') or '').strip().lower()
        name = userinfo.get('name') or email.split('@')[0]
        google_id = userinfo.get('sub', '')

        if not email:
            flash('No se pudo obtener el email de Google.', 'danger')
            return redirect(url_for('auth.login'))

        # Buscar por email o google_id
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User.query.filter_by(google_id=google_id).first()

        if not user:
            # Nuevo usuario via Google
            is_admin = (email == ADMIN_EMAIL)
            user = User(
                username=email,
                email=email,
                full_name=name,
                google_id=google_id,
                role=User.ROLE_ADMIN if is_admin else User.ROLE_VIEWER,
                is_active_user=True,
                is_approved=is_admin,  # admin directo; resto requiere aprobacion
            )
            user.set_password(secrets.token_urlsafe(24))  # sin password; login solo via Google
            db.session.add(user)
            db.session.commit()

            if not user.is_approved:
                flash('Cuenta creada. El administrador debe aprobarla antes de ingresar.', 'info')
                return redirect(url_for('auth.login'))
        else:
            # Usuario existente: vincular google_id si no lo tiene
            if not user.google_id:
                user.google_id = google_id
            if email == ADMIN_EMAIL and not user.is_admin:
                user.role = User.ROLE_ADMIN
            if not user.is_approved:
                db.session.commit()
                flash('Tu cuenta esta pendiente de aprobacion del administrador.', 'warning')
                return redirect(url_for('auth.login'))
            if not user.is_active_user:
                db.session.commit()
                flash('Tu cuenta esta desactivada. Contacta al administrador.', 'warning')
                return redirect(url_for('auth.login'))

        login_user(user)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        nxt = request.args.get('next')
        return redirect(nxt or url_for('admin.dashboard'))

    except Exception as e:
        current_app.logger.exception('Error en OAuth callback')
        flash(f'Error al iniciar sesion con Google: {e}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesion cerrada.', 'info')
    return redirect(url_for('auth.login'))
