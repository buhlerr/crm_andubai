# Diretrizes Mandatórias para Claude Code

Este projeto adota o arquivo **`AGENTS.md`** como fonte única e central da verdade para padrões de arquitetura, regras de negócio e restrições de agentes de inteligência artificial.

Antes de qualquer intervenção:
1. Leia atentamente as regras e proibições em [`AGENTS.md`](file:///d:/dev/crm_andubai/AGENTS.md).
2. Nunca remova o módulo de Pautas TM, a autenticação local por PBKDF2 ou a leitura rápida via Calamine.
3. Execute os testes proporcionais ao risco da alteração conforme a política de `AGENTS.md`. Rode a suíte completa (`pytest`) antes de merge ou publicação.
