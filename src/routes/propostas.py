from datetime import datetime, timezone
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, current_app
from itsdangerous import URLSafeSerializer
from flask_login import login_required, current_user
from src.extensions import db
from src.core.security import roles_required, owned, audit
from src.models import Proposta, PropostaItem, Cliente, ProdutoServico, EnvioEmail, Auditoria
from src.services.propostas import fill_proposal, new_proposal, save_customer, STATUSES
from src.services.pdf import generate_pdf, render_pdf_html, PDFGenerationError
from src.services.logos import company_logo_bytes
from src.services.envios import finish_delivery
from sqlalchemy.exc import SQLAlchemyError
from src.services.brevo import brevo_service

propostas_bp = Blueprint('propostas', __name__, url_prefix='/propostas')


@propostas_bp.errorhandler(PDFGenerationError)
def pdf_error(error):
    flash(str(error), 'danger')
    return redirect(url_for('propostas.index'))


def filtered_query():
    query = Proposta.query.filter_by(empresa_id=current_user.empresa_id)
    if request.args.get('status') in STATUSES:
        query = query.filter_by(status=request.args['status'])
    if request.args.get('cliente_id', type=int):
        query = query.filter_by(cliente_id=request.args.get('cliente_id', type=int))
    for field, operation in [('inicio', 'start'), ('fim', 'end')]:
        if request.args.get(field):
            try:
                value = datetime.strptime(request.args[field], '%Y-%m-%d').date()
            except ValueError:
                abort(400, 'Data de filtro inválida.')
            query = query.filter(Proposta.data_emissao >= value if operation == 'start' else Proposta.data_emissao <= value)
    return query


@propostas_bp.route('/')
@login_required
def index():
    page = filtered_query().order_by(Proposta.id.desc()).paginate(page=request.args.get('page', 1, type=int), per_page=25)
    return render_template('propostas/lista.html', page=page, statuses=STATUSES,
                           clientes=Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.nome).all())


@propostas_bp.route('/nova', methods=['GET', 'POST'])
@roles_required('admin', 'operador')
def nova():
    return edit_form(new_proposal(), True)


@propostas_bp.route('/<int:identifier>/editar', methods=['GET', 'POST'])
@roles_required('admin', 'operador')
def editar(identifier):
    proposal = owned(Proposta, identifier)
    if proposal.status in ('aceita', 'rejeitada'):
        abort(409, 'Proposta finalizada. Replique para criar uma nova versão.')
    return edit_form(proposal, False)


def edit_form(proposal, creating):
    if request.method == 'POST':
        try:
            fill_proposal(proposal, request.form)
            db.session.add(proposal)
            db.session.flush()
            audit('criar_proposta' if creating else 'editar_proposta', 'proposta', proposal.id)
            db.session.commit()
            flash('Proposta salva.', 'success')
            return redirect(url_for('propostas.detalhe', identifier=proposal.id))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
            return render_template('propostas/form.html', p=proposal, creating=creating, submitted=request.form,
                                   clientes=Cliente.query.filter_by(empresa_id=current_user.empresa_id, ativo=True).all(),
                                   produtos=ProdutoServico.query.filter_by(empresa_id=current_user.empresa_id, ativo=True).all()), 400
    return render_template('propostas/form.html', p=proposal, creating=creating, submitted=None,
                           clientes=Cliente.query.filter_by(empresa_id=current_user.empresa_id, ativo=True).all(),
                           produtos=ProdutoServico.query.filter_by(empresa_id=current_user.empresa_id, ativo=True).all())


@propostas_bp.route('/<int:identifier>')
@login_required
def detalhe(identifier):
    proposal = owned(Proposta, identifier)
    history = Auditoria.query.filter_by(empresa_id=current_user.empresa_id, entidade='proposta', entidade_id=identifier).order_by(Auditoria.id.desc()).all()
    return render_template('propostas/detalhe.html', p=proposal, history=history)


@propostas_bp.route('/<int:identifier>/status', methods=['POST'])
@roles_required('admin', 'operador')
def status(identifier):
    proposal = owned(Proposta, identifier)
    target = request.form.get('status')
    if target not in ('pendente', 'aceita', 'rejeitada') or proposal.status in ('aceita', 'rejeitada'):
        abort(409, 'Transição de status não permitida.')
    if not proposal.cliente_nome or not proposal.cliente_telefone or proposal.itens.count() == 0:
        abort(400, 'A proposta precisa de cliente e itens válidos.')
    if target == 'aceita':
        save_customer(proposal)
        proposal.aprovado_por = current_user.id
        proposal.aprovado_em = datetime.now(timezone.utc).replace(tzinfo=None)
    proposal.status = target
    audit({'aceita': 'aprovar_proposta', 'rejeitada': 'rejeitar_proposta', 'pendente': 'marcar_pendente'}[target], 'proposta', proposal.id)
    db.session.commit()
    flash('Status atualizado.', 'success')
    return redirect(url_for('propostas.detalhe', identifier=identifier))


@propostas_bp.route('/<int:identifier>/replicar', methods=['POST'])
@roles_required('admin', 'operador')
def replicar(identifier):
    original = owned(Proposta, identifier)
    proposal = new_proposal()
    for name in ('subtotal', 'desconto', 'impostos', 'outros_acrescimos', 'total', 'total_extenso', 'observacoes', 'validade', 'condicao_pagamento'):
        setattr(proposal, name, getattr(original, name))
    proposal.cliente_nome = ''
    proposal.cliente_telefone = ''
    if proposal.validade and proposal.validade < proposal.data_emissao:
        proposal.validade = None
    db.session.add(proposal)
    for item in original.itens.order_by(PropostaItem.sequencial):
        proposal.itens.append(PropostaItem(**{name: getattr(item, name) for name in
                             ('sequencial', 'codigo', 'descricao', 'quantidade', 'unidade', 'valor_unitario', 'valor_total')}))
    db.session.flush()
    audit('replicar_proposta', 'proposta', proposal.id)
    db.session.commit()
    flash('Cópia criada como rascunho. Informe o cliente de destino.', 'info')
    return redirect(url_for('propostas.editar', identifier=proposal.id))


@propostas_bp.route('/<int:identifier>/pdf')
@login_required
def pdf(identifier):
    proposal = owned(Proposta, identifier)
    return send_file(BytesIO(generate_pdf(proposal)), mimetype='application/pdf', as_attachment=True,
                     download_name=f'proposta-{proposal.numero}.pdf')


@propostas_bp.route('/<int:identifier>/imprimir')
@login_required
def imprimir(identifier):
    return render_template('propostas/imprimir.html', p=owned(Proposta, identifier))


@propostas_bp.route('/<int:identifier>/enviar', methods=['POST'])
@roles_required('admin', 'operador')
def enviar(identifier):
    from email_validator import validate_email, EmailNotValidError
    proposal = owned(Proposta, identifier)
    recipient = request.form.get('destinatario', '').strip()
    subject = request.form.get('assunto', '').strip()
    message = request.form.get('mensagem', '').strip()
    try:
        validate_email(recipient, check_deliverability=False)
    except EmailNotValidError:
        abort(400, 'Destinatário inválido.')
    if not subject or len(subject) > 255 or len(recipient) > 120 or not proposal.cliente_nome or not proposal.cliente_telefone:
        abort(400, 'Preencha cliente, destinatário e assunto válidos.')
    company_id, user_id = current_user.empresa_id, current_user.id
    try:
        delivery = EnvioEmail(empresa_id=company_id, proposta_id=identifier, destinatario=recipient,
                             assunto=subject, mensagem=message, status='processando')
        db.session.add(delivery)
        db.session.flush()
        delivery_id = delivery.id
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('Falha ao registrar tentativa de envio da proposta %s, empresa %s. Brevo não chamado.',
                                 identifier, company_id)
        flash('Não foi possível registrar a tentativa no banco. Nenhum e-mail foi enviado.', 'danger')
        return redirect(url_for('propostas.detalhe', identifier=identifier))
    try:
        return prepare_and_send(proposal, identifier, company_id, user_id, delivery_id, recipient, subject, message)
    except PDFGenerationError as error:
        db.session.rollback()
        saved = finish_delivery(delivery_id, company_id, user_id, False)
        flash(f'Não foi possível gerar o anexo. Nenhum e-mail foi enviado. {error}', 'danger')
        if not saved:
            flash('A tentativa foi registrada, mas seu resultado não pôde ser atualizado no banco.', 'warning')
        return redirect(url_for('propostas.detalhe', identifier=identifier))


def prepare_and_send(proposal, identifier, company_id, user_id, delivery_id, recipient, subject, message):
    logo_url = None
    missing_logo = False
    if company_logo_bytes(proposal.empresa):
        token = URLSafeSerializer(current_app.secret_key, salt='marca-email').dumps(proposal.empresa.logo)
        logo_url = current_app.config['PUBLIC_BASE_URL'] + url_for('gestao.marca_email', token=token)
    elif proposal.empresa.logo:
        missing_logo = True
    customer_name, number = proposal.cliente_nome, proposal.numero
    email_html = render_template('email/proposta.html', p=proposal, mensagem=message, logo_url=logo_url)
    pdf_html = render_pdf_html(proposal)
    if missing_logo:
        flash('O arquivo do logo não está disponível no servidor. A proposta será enviada sem logo; '
              'acesse Empresa e envie a imagem novamente para os próximos envios.', 'warning')
    # Não manter uma transação remota ociosa durante Chromium ou API externa.
    db.session.rollback()
    attachment = generate_pdf(pdf_html)
    successful = brevo_service.send_transactional_email(recipient, customer_name, subject, email_html,
                    attachment={'name': f'proposta-{number}.pdf', 'content': attachment})
    saved = finish_delivery(delivery_id, company_id, user_id, successful)
    if not saved:
        flash('O Brevo aceitou o e-mail, mas o histórico não pôde ser atualizado. Não reenvie sem conferir o destinatário.'
              if successful else 'O envio falhou e o histórico não pôde ser atualizado. Verifique a conexão com o banco.', 'warning')
    else:
        flash('E-mail enviado.' if successful else 'Envio não concluído. Verifique a configuração exclusiva do Brevo.', 'success' if successful else 'danger')
    return redirect(url_for('propostas.detalhe', identifier=identifier))