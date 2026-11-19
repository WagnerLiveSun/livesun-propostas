"""Testes não podem enviar mensagens nem acessar serviços de produção."""
import pytest


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise RuntimeError('HTTP externo bloqueado durante testes; utilize mock.')
    monkeypatch.setattr('requests.sessions.Session.request', blocked)