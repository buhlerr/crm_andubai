"""Comandos de manutenção. O uso do dia a dia vai ser pelas telas (etapa 4);
estes comandos servem para instalar e testar."""

import click
from flask import Flask

from app.importacao.rotulos import RESUMO_CHECKLIST as ROTULOS_RESUMO_CHECKLIST


def _mostrar_previa(importacao, rotulos):
    periodo = ""
    if importacao.periodo_inicio:
        periodo = f", período {importacao.periodo_inicio:%d/%m/%Y} a {importacao.periodo_fim:%d/%m/%Y}"
    click.echo(f"\nPrévia da importação nº {importacao.id} ({importacao.arquivo_nome}{periodo})")
    for chave, rotulo in rotulos.items():
        click.echo(f"  {rotulo:.<48} {importacao.resumo.get(chave, 0)}")
    campos = importacao.resumo.get("detalhes", {}).get("campos_atualizados")
    if campos:
        click.echo("  O que mudou nas tarefas atualizadas: " + ", ".join(f"{c} ({n})" for c, n in campos.items()))
    if importacao.ocorrencias:
        click.echo("\nErros e avisos:")
        for o in importacao.ocorrencias[:40]:
            onde = f"linha {o.linha}: " if o.linha else ""
            click.echo(f"  [{o.gravidade.value.upper()}] {onde}{o.mensagem}")
        if len(importacao.ocorrencias) > 40:
            click.echo(f"  ... e mais {len(importacao.ocorrencias) - 40}.")


def _confirmar_ou_descartar(importacao, sim, confirmar, descartar):
    from app.importacao import ErroImportacao

    if sim or click.confirm("\nConfirmar e gravar?", default=False):
        try:
            confirmar(importacao)
        except ErroImportacao as erro:
            raise click.ClickException(str(erro)) from erro
        click.echo("Importação gravada.")
    else:
        descartar(importacao)
        click.echo("Importação descartada. Nada foi alterado.")


def registrar_comandos(app: Flask) -> None:
    @app.cli.group("catalogo", help="Trilhas, etapas e serviços.")
    def catalogo():
        pass

    @catalogo.command("carregar", help="Cria as trilhas, etapas e serviços que ainda não existem.")
    def carregar():
        from app.catalogo_inicial import carregar_catalogo

        c = carregar_catalogo()
        click.echo(
            f"Catálogo carregado: {c['trilhas']} trilha(s), {c['etapas']} etapa(s), "
            f"{c['apelidos']} texto(s) de procedimento e {c['servicos']} serviço(s) novos ou classificados."
        )
        if c["reorganizadas"] or c["trilhas_mescladas"]:
            click.echo(f"Reorganização aplicada: {c['reorganizadas']} etapa(s) mudaram de trilha, "
                       f"{c['trilhas_mescladas']} trilha(s) mescladas.")

    @app.cli.command("backup", help="Copia o banco para <dados>/backups e apaga os mais antigos.")
    @click.option("--manter", type=int, help="Quantos backups guardar (padrão: BACKUPS_MANTER, 30).")
    def backup(manter):
        from app.manutencao import ErroManutencao, fazer_backup

        try:
            click.echo(f"Backup salvo em {fazer_backup(app, manter)}")
        except ErroManutencao as erro:
            raise click.ClickException(str(erro)) from erro

    @app.cli.command("diagnostico", help="Confere banco, pasta de dados, segurança e o leitor de planilhas.")
    @click.option("--planilha", type=click.Path(exists=True, dir_okay=False), help="Testa a leitura de uma planilha.")
    @click.option("--sem-excel", is_flag=True, help="Não testa o leitor de planilhas.")
    def diagnostico(planilha, sem_excel):
        from app.manutencao import diagnosticar

        verificacoes = diagnosticar(app, planilha, testar_excel=not sem_excel)
        for v in verificacoes:
            marca = {True: "OK   ", False: "ERRO ", None: "AVISO"}[v.ok]
            click.echo(f"[{marca}] {v.nome}: {v.detalhe}")
        if any(v.ok is False for v in verificacoes):
            raise SystemExit(1)

    @app.cli.command("criar-admin", help="Cria ou promove um usuário para Administrador e define sua senha.")
    @click.option("--nome", prompt="Nome completo", help="Nome do administrador.")
    @click.option("--email", prompt="E-mail", help="E-mail do administrador.")
    @click.option("--senha", prompt=True, hide_input=True, confirmation_prompt=True, help="Senha de acesso.")
    def criar_admin(nome, email, senha):
        from sqlalchemy.exc import IntegrityError
        from app.extensions import db
        from app.models import Papel, Usuario

        email_clean = email.strip().lower()
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email_clean)).scalar_one_or_none()
        if usuario:
            usuario.nome = nome.strip()
            usuario.papel = Papel.ADMIN
            usuario.ativo = True
            usuario.definir_senha(senha)
            click.echo(f"Usuário existente {email_clean} promovido a Administrador e senha atualizada.")
        else:
            usuario = Usuario(nome=nome.strip(), email=email_clean, papel=Papel.ADMIN, ativo=True)
            usuario.definir_senha(senha)
            db.session.add(usuario)
            click.echo(f"Administrador {nome.strip()} <{email_clean}> criado com sucesso.")
        db.session.commit()

    @app.cli.command("redefinir-senha", help="Redefine a senha de um usuário pelo e-mail.")
    @click.argument("email")
    @click.option("--senha", prompt=True, hide_input=True, confirmation_prompt=True, help="Nova senha.")
    def redefinir_senha_cmd(email, senha):
        from app.extensions import db
        from app.models import Usuario

        email_clean = email.strip().lower()
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email_clean)).scalar_one_or_none()
        if not usuario:
            raise click.ClickException(f"Nenhum usuário encontrado com o e-mail {email_clean}.")
        usuario.definir_senha(senha)
        db.session.commit()
        click.echo(f"Senha de {usuario.nome} <{email_clean}> redefinida com sucesso.")

    @app.cli.group("usuarios", help="Cadastro de usuários.")
    def usuarios():
        pass

    @usuarios.command("adicionar")
    @click.argument("nome")
    @click.argument("email")
    @click.option("--papel", type=click.Choice(["consultor", "estagiario", "admin"]), default="consultor")
    @click.option("--senha", help="Senha inicial do usuário.")
    def adicionar_usuario(nome, email, papel, senha):
        from app.extensions import db
        from app.models import Papel, Usuario

        from sqlalchemy.exc import IntegrityError

        novo = Usuario(nome=nome.strip(), email=email.strip().lower(), papel=Papel(papel))
        if senha:
            novo.definir_senha(senha)
        db.session.add(novo)
        try:
            db.session.commit()
        except IntegrityError as erro:
            db.session.rollback()
            raise click.ClickException(f"Já existe um usuário com o e-mail {email.strip().lower()}.") from erro
        click.echo(f"Usuário {nome} cadastrado.")

    @usuarios.command("redefinir-senha")
    @click.argument("email")
    @click.argument("senha")
    def redefinir_senha_usuario(email, senha):
        from app.extensions import db
        from app.models import Usuario

        email_clean = email.strip().lower()
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email_clean)).scalar_one_or_none()
        if not usuario:
            raise click.ClickException(f"Nenhum usuário encontrado com o e-mail {email_clean}.")
        usuario.definir_senha(senha)
        db.session.commit()
        click.echo(f"Senha de {usuario.nome} <{email_clean}> atualizada com sucesso.")

    @usuarios.command("listar")
    def listar_usuarios():
        from app.extensions import db
        from app.models import Usuario

        for u in db.session.execute(db.select(Usuario).order_by(Usuario.nome)).scalars():
            tem_senha = " [com senha]" if u.senha_hash else " [sem senha]"
            click.echo(f"{u.id:4}  {u.nome}  <{u.email}>  {u.papel.value}{tem_senha}{'' if u.ativo else '  (inativo)'}")

    @usuarios.command("apelido", help="Exceção de nome: TEXTO da planilha passa a apontar para o usuário EMAIL.")
    @click.argument("texto")
    @click.argument("email", required=False)
    def apelido(texto, email):
        from app.extensions import db
        from app.models import ApelidoConsultor, Usuario
        from app.texto import normalizar_texto

        usuario = None
        if email:
            usuario = db.session.execute(db.select(Usuario).filter_by(email=email.strip().lower())).scalar_one_or_none()
            if usuario is None:
                raise click.ClickException(f"Nenhum usuário com o e-mail {email}.")
        db.session.add(ApelidoConsultor(texto_planilha=texto, texto_normalizado=normalizar_texto(texto), usuario=usuario))
        db.session.commit()
        click.echo(f"\"{texto}\" -> {usuario.nome if usuario else 'sem consultor'}")

    @app.cli.group("importar", help="Importações.")
    def importar():
        pass

    @importar.command("checklist", help="Importa o relatório de checklist do TM (CSV): alunos, programas, tarefas e painel RSA.")
    @click.argument("caminho", type=click.Path(exists=True, dir_okay=False))
    @click.option("--de", "inicio", help="Início do período exportado (dd/mm/aaaa). Padrão: menor prazo do arquivo.")
    @click.option("--ate", "fim", help="Fim do período exportado (dd/mm/aaaa). Padrão: maior prazo do arquivo.")
    @click.option("--completo", is_flag=True, help="Exportação sem filtro de período: todo item ausente é encerrado.")
    @click.option("--sim", is_flag=True, help="Confirma sem perguntar.")
    def importar_checklist(caminho, inicio, fim, completo, sim):
        from app.importacao import ErroImportacao
        from app.importacao.checklist import confirmar, descartar, importar_arquivo
        from app.importacao.valores import para_data

        try:
            importacao = importar_arquivo(
                caminho, periodo_inicio=para_data(inicio), periodo_fim=para_data(fim), periodo_completo=completo
            )
        except (ErroImportacao, ValueError) as erro:
            raise click.ClickException(str(erro)) from erro
        _mostrar_previa(importacao, ROTULOS_RESUMO_CHECKLIST)
        _confirmar_ou_descartar(importacao, sim, confirmar, descartar)
