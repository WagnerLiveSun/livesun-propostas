import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
threads = 2
timeout = 120
graceful_timeout = 120
# Não registrar paths de confirmação/recuperação contendo tokens.
accesslog = None
errorlog = '-'
capture_output = True


def on_starting(server):
    from src.services.central_migration import before_server_start
    before_server_start(server)