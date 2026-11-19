from src.extensions import db

# Import all models to register them with SQLAlchemy
from src.models.empresa import Empresa
from src.models.usuario import Usuario
from src.models.cliente import Cliente
from src.models.produto_servico import ProdutoServico
from src.models.proposta import Proposta
from src.models.proposta_item import PropostaItem
from src.models.envio_email import EnvioEmail
from src.models.auditoria import Auditoria
from src.models.cadastro_publico import CadastroPublico, TentativaConfirmacaoEmail
from src.models.solicitacao_central import SolicitacaoCentral
from src.models.commercial_usage import CommercialUsage, TrialProposal, WelcomePreference
from src.services.identidades import register_identity_events

register_identity_events(Empresa, Usuario)

__all__ = [
    'db',
    'Empresa',
    'Usuario',
    'Cliente',
    'ProdutoServico',
    'Proposta',
    'PropostaItem',
    'EnvioEmail',
    'Auditoria',
]