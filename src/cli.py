import click
from src.extensions import db
from src.models import Empresa, Usuario


def register_commands(app):
    @app.cli.command('criar-admin')
    @click.option('--empresa', prompt='Nome da empresa')
    @click.option('--nome', prompt='Nome do administrador')
    @click.option('--email', prompt='E-mail')
    @click.option('--usuario', prompt='Usuário')
    @click.option('--senha', prompt=True, hide_input=True, confirmation_prompt=True)
    def criar_admin(empresa, nome, email, usuario, senha):
        """Cria uma conta independente com seu administrador."""
        if len(senha) < 8:
            raise click.ClickException('A senha deve ter pelo menos 8 caracteres.')
        if Usuario.query.filter_by(usuario=usuario).first():
            raise click.ClickException('Usuário já cadastrado.')
        account = Empresa(nome=empresa.strip())
        db.session.add(account)
        db.session.flush()
        user = Usuario(empresa_id=account.id, nome=nome.strip(), email=email.strip().lower(),
                       usuario=usuario.strip(), perfil='admin')
        user.set_password(senha)
        db.session.add(user)
        db.session.commit()
        click.echo('Empresa e administrador criados com sucesso.')