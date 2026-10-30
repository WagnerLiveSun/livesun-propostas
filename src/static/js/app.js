document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'moonlight' ? 'bluemetal' : 'moonlight';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('ls-theme', next); } catch (_) { /* armazenamento indisponível */ }
});

const sidebarToggle = document.getElementById('sidebar-toggle');
if (sidebarToggle) {
    const setSidebarOpen = open => {
        document.body.classList.toggle('sidebar-open', open);
        sidebarToggle.setAttribute('aria-expanded', String(open));
    };
    sidebarToggle.addEventListener('click', () => {
        setSidebarOpen(!document.body.classList.contains('sidebar-open'));
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
            setSidebarOpen(false);
            sidebarToggle.focus();
        }
    });
    window.matchMedia('(max-width: 991px)').addEventListener('change', () => setSidebarOpen(false));
}

const form = document.getElementById('proposal-form');
if (form) {
    const body = document.getElementById('items-body');
    const money = value => value.toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
    const calculate = () => {
        let subtotal = 0;
        body.querySelectorAll('tr').forEach((row, i) => {
            row.querySelector('.sequence').textContent = i + 1;
            const quantity = Number(row.querySelector('[name="quantidade[]"]').value) || 0;
            const price = Number(row.querySelector('[name="valor_unitario[]"]').value) || 0;
            const cents = Math.round((quantity * price + Number.EPSILON) * 100);
            subtotal += cents;
            row.querySelector('.line-total').textContent = money(cents / 100);
        });
        const adjustment = name => Math.round((Number(form.elements[name].value) || 0) * 100);
        const total = subtotal - adjustment('desconto') + adjustment('impostos') + adjustment('outros_acrescimos');
        document.getElementById('grand-total').textContent = 'Total estimado: ' + money(total / 100);
    };
    const addRow = (data = {}) => {
        const row = document.createElement('tr');
        const seq = document.createElement('td'); seq.className = 'sequence'; row.append(seq);
        for (const [name, value, limit] of [['codigo',data.codigo || '',50],['descricao',data.descricao || '',255],['quantidade',1,null],['unidade',data.unidade || '',20],['valor_unitario',data.valor || 0,null]]) {
            const cell = document.createElement('td');
            const input = document.createElement('input');
            input.className = 'form-control' + (name === 'descricao' ? ' description' : '');
            input.name = name + '[]'; input.value = value;
            if (limit) input.maxLength = limit;
            if (['quantidade','valor_unitario'].includes(name)) {
                input.type = 'number'; input.step = name === 'quantidade' ? '0.001' : '0.01';
                input.min = name === 'quantidade' ? '0.001' : '0';
            }
            input.required = ['descricao','quantidade','valor_unitario'].includes(name);
            cell.append(input); row.append(cell);
        }
        const total = document.createElement('td'); total.className = 'line-total'; row.append(total);
        const action = document.createElement('td'); const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-outline-danger remove-item'; button.textContent = '×';
        button.setAttribute('aria-label','Remover item'); action.append(button); row.append(action); body.append(row);
        calculate();
    };
    document.getElementById('add-item').addEventListener('click', () => addRow());
    document.getElementById('add-product').addEventListener('click', () => {
        const select = document.getElementById('product-select');
        if (select.selectedIndex > 0) addRow(select.selectedOptions[0].dataset);
    });
    body.addEventListener('click', event => {
        if (event.target.closest('.remove-item')) { event.target.closest('tr').remove(); calculate(); }
    });
    form.addEventListener('input', calculate);
    document.getElementById('customer-select').addEventListener('change', event => {
        const data = event.target.selectedOptions[0].dataset;
        for (const name of ['nome','telefone','cnpj_cpf','email','contato','endereco']) {
            document.getElementById('cliente_' + name).value = data[name] || '';
        }
    });
    if (!body.children.length) addRow(); else calculate();
}