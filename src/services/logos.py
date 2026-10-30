"""Logo persistido no banco; arquivos antigos continuam compatíveis."""
from pathlib import Path
from flask import current_app


def company_logo_path(company):
    if not company.logo or '/' in company.logo or '\\' in company.logo:
        return None
    uploads = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    path = (uploads / company.logo).resolve()
    return path if path.parent == uploads and path.is_file() else None


def company_logo_bytes(company):
    if company.logo_dados:
        return bytes(company.logo_dados)
    path = company_logo_path(company)
    if path:
        try:
            return path.read_bytes()
        except OSError:
            current_app.logger.warning('Arquivo de logo indisponível para empresa %s.', company.id)
    return None