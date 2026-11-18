"""RSA - Checklist do Suporte (APP_Checklist_Suporte_ao_Aluno.html, do modelo base VEG).

O app é um HTML de arquivo único feito por outro analista, com os dados embutidos
(inclusive nomes de colaboradores). Por isso ele nunca vai para o repositório: o
administrador envia o arquivo pela tela e ele fica em instance/rsa/.

Os dados do painel vêm do relatório de checklist do ano, importado em Administração →
Importações (app/importacao/rsa_checklist.py). Na hora de servir, o CRM troca a base
embutida no HTML (DADOS_CHECKLIST) pela base gerada desse relatório; sem relatório
importado, vale a base que veio no HTML. O HTML guardado funciona só como layout.

O CRM mostra o arquivo num iframe, sem mudar o original guardado. Na hora de servir,
acrescenta no fim um trecho que:
- pula o login próprio do app (quem chega aqui já entrou no CRM);
- esconde o cabeçalho e a barra lateral do app (a navegação é a do CRM);
- abre a página pedida, chamando go(pagina) do próprio app.
"""

import json
import os
import re

from app.importacao.rsa_checklist import EXECUTOR_EM_ABERTO
from app.models.base import agora, hora_local

# Grupo 1 do app: todos veem. As chaves são as de go(page) no HTML.
PAGINAS_DADOS = {
    "visao": "Visão Geral",
    "procedimentos": "Procedimentos",
    "pessoas": "Executores e Consultores",
    "programas": "Programas e Vistos",
    "atrasos": "Prazos e Atrasos",
}
# Grupo Sistema do app: só administradores.
PAGINAS_SISTEMA = {
    "credenciais": "Credenciais",
    "envio": "Envio de Arquivos",
    "manual": "Manual de Instrução",
    "melhorias": "Melhorias",
    "testes": "Testes",
}
PAGINAS = {**PAGINAS_DADOS, **PAGINAS_SISTEMA}


# O app roda isolado do CRM: scripts, formulários, alertas, abas e downloads, mas NUNCA allow-same-origin
# (com ele, o HTML enviado voltaria a ter acesso à origem do CRM).
SANDBOX = "allow-scripts allow-forms allow-modals allow-popups allow-downloads"

# Na origem isolada, localStorage/sessionStorage dão erro. O app usa o localStorage (saveDB): troca por uma
# versão em memória, que vale enquanto a página estiver aberta. Vai no começo do HTML, antes dos scripts do app.
ARMAZENAMENTO_EM_MEMORIA = """<script>
(function () {
  function memoria() {
    var d = {};
    return {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(d, k) ? d[k] : null; },
      setItem: function (k, v) { d[k] = String(v); },
      removeItem: function (k) { delete d[k]; },
      clear: function () { d = {}; },
      key: function (i) { return Object.keys(d)[i] || null; },
      get length() { return Object.keys(d).length; }
    };
  }
  ["localStorage", "sessionStorage"].forEach(function (nome) {
    try { window[nome].getItem("x"); }
    catch (e) { try { Object.defineProperty(window, nome, {value: memoria(), configurable: true}); } catch (e2) {} }
  });
})();
</script>"""


class ErroRSA(Exception):
    pass


def _pasta() -> str:
    from flask import current_app

    pasta = os.path.join(current_app.instance_path, "rsa")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def validar(html: str) -> str:
    """Confere se é o app do modelo base VEG (precisa de go(page) e revealApp para o encaixe)."""
    for trecho in ("function go(", "function revealApp(", 'id="login"', "</body>"):
        if trecho not in html:
            raise ErroRSA("Este arquivo não parece ser o APP Checklist do Suporte ao Aluno (modelo base VEG). "
                          "Envie o HTML exatamente como foi baixado do próprio app.")
    return html


def guardar(conteudo: bytes, nome_original: str, usuario: str) -> dict:
    try:
        html = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroRSA("O arquivo não está em UTF-8. Envie o HTML exatamente como foi baixado do app.")
    validar(html)
    info = {
        "nome_original": nome_original,
        "enviado_em": hora_local(agora()).strftime("%d/%m/%Y %H:%M"),
        "enviado_por": usuario,
        "tamanho_kb": round(len(conteudo) / 1024),
    }
    pasta = _pasta()
    with open(os.path.join(pasta, "app.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(pasta, "app.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    return info


def info_guardada() -> dict | None:
    pasta = _pasta()
    if not os.path.exists(os.path.join(pasta, "app.html")):
        return None
    try:
        with open(os.path.join(pasta, "app.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def html_guardado() -> str | None:
    caminho = os.path.join(_pasta(), "app.html")
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as f:
        return f.read()


MARCA_BASE = "const DADOS_CHECKLIST = "

# Textos do app que falam só de "finalizados": com os em aberto na base, mudam na hora de mostrar.
TEXTOS_COM_EM_ABERTO = {
    "['per','Período do relatório']": "['per','Situação (finalizado ou em aberto)']",
    "['mes','Mês de finalização']": "['mes','Mês (finalização ou prazo)']",
    "Comparação entre os períodos carregados": "Finalizados e em aberto",
    "clique em um período para filtrar o painel": "clique em uma situação para filtrar o painel",
    "<th>Período</th>": "<th>Situação</th>",
    "'finalizados no período'": "'finalizados e em aberto'",
    "Cada registro é um procedimento da jornada do aluno\n     finalizado pela equipe de Suporte ao Aluno.":
        "Cada registro é um procedimento da jornada do aluno\n     do Suporte ao Aluno, finalizado ou em aberto.",
    "A base traz apenas itens já finalizados,\n     então o que se mede aqui é pontualidade, não backlog.":
        "Nos procedimentos em aberto, o atraso é contado até a data da importação do relatório (backlog);\n     use o filtro Situação para separar.",
}


def aceita_base(html: str) -> bool:
    """O HTML tem a declaração `const DADOS_CHECKLIST = {...}` que o CRM troca pela base importada?"""
    inicio = html.find(MARCA_BASE)
    if inicio < 0:
        return False
    try:
        json.JSONDecoder().raw_decode(html[inicio + len(MARCA_BASE):])
    except ValueError:
        return False
    return True


AVISO_SEM_BASE = ("O HTML do RSA guardado não tem a base de dados no formato esperado (const DADOS_CHECKLIST = {...}): "
                  "o painel mostra os dados que vieram dentro do HTML, não os do relatório de checklist importado. "
                  "Envie o HTML exatamente como foi baixado do app.")


def _trocar_base(html: str, base: dict) -> str:
    """Troca o objeto DADOS_CHECKLIST do HTML pela base do relatório importado."""
    inicio = html.find(MARCA_BASE)
    if inicio < 0:
        return html
    inicio += len(MARCA_BASE)
    try:
        _, tamanho = json.JSONDecoder().raw_decode(html[inicio:])
    except ValueError:
        return html
    html = html[:inicio] + _js(base) + html[inicio + tamanho:]
    for antes, depois in TEXTOS_COM_EM_ABERTO.items():
        html = html.replace(antes, depois)
    return html


def _js(valor) -> str:
    # JSON dentro de <script>: "</" quebraria a tag.
    return json.dumps(valor, ensure_ascii=False).replace("</", "<\\/")


def encaixar(html: str, pagina: str, nome_usuario: str, admin: bool, base: dict | None = None) -> str:
    """Devolve o HTML pronto para o iframe, abrindo direto na página pedida.
    Com `base` (relatório de checklist importado), os dados do painel passam a ser os dela."""
    patch_base = ""
    if base is not None:
        html = _trocar_base(html, base)
        # "Quem mais finaliza" e as tabelas de executor não contam os em aberto (ninguém finalizou ainda).
        patch_base = f"""
    if (typeof agregaCH === "function") {{
      const agregaOriginal = agregaCH, semExecutor = {_js(EXECUTOR_EM_ABERTO)};
      agregaCH = function (dim, rows) {{
        const g = agregaOriginal(dim, rows);
        return dim === "exec" ? g.filter(o => o.rot !== semExecutor) : g;
      }};
    }}"""
    trecho = f"""
<!-- >>> CRM · RSA embutido >>> -->
<style>
  .topbar, nav.sidebar, #login, #loader {{ display: none !important; }}
  #app {{ grid-template-columns: 1fr !important; grid-template-rows: 1fr !important; grid-template-areas: "main" !important; }}
</style>
<script>
(function () {{
  try {{
    if (!DB.appNome) {{ DB.appNome = APP_NOME_PADRAO; saveDB(); }}{patch_base}
    SESSION = {{nome: {_js(nome_usuario)}, email: "", perfil: {_js("Master" if admin else "Leitura")}, ativo: true}};
    activePage = {_js(pagina)};
    revealApp(SESSION);
  }} catch (e) {{
    document.body.insertAdjacentHTML("afterbegin",
      "<p style='padding:20px;font-family:sans-serif'>Não consegui abrir esta página do RSA. "
      + "Peça para um administrador enviar o HTML de novo.</p>");
  }}
}})();
</script>
<!-- <<< CRM · RSA embutido <<< -->
"""
    posicao = html.rfind("</body>")
    html = html[:posicao] + trecho + html[posicao:]
    # Logo depois de <head> (ou de <body>, se não houver head): antes de qualquer script do app.
    abertura = re.search(r"<head(?:\s[^>]*)?>", html, re.IGNORECASE) or re.search(r"<body(?:\s[^>]*)?>", html, re.IGNORECASE)
    inicio = abertura.end() if abertura else 0
    return html[:inicio] + ARMAZENAMENTO_EM_MEMORIA + html[inicio:]
