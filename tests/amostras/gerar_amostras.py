"""Gera as amostras FICTÍCIAS de pautas usadas em tests/test_pautas.py (rode de novo se mudar o formato).

Nenhum dado real: nomes, alunos e números inventados. O formato imita a exportação do TM
(CSV em latin1, separado por ';', cabeçalho começando por "#") e a página salva (tabela HTML).
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
LINHAS = [
    # #, Categoria, Pauta, Status, Consultor, Criado em, Criado por, Atualizado em, Atualizado por, Aluno, Atualizado, TAG
    ("9000001", "MKT - Criação de material - ", "9000001 - AC-SA-AND - Aluno Ficticio Um - Escola Exemplo (Toronto) - 01/10/2026",
     "Em aberto", "Pessoa Acomodacao", "28/09/2026 10:00:00", "Consultora Ana", "29/09/2026 09:00:00", "Pessoa Acomodacao",
     "", "50:10:00", "Atrasada 72h +"),
    ("9000002", "DOF - Pauta com diretor operacional", "Visto negado - Aluna Ficticia Dois",
     "Em aberto", "Consultora Ana", "25/09/2026 08:00:00", "Pessoa Acomodacao", "29/09/2026 15:00:00", "Consultora Ana",
     "", "10:00:00", "Atrasada"),
    ("9000003", "Categoria Sem Prazo", "9000003 - AC-SA-AND - Aluno Ficticio Tres - Escola Exemplo (Dubai) - 01/10/2026",
     "Finalizando", "Consultora Ana", "30/09/2026 11:00:00", "Consultora Ana", "30/09/2026 12:00:00", "Consultora Ana",
     "Aluno Ficticio Tres", "02:00:00", ""),
]
CAB = ["#", "Categoria", "Pauta", "Status", "Consultor", "Criado em", "Criado por", "Atualizado em", "Atualizado por",
       "Aluno", "Atualizado", "TAG"]

if __name__ == "__main__":
    csv = ";".join(f'"{c}"' for c in CAB) + "\r\n" + "".join(";".join(f'"{v}"' for v in l) + "\r\n" for l in LINHAS)
    with open(os.path.join(AQUI, "pautas_exemplo.csv"), "wb") as f:
        f.write(csv.encode("latin1"))
    tds = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in (l[0], l[1], l[2], l[3], l[4], f"{l[5]} por {l[6]}", f"{l[7]} por {l[8]}",
                                                    l[9], l[10], l[11])) + "</tr>\n"
        for l in LINHAS)
    html = f"<html><body><table><tr><th>#</th><th>Categoria</th></tr>\n{tds}</table></body></html>\n"
    with open(os.path.join(AQUI, "pautas_exemplo.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("amostras geradas")
