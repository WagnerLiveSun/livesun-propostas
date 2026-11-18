from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging


class RateLimitSafeFilter(logging.Filter):
    def filter(self, record):
        # A biblioteca inclui chave/IP nos argumentos de mensagens padrão.
        record.msg, record.args = '{"event":"rate_limit_event"}', ()
        record.exc_info, record.exc_text = None, None
        return True


logging.getLogger('flask-limiter').addFilter(RateLimitSafeFilter())


class ConfirmationAccessFilter(logging.Filter):
    def filter(self, record):
        if '/cadastro/confirmar/' in record.getMessage():
            record.msg, record.args = '{"event":"confirmation_http_request"}', ()
            record.exc_info, record.exc_text = None, None
        return True


logging.getLogger('werkzeug').addFilter(ConfirmationAccessFilter())

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
