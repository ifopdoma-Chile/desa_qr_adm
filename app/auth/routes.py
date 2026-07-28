from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone
from app import db
from app.models import User
from app.auth import auth_bp


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active_user:
            login_user(user, remember=bool(remember))
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            nxt = request.args.get('next')
            return redirect(nxt or url_for('admin.dashboard'))
        flash('Usuario o contrasena incorrectos.', 'danger')
    return render_template('login.html')


@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesion cerrada.', 'info')
    return redirect(url_for('auth.login'))
