"""Entrada WSGI de produção: gunicorn --config deploy/gunicorn.conf.py wsgi:app."""
from src.app import create_app

app = create_app('production')