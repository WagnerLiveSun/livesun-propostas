"""
Rotas de autenticação: login, logout, recuperação de senha.
"""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from src.extensions import db
from src.models.usuario import Usuario
from src.services.brevo import brevo_service
from src.core.security import audit

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login do usuário."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        senha = request.form.get('senha')
        remember = request.form.get('remember') == 'on'

        if not usuario or not senha:
            flash('Por favor, informe usuário e senha.', 'warning')
            return render_template('auth/login.html')

        candidates = Usuario.query.filter((Usuario.usuario == usuario) | (Usuario.email == usuario.lower())).all()
        matches = [candidate for candidate in candidates if candidate.is_active and candidate.check_password(senha)]
        user = matches[0] if len(matches) == 1 else None

        if user:
            login_user(user, remember=remember)
            flash(f'Bem-vindo, {user.nome}!', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Logout do usuário."""
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Solicitar recuperação de senha."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email')

        if not email:
            flash('Por favor, informe seu e-mail.', 'warning')
            return render_template('auth/forgot_password.html')

        for user in Usuario.query.filter_by(email=email.strip().lower(), ativo=True).all():
            if not user.is_active:
                continue
            token = secrets.token_urlsafe(32)
            user.reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
            user.reset_expira_em = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
            db.session.commit()
            reset_url = current_app.config['PUBLIC_BASE_URL'] + url_for('auth.reset_password', token=token)
            brevo_service.send_reset_password_email(email, user.nome, reset_url)
        flash('Se o e-mail estiver cadastrado, você receberá instruções.', 'info')

        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Redefinir senha com token."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    digest = hashlib.sha256(token.encode()).hexdigest()
    user = Usuario.query.filter_by(reset_token_hash=digest).first()
    if not user or not user.is_active or not user.reset_expira_em or user.reset_expira_em <= datetime.now(timezone.utc).replace(tzinfo=None):
        flash('Link inválido ou expirado. Solicite uma nova recuperação.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if not nova_senha or not confirmar_senha:
            flash('Por favor, preencha todos os campos.', 'warning')
            return render_template('auth/reset_password.html', token=token)

        if nova_senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if len(nova_senha) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(nova_senha)
        user.reset_token_hash = None
        user.reset_expira_em = None
        db.session.commit()
        flash('Senha redefinida com sucesso! Faça login com sua nova senha.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/perfil')
@login_required
def perfil():
    """Perfil do usuário."""
    return render_template('auth/perfil.html')


@auth_bp.route('/alterar_senha', methods=['POST'])
@login_required
def alterar_senha():
    """Alterar senha do usuário logado."""
    senha_atual = request.form.get('senha_atual')
    nova_senha = request.form.get('nova_senha')
    confirmar_senha = request.form.get('confirmar_senha')

    if not senha_atual or not nova_senha or not confirmar_senha:
        flash('Por favor, preencha todos os campos.', 'warning')
        return redirect(url_for('auth.perfil'))

    if not current_user.check_password(senha_atual):
        flash('Senha atual incorreta.', 'danger')
        return redirect(url_for('auth.perfil'))

    if nova_senha != confirmar_senha:
        flash('As senhas não coincidem.', 'danger')
        return redirect(url_for('auth.perfil'))

    if len(nova_senha) < 8:
        flash('A nova senha deve ter pelo menos 8 caracteres.', 'danger')
        return redirect(url_for('auth.perfil'))

    current_user.set_password(nova_senha)
    current_user.reset_token_hash = None
    current_user.reset_expira_em = None
    audit('alterar_senha', 'usuario', current_user.id)
    db.session.commit()

    flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('auth.perfil'))
