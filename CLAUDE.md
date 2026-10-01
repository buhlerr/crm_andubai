# Diretrizes Mandatórias para Claude Code

Este projeto adota o arquivo **`AGENTS.md`** como fonte única e central da verdade para padrões de arquitetura, regras de negócio e restrições de agentes de inteligência artificial.

Antes de qualquer intervenção, execute:
1. Leia atentamente as regras e proibições em [`AGENTS.md`](file:///d:/dev/crm_andubai/AGENTS.md).
2. Nunca remova o módulo de Pautas TM, a autenticação local por PBKDF2 ou a leitura rápida via Calamine.
3. Certifique-se de que todos os 270 testes automatizados (`pytest`) passem antes de concluir qualquer tarefa.
