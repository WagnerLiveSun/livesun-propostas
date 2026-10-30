from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from flask_login import current_user
from src.extensions import db
from src.models import Cliente, Proposta, PropostaItem
from src.services.money import decimal_value, numero_por_extenso

CLIENT_FIELDS = {'nome': 150, 'telefone': 20, 'cnpj_cpf': 18, 'email': 120, 'contato': 150, 'endereco': 255}
STATUSES = ('rascunho', 'enviada', 'pendente', 'aceita', 'rejeitada')


def fill_proposal(proposal, form):
    snapshot = {}
    for name, limit in CLIENT_FIELDS.items():
        value = form.get('cliente_' + name, '').strip()
        if len(value) > limit:
            raise ValueError(f'Campo do cliente {name} excede {limit} caracteres.')
        snapshot[name] = value
    if not snapshot['nome'] or not snapshot['telefone']:
        raise ValueError('Nome e telefone do cliente são obrigatórios.')
    customer = None
    if form.get('cliente_id'):
        customer = Cliente.query.filter_by(id=form.get('cliente_id'), empresa_id=current_user.empresa_id).first()
        if not customer:
            raise ValueError('Cliente inválido para esta empresa.')
    try:
        issued = date.fromisoformat(form.get('data_emissao', ''))
        valid = date.fromisoformat(form['validade']) if form.get('validade') else None
    except ValueError:
        raise ValueError('Informe datas válidas.') from None
    if valid and valid < issued:
        raise ValueError('Validade não pode ser anterior à emissão.')
    descriptions = form.getlist('descricao[]')
    columns = {name: form.getlist(name + '[]') for name in ('codigo', 'quantidade', 'unidade', 'valor_unitario')}
    if not descriptions or len(descriptions) > 200 or any(len(values) != len(descriptions) for values in columns.values()):
        raise ValueError('Informe de 1 a 200 itens completos.')
    items = []
    for index, description in enumerate(descriptions):
        description = description.strip()
        if not description or len(description) > 255:
            raise ValueError('Cada item precisa de uma descrição de até 255 caracteres.')
        quantity = decimal_value(columns['quantidade'][index], '0.001', '9999999.999')
        price = decimal_value(columns['valor_unitario'][index])
        if quantity <= 0:
            raise ValueError('Quantidade deve ser maior que zero.')
        code, unit = columns['codigo'][index].strip(), columns['unidade'][index].strip()
        if len(code) > 50 or len(unit) > 20:
            raise ValueError('Código ou unidade excede o tamanho permitido.')
        total = decimal_value((quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        items.append(PropostaItem(sequencial=index + 1, codigo=code, descricao=description,
                                  quantidade=quantity, unidade=unit, valor_unitario=price, valor_total=total))
    subtotal = decimal_value(sum((item.valor_total for item in items), Decimal('0')))
    adjustments = {name: decimal_value(form.get(name, '0') or '0') for name in ('desconto', 'impostos', 'outros_acrescimos')}
    total = subtotal - adjustments['desconto'] + adjustments['impostos'] + adjustments['outros_acrescimos']
    if total < 0:
        raise ValueError('O desconto não pode tornar o total negativo.')
    total = decimal_value(total)
    payment = form.get('condicao_pagamento', '').strip()
    if len(payment) > 500:
        raise ValueError('Condição de pagamento deve ter até 500 caracteres.')
    for name, value in snapshot.items():
        setattr(proposal, 'cliente_' + name, value)
    proposal.cliente_id = customer.id if customer else None
    proposal.data_emissao, proposal.validade = issued, valid
    proposal.observacoes = form.get('observacoes', '').strip()
    proposal.condicao_pagamento = payment
    proposal.subtotal, proposal.total = subtotal, total
    proposal.total_extenso = numero_por_extenso(total)
    for name, value in adjustments.items():
        setattr(proposal, name, value)
    for item in list(proposal.itens):
        db.session.delete(item)
    for item in items:
        proposal.itens.append(item)


def new_proposal():
    return Proposta(empresa_id=current_user.empresa_id, usuario_id=current_user.id,
                    numero=date.today().strftime('%Y') + '-' + uuid4().hex[:16].upper(),
                    status='rascunho', data_emissao=date.today())


def save_customer(proposal):
    query = Cliente.query.filter_by(empresa_id=proposal.empresa_id)
    if proposal.cliente_id:
        customer = query.filter_by(id=proposal.cliente_id).first()
    elif proposal.cliente_cnpj_cpf:
        customer = query.filter_by(cnpj_cpf=proposal.cliente_cnpj_cpf).first()
    else:
        customer = query.filter_by(nome=proposal.cliente_nome, telefone=proposal.cliente_telefone).first()
    if not customer:
        customer = Cliente(empresa_id=proposal.empresa_id)
        db.session.add(customer)
    for name in CLIENT_FIELDS:
        setattr(customer, name, getattr(proposal, 'cliente_' + name))
    db.session.flush()
    proposal.cliente_id = customer.id