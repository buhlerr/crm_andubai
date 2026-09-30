"""Nomes das contagens dos resumos de importação, como aparecem para a equipe."""

RESUMO_BASE = {
    "linhas_importadas": "Linhas válidas",
    "linhas_sem_dados_ignoradas": "Linhas sem dados de aluno (ignoradas)",
    "alunos_novos": "Alunos novos",
    "alunos_renomeados": "Alunos com nome atualizado",
    "programas_novos": "Programas novos",
    "programas_atualizados": "Programas atualizados",
    "programas_sem_mudanca": "Programas sem mudança",
    "programas_reativados": "Programas reativados",
    "programas_cancelados": "Programas cancelados",
    "programas_so_visto_incorporados": "Programas só de visto juntados a um curso",
    "programas_sem_consultor": "Programas sem consultor",
    "compras_ligadas": "Compras ligadas",
    "compras_movidas": "Compras que mudaram de programa",
    "compras_desligadas": "Compras desligadas",
    "erros": "Erros (linhas não importadas)",
    "avisos": "Avisos",
}

RESUMO_CHECKLIST = {
    "linhas_importadas": "Linhas válidas",
    "linhas_sem_dados_ignoradas": "Linhas vazias (ignoradas)",
    "tarefas_novas": "Tarefas novas",
    "tarefas_atualizadas": "Tarefas atualizadas",
    "tarefas_sem_mudanca": "Tarefas sem mudança",
    "tarefas_reabertas": "Tarefas reabertas (voltaram ao checklist)",
    "tarefas_finalizadas": "Tarefas encerradas: finalizadas na Egali",
    "tarefas_canceladas": "Tarefas encerradas: serviço cancelado",
    "tarefas_fora_do_periodo": "Fora do período (não mexidas)",
    "compras_juntadas": "Compras avulsas juntadas a um programa",
    "programas_so_visto_criados": "Programas só de visto criados",
    "alunos_criados": "Alunos criados (só de visto)",
    "itens_ignorados": "Itens de serviços ignorados",
    "itens_sem_programa": "Itens sem programa (não importados)",
    "etapas_criadas": "Procedimentos novos no catálogo",
    "erros": "Erros",
    "avisos": "Avisos",
}

# Listas em resumo["detalhes"] e como mostrar cada uma: (título, colunas [(chave, cabeçalho)]).
DETALHES = {
    "programas_cancelados": ("Programas cancelados (sumiram da planilha)", [("programa_id", "Programa"), ("aluno", "Aluno")]),
    "programas_novos": ("Programas novos", [("programa_id", "Programa"), ("aluno", "Aluno")]),
    "programas_atualizados": ("Programas atualizados", [("programa_id", "Programa"), ("aluno", "Aluno"), ("campos", "O que mudou")]),
    "programas_reativados": ("Programas reativados", [("programa_id", "Programa"), ("aluno", "Aluno")]),
    "alunos_renomeados": ("Alunos com nome atualizado", [("aluno_id", "ID"), ("de", "Antes"), ("para", "Agora")]),
    "programas_so_visto_incorporados": ("Programas só de visto juntados a um curso", [("aluno", "Aluno"), ("programa_id", "Programa")]),
    "tarefas_encerradas": ("Tarefas encerradas (sumiram do checklist)",[("item", "#"), ("aluno", "Aluno"), ("etapa", "Procedimento"), ("motivo", "Motivo")]),
    "itens_sem_programa": ("Compras sem programa", [("compra_id", "Compra"), ("aluno", "Aluno"), ("servico", "Serviço"), ("itens", "Itens"), ("motivo", "Motivo")]),
    "programas_so_visto_criados": ("Programas só de visto criados", [("aluno_id", "ID"), ("aluno", "Aluno")]),
    "etapas_criadas": ("Procedimentos novos no catálogo", None),
}
