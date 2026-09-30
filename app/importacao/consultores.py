"""Nome do consultor (texto livre na planilha) -> usuário do sistema.

Mesma regra do script do ClickUp: primeiro as exceções manuais (agora
editáveis na tabela apelido_consultor), depois o nome exato, depois a
correspondência parcial, desde que só um usuário bata.
"""

from app.extensions import db
from app.models import ApelidoConsultor, Usuario
from app.texto import normalizar_texto

TEXTOS_SEM_CONSULTOR = {"", "(sem consultor)", "sem consultor", "nan", "-"}


class ResolvedorConsultor:
    def __init__(self):
        self._apelidos = {
            a.texto_normalizado: a.usuario_id for a in db.session.execute(db.select(ApelidoConsultor)).scalars()
        }
        self._usuarios = [
            (normalizar_texto(u.nome), u.id)
            for u in db.session.execute(db.select(Usuario).filter_by(ativo=True)).scalars()
        ]
        self._cache: dict[str, tuple[int | None, str | None]] = {}

    def resolver(self, texto: str | None) -> tuple[int | None, str | None]:
        """Devolve (usuario_id, problema). problema é None quando deu certo
        ou quando o programa está sem consultor de propósito."""
        nome = normalizar_texto(texto)
        if nome not in self._cache:
            self._cache[nome] = self._resolver(nome)
        return self._cache[nome]

    def _resolver(self, nome: str) -> tuple[int | None, str | None]:
        if nome in TEXTOS_SEM_CONSULTOR:
            return None, None
        if nome in self._apelidos:
            return self._apelidos[nome], None
        exatos = [uid for n, uid in self._usuarios if n == nome]
        if len(exatos) == 1:
            return exatos[0], None
        parciais = [uid for n, uid in self._usuarios if n.startswith(nome) or nome in n]
        if len(parciais) == 1:
            return parciais[0], None
        if len(exatos) > 1 or len(parciais) > 1:
            return None, "mais de um usuário tem esse nome"
        return None, "nenhum usuário cadastrado com esse nome"
