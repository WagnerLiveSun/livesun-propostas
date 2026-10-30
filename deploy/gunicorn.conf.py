"""Executar na raiz do projeto, como usuário sem privilégios de root."""
bind = '127.0.0.1:8000'
workers = 2
worker_class = 'sync'
timeout = 120
graceful_timeout = 120
accesslog = '-'
errorlog = '-'
capture_output = True