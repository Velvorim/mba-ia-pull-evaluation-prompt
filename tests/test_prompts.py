"""
Testes automatizados para validação de prompts.
Garantem estrutura e conteúdo do prompt ANTES de rodar avaliação com o modelo.

Fluxo recomendado:
1. pytest tests/test_prompts.py     → validação estática (sem chamar LLM)
2. (opcional) Avaliação rápida com poucos exemplos (Linux/Mac: EVAL_MAX_EXAMPLES=4 python src/evaluate.py --local | Windows: set EVAL_MAX_EXAMPLES=4 && python src/evaluate.py --local):
   → testa 4 bugs no prompt local; ainda chama o modelo, mas bem mais rápido que 15.
3. python src/push_prompts.py && python src/evaluate.py  → avaliação completa
"""
import pytest
import yaml
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
V2_PATH = PROMPTS_DIR / "bug_to_user_story_v2.yml"


def _load_prompt_block():
    """Carrega o primeiro bloco de prompt do YAML (bug_to_user_story_v2)."""
    with open(V2_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        raise FileNotFoundError(f"Arquivo vazio ou inválido: {V2_PATH}")
    for key, value in data.items():
        if isinstance(value, dict) and ("system_prompt" in value or "user_prompt" in value):
            return value
    raise ValueError(f"Nenhum bloco de prompt encontrado em {V2_PATH}")


class TestPrompts:
    """Testes estáticos: não chamam o modelo, validam YAML e texto do prompt."""

    def test_prompt_has_system_prompt(self):
        """Verifica se o campo 'system_prompt' existe e não está vazio."""
        block = _load_prompt_block()
        assert "system_prompt" in block, "Campo 'system_prompt' não encontrado"
        sp = (block.get("system_prompt") or "").strip()
        assert len(sp) > 100, "system_prompt está vazio ou muito curto"

    def test_prompt_has_role_definition(self):
        """Verifica se o prompt define uma persona (ex: 'Você é um', 'Como um')."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        has_role = (
            "Você é" in sp
            or "Como um" in sp
            or "analista" in sp.lower()
            or "product manager" in sp.lower()
            or "persona" in sp.lower()
        )
        assert has_role, "Prompt deve definir persona/role (ex: 'Você é um...', 'Como um...')"

    def test_prompt_mentions_format(self):
        """Verifica se o prompt exige formato User Story padrão ou estrutura clara."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        has_format = (
            "Como um" in sp
            and "eu quero" in sp.lower()
            and "para que" in sp.lower()
            and ("Critérios de Aceitação" in sp or "critérios de aceitação" in sp.lower())
        )
        assert has_format, "Prompt deve exigir formato User Story (Como um... eu quero... para que... + Critérios)"

    def test_prompt_has_few_shot_examples(self):
        """Verifica se o prompt contém exemplos de entrada/saída (técnica Few-shot)."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        has_example = (
            "Exemplo" in sp or "exemplo" in sp.lower()
        ) and (
            "Entrada:" in sp or "Saída:" in sp or "entrada" in sp.lower()
        )
        assert has_example, "Prompt deve conter exemplos Few-shot (Entrada/Saída ou Exemplo)"

    def test_prompt_no_todos(self):
        """Garante que você não esqueceu nenhum [TODO] no texto."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        up = (block.get("user_prompt") or "").strip()
        combined = sp + "\n" + up
        assert "[TODO]" not in combined and "TODO:" not in combined, "Remova todos os [TODO] do prompt"

    def test_minimum_techniques(self):
        """Verifica (metadados do YAML) se pelo menos 2 técnicas foram listadas."""
        block = _load_prompt_block()
        techniques = block.get("techniques_applied") or block.get("techniques") or []
        if isinstance(techniques, str):
            techniques = [techniques]
        assert len(techniques) >= 2, (
            f"Mínimo de 2 técnicas requeridas no YAML (techniques_applied/techniques). Encontradas: {len(techniques)}"
        )


class TestPromptContent:
    """Testes de conteúdo mínimo para alinhar com as métricas (Tone, Acceptance, Completeness)."""

    def test_mentions_benefit_para_que(self):
        """Garante que o prompt orienta o benefício na frase 'para que' (Tone)."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        assert "para que" in sp.lower(), "Prompt deve orientar o uso de 'para que' (benefício)"
        assert "benefício" in sp.lower() or "eu possa" in sp, "Prompt deve reforçar benefício concreto / 1ª pessoa"

    def test_mentions_minimum_criteria(self):
        """Garante que o prompt exige quantidade mínima de critérios (Acceptance)."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        assert "6" in sp or "seis" in sp.lower(), "Prompt deve exigir mínimo de critérios (ex.: 6)"

    def test_mentions_contexto_do_bug(self):
        """Garante que o prompt exige Contexto do Bug quando há detalhes (Completeness)."""
        block = _load_prompt_block()
        sp = (block.get("system_prompt") or "").strip()
        assert "Contexto do Bug" in sp or "Contexto Técnico" in sp or "Contexto de Segurança" in sp, (
            "Prompt deve exigir seção de contexto (Contexto do Bug / Técnico / Segurança) quando aplicável"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
