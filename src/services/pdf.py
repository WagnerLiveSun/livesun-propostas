"""PDF gerado pelo navegador a partir do mesmo template da impressão."""
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from flask import current_app, render_template, has_request_context


class PDFGenerationError(RuntimeError):
    pass


def find_browser():
    configured = current_app.config.get('PDF_BROWSER_PATH', '')
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise PDFGenerationError('PDF_BROWSER_PATH não aponta para um navegador válido.')
        return str(path)
    candidates = []
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if os.environ.get(variable):
            root = Path(os.environ[variable])
            candidates.extend([root / 'Google/Chrome/Application/chrome.exe',
                               root / 'Microsoft/Edge/Application/msedge.exe'])
    for command in ('google-chrome', 'chromium', 'chromium-browser', 'msedge', 'chrome'):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return str(path)
    raise PDFGenerationError('Instale Chrome/Edge ou configure PDF_BROWSER_PATH para gerar o PDF.')


def render_pdf_html(proposal):
    """Reutiliza integralmente a impressão e embute os recursos locais."""
    static = Path(current_app.static_folder)
    uploads = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    logo_url = ''
    if proposal.empresa.logo:
        logo = (uploads / proposal.empresa.logo).resolve()
        if logo.parent != uploads or not logo.is_file():
            raise PDFGenerationError('Logo da empresa não encontrado na pasta de uploads.')
        logo_url = 'data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode('ascii')
    html = render_template('propostas/imprimir.html', p=proposal, proposal_logo_url=logo_url)
    bootstrap = (static / 'vendor/bootstrap/bootstrap.min.css').read_text(encoding='utf-8')
    styles = (static / 'css/style.css').read_text(encoding='utf-8')
    # Sem chamadas HTTP, sessão compartilhada ou conteúdo executável durante a geração.
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    html = re.sub(r'<link\b[^>]*>', '', html, flags=re.I)
    html = re.sub(r'<img\b(?=[^>]*class="(?:developer-logo|footer-logo)")[^>]*>', '', html, flags=re.I)
    html = html.replace('</head>', f'<style>{bootstrap}\n{styles}</style></head>')
    policy = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:">'
    return html.replace('<head>', '<head>' + policy, 1)


def generate_pdf(proposal):
    browser = find_browser()
    if has_request_context():
        html = render_pdf_html(proposal)
    else:
        with current_app.test_request_context('/'):
            html = render_pdf_html(proposal)
    with tempfile.TemporaryDirectory(prefix='livesun-pdf-') as folder:
        root = Path(folder)
        source = root / 'proposta.html'
        output = root / 'proposta.pdf'
        source.write_text(html, encoding='utf-8')
        command = [browser, '--headless', '--disable-gpu', '--disable-dev-shm-usage', '--disable-extensions',
                   '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                   '--no-pdf-header-footer', '--timeout=20000',
                   f'--user-data-dir={root / "profile"}', f'--print-to-pdf={output}', source.as_uri()]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PDFGenerationError('Não foi possível concluir a geração do PDF no navegador.') from error
        if result.returncode != 0 or not output.is_file():
            raise PDFGenerationError('O navegador não gerou o PDF. Verifique a instalação do Chrome/Edge.')
        data = output.read_bytes()
        if not data.startswith(b'%PDF'):
            raise PDFGenerationError('O navegador retornou um arquivo PDF inválido.')
        return data