from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from itsdangerous import URLSafeSerializer, BadSignature
from flask_login import current_user, login_required
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from email_validator import validate_email, EmailNotValidError
from src.extensions import db
from src.models import Empresa, Cliente, ProdutoServico, Usuario
from src.core.security import roles_required, owned, audit
from src.services.propostas import CLIENT_FIELDS
from src.services.money import decimal_value

gestao_bp = Blueprint('gestao', __name__)


def text_fields(obj, limits):
    for name, limit in limits.items():
        value = request.form.get(name, '').strip()
        if len(value) > limit:
            raise ValueError(f'{name}: limite de {limit} caracteres.')
        setattr(obj, name, value)


@gestao_bp.route('/clientes')
@login_required
def clientes():
    return render_template('cadastros/lista.html', kind='clientes', title='Clientes',
                           rows=Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.nome).all())


@gestao_bp.route('/clientes/novo', methods=['GET', 'POST'])
@gestao_bp.route('/clientes/<int:identifier>/editar', methods=['GET', 'POST'])
@roles_required('admin', 'operador')
def cliente_form(identifier=None):
    obj = owned(Cliente, identifier) if identifier else Cliente(empresa_id=current_user.empresa_id, ativo=True)
    if request.method == 'POST':
        try:
            text_fields(obj, CLIENT_FIELDS)
            if not obj.nome or not obj.telefone:
                raise ValueError('Nome e telefone são obrigatórios.')
            obj.ativo = request.form.get('ativo') == 'on'
            db.session.add(obj)
            db.session.flush()
            audit('editar_cliente' if identifier else 'criar_cliente', 'cliente', obj.id)
            db.session.commit()
            return redirect(url_for('gestao.clientes'))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return render_template('cadastros/form.html', obj=obj, kind='clientes', title='Cliente', fields=CLIENT_FIELDS)


@gestao_bp.route('/itens')
@login_required
def itens():
    return render_template('cadastros/lista.html', kind='itens', title='Produtos e serviços',
                           rows=ProdutoServico.query.filter_by(empresa_id=current_user.empresa_id).order_by(ProdutoServico.descricao).all())


@gestao_bp.route('/itens/novo', methods=['GET', 'POST'])
@gestao_bp.route('/itens/<int:identifier>/editar', methods=['GET', 'POST'])
@roles_required('admin', 'operador')
def item_form(identifier=None):
    obj = owned(ProdutoServico, identifier) if identifier else ProdutoServico(empresa_id=current_user.empresa_id, ativo=True)
    fields = {'codigo': 50, 'descricao': 255, 'unidade': 20}
    if request.method == 'POST':
        try:
            text_fields(obj, fields)
            obj.tipo = request.form.get('tipo')
            obj.valor_unitario = decimal_value(request.form.get('valor_unitario'))
            obj.ativo = request.form.get('ativo') == 'on'
            if not obj.descricao or obj.tipo not in ('P', 'S'):
                raise ValueError('Informe descrição e tipo P/S.')
            db.session.add(obj)
            db.session.flush()
            audit('editar_item' if identifier else 'criar_item', 'produto_servico', obj.id)
            db.session.commit()
            return redirect(url_for('gestao.itens'))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return render_template('cadastros/form.html', obj=obj, kind='itens', title='Produto / serviço', fields=fields)


@gestao_bp.route('/empresa', methods=['GET', 'POST'])
@roles_required('admin')
def empresa():
    obj = db.session.get(Empresa, current_user.empresa_id)
    fields = {'nome': 150, 'razao_social': 150, 'cnpj_cpf': 18, 'endereco': 255, 'telefone': 20, 'email': 120}
    if request.method == 'POST':
        saved = None
        try:
            text_fields(obj, fields)
            if not obj.nome:
                raise ValueError('Nome da empresa é obrigatório.')
            upload = request.files.get('logo')
            if upload and upload.filename:
                with Image.open(upload.stream) as image:
                    if image.width * image.height > 16000000:
                        raise ValueError('Logo deve ter no máximo 16 megapixels.')
                    image.thumbnail((1200, 1200))
                    filename = f'{obj.id}-{uuid4().hex}.png'
                    saved = Path(current_app.config['UPLOAD_FOLDER']) / filename
                    image.convert('RGBA').save(saved, format='PNG')
                    obj.logo = filename
            audit('editar_empresa', 'empresa', obj.id)
            db.session.commit()
            flash('Empresa atualizada.', 'success')
            return redirect(url_for('gestao.empresa'))
        except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            db.session.rollback()
            if saved and saved.exists():
                saved.unlink()
            flash('Não foi possível salvar a empresa. Verifique os campos e a imagem.', 'danger')
    return render_template('cadastros/form.html', obj=obj, kind='empresa', title='Empresa emitente', fields=fields)


@gestao_bp.route('/empresa/logo')
@login_required
def logo():
    filename = current_user.empresa.logo
    if not filename:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@gestao_bp.route('/marca/<token>')
def marca_email(token):
    # Token autoriza somente o arquivo da marca, sem expor cadastros ou outros uploads.
    try:
        filename = URLSafeSerializer(current_app.secret_key, salt='marca-email').loads(token)
    except BadSignature:
        abort(404)
    if not isinstance(filename, str) or '/' in filename or '\\' in filename:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@gestao_bp.route('/usuarios', methods=['GET', 'POST'])
@roles_required('admin')
def usuarios():
    if request.method == 'POST':
        try:
            # Serializa a contagem por empresa para respeitar o limite em cadastros simultâneos.
            account = Empresa.query.filter_by(id=current_user.empresa_id).with_for_update().one()
            if Usuario.query.filter_by(empresa_id=account.id).count() >= account.usuarios_maximos:
                raise ValueError('Limite de usuários da empresa atingido.')
            user = Usuario(empresa_id=account.id)
            text_fields(user, {'nome': 150, 'email': 120, 'usuario': 80})
            user.email = user.email.lower()
            validate_email(user.email, check_deliverability=False)
            user.perfil = request.form.get('perfil')
            password = request.form.get('senha', '')
            if not user.nome or not user.usuario or user.perfil not in ('admin', 'operador', 'visualizador') or len(password) < 8:
                raise ValueError('Preencha todos os campos; senha mínima de 8 caracteres.')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            audit('criar_usuario', 'usuario', user.id)
            db.session.commit()
            flash('Usuário criado.', 'success')
        except (ValueError, EmailNotValidError, IntegrityError) as error:
            db.session.rollback()
            flash('Usuário/e-mail já cadastrado ou dados inválidos. Verifique também o limite da conta.', 'danger')
        return redirect(url_for('gestao.usuarios'))
    return render_template('cadastros/usuarios.html', users=Usuario.query.filter_by(empresa_id=current_user.empresa_id).all())