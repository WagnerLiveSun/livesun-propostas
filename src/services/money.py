from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def decimal_value(value, places='0.01', maximum='9999999999999.99'):
    try:
        text = str(value).strip()
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        number = Decimal(text)
        if not number.is_finite() or number < 0 or number > Decimal(maximum):
            raise ValueError()
        rounded = number.quantize(Decimal(places), rounding=ROUND_HALF_UP)
        if rounded > Decimal(maximum):
            raise ValueError()
        return rounded
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Informe um valor numérico válido, não negativo e dentro do limite.') from None


def numero_por_extenso(valor):
    value = decimal_value(valor)
    units = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
    teens = ['dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
    tens = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
    hundreds = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

    def group(n):
        if n == 100:
            return 'cem'
        if n < 10:
            return units[n]
        if n < 20:
            return teens[n - 10]
        if n < 100:
            return tens[n // 10] + (' e ' + units[n % 10] if n % 10 else '')
        return hundreds[n // 100] + (' e ' + group(n % 100) if n % 100 else '')

    def integer(n):
        parts = []
        for scale, singular, plural in [(10**12, 'trilhão', 'trilhões'), (10**9, 'bilhão', 'bilhões'), (10**6, 'milhão', 'milhões'), (1000, 'mil', 'mil')]:
            amount, n = divmod(n, scale)
            if amount:
                parts.append('mil' if scale == 1000 and amount == 1 else group(amount) + ' ' + (singular if amount == 1 else plural))
        if n:
            parts.append(group(n))
        return ' e '.join(parts)

    reais, cents = divmod(int(value * 100), 100)
    parts = []
    if reais:
        parts.append(integer(reais) + (' de' if reais % 1000000 == 0 else '') + (' real' if reais == 1 else ' reais'))
    if cents:
        parts.append(group(cents) + (' centavo' if cents == 1 else ' centavos'))
    return ' e '.join(parts) or 'zero reais'