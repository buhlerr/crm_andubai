"""RSA - Checklist do Suporte (APP_Checklist_Suporte_ao_Aluno.html, do modelo base VEG).

O app é um HTML de arquivo único feito por outro analista, com os dados embutidos
(inclusive nomes de colaboradores). Por isso ele nunca vai para o repositório: o
administrador envia o arquivo pela tela e ele fica em instance/rsa/.

O CRM mostra o arquivo num iframe, sem mudar o original guardado. Na hora de servir,
acrescenta no fim um trecho que:
- pula o login próprio do app (quem chega aqui já entrou no CRM);
- esconde o cabeçalho e a barra lateral do app (a navegação é a do CRM);
- abre a página pedida, chamando go(pagina) do próprio app.
"""

import json
import os

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


def _js(valor) -> str:
    # JSON dentro de <script>: "</" quebraria a tag.
    return json.dumps(valor, ensure_ascii=False).replace("</", "<\\/")


def encaixar(html: str, pagina: str, nome_usuario: str, admin: bool) -> str:
    """Devolve o HTML pronto para o iframe, abrindo direto na página pedida."""
    trecho = f"""
<!-- >>> CRM · RSA embutido >>> -->
<style>
  .topbar, nav.sidebar, #login, #loader {{ display: none !important; }}
  #app {{ grid-template-columns: 1fr !important; grid-template-rows: 1fr !important; grid-template-areas: "main" !important; }}
</style>
<script>
(function () {{
  try {{
    if (!DB.appNome) {{ DB.appNome = APP_NOME_PADRAO; saveDB(); }}
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
    return html[:posicao] + trecho + html[posicao:]
