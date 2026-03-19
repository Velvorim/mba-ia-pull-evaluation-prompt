# Checklist de Entrega Final

## Itens do repositório

- Repositório com implementação completa do fluxo de pull, push e avaliação de prompts
- Prompt otimizado em `prompts/bug_to_user_story_v2.yml`
- Testes automatizados em `tests/test_prompts.py`
- README consolidando técnicas, execução e evidências

## Evidências principais

- Dashboard do projeto no LangSmith (link na seção **Resultados Finais** do `README.md`)
- Prompt publicado no LangSmith Hub: `velvor/bug_to_user_story_v2`
- Capturas em `docs/screenshots/` (índice em [screenshots/README.md](screenshots/README.md)):

| Arquivo | Link | Descrição |
|---------|------|------------|
| Retorno da avaliação | [retorno-medias-aprovadas.png](screenshots/retorno-medias-aprovadas.png) | Saída do `evaluate.py` — APROVADO |
| Dashboard / trace | [dashboard-trace.png](screenshots/dashboard-trace.png) | Projeto no LangSmith |
| Avaliação v1 (baixa) | [avaliacao-v1-baixa-nota.png.png](screenshots/avaliacao-v1-baixa-nota.png.png) | Notas baixas v1 |
| Avaliação v2 (aprovado) | [avaliacao-v2-aprovado.png.png](screenshots/avaliacao-v2-aprovado.png.png) | Métricas ≥ 0,9 |
| Tracing — dashboard | [tracing-dashboard.png](screenshots/tracing-dashboard.png) | Visão do run |
| Tracing — Tone | [tracing-tone.png](screenshots/tracing-tone.png) | Avaliador Tone |
| Tracing — Acceptance | [tracing-acceptance.png](screenshots/tracing-acceptance.png) | Avaliador Acceptance |
| Tracing — Format | [tracing-format.png](screenshots/tracing-format.png) | Avaliador Format |
| Tracing — Completeness | [tracing-completeness.png](screenshots/tracing-completeness.png) | Avaliador Completeness |

## Observação sobre configuração

- A rodada documentada foi obtida com o modelo `gemini-3.1-flash-lite-preview`
- O dataset de avaliação possui 15 exemplos (`datasets/bug_to_user_story.jsonl`).
- Métricas de aprovação: Tone, Acceptance Criteria, User Story Format e Completeness ≥ 0,9; média ≥ 0,9.

## Fechamento recomendado

- Links do dashboard e do prompt no `README.md` (seção **Resultados Finais**)
- Capturas em `docs/screenshots/`
