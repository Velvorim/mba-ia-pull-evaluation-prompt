"""
Script para fazer push de prompts otimizados ao LangSmith Prompt Hub.

Este script:
1. Lê os prompts de prompts/bug_to_user_story_v2.yml
2. Valida os prompts
3. Faz push PÚBLICO para o LangSmith Hub
4. Adiciona metadados (tags, descrição, técnicas utilizadas)
"""

import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from utils import load_yaml, check_env_vars, print_section_header

load_dotenv()

PROMPT_FILE = "prompts/bug_to_user_story_v2.yml"
PROMPT_NAME = "bug_to_user_story_v2"


def slugify_username(name: str) -> str:
    """Converte nome para slug (ex: 'Vitor Hugo' -> 'vitor-hugo')."""
    if not name or not name.strip():
        return "my-prompts"
    s = re.sub(r"[^\w\s-]", "", name.strip().lower())
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s or "my-prompts"


def validate_prompt(prompt_data: dict) -> tuple[bool, list]:
    """
    Valida estrutura básica de um prompt.

    Args:
        prompt_data: Dados do prompt (conteúdo sob a chave do prompt no YAML)

    Returns:
        (is_valid, errors) - Tupla com status e lista de erros
    """
    errors = []

    if not prompt_data:
        return False, ["Prompt vazio"]

    if not prompt_data.get("system_prompt", "").strip():
        errors.append("Campo 'system_prompt' está vazio ou ausente")
    if "TODO" in (prompt_data.get("system_prompt") or ""):
        errors.append("Remova todos os [TODO] do system_prompt")

    techniques = prompt_data.get("techniques_applied", [])
    if not isinstance(techniques, list):
        errors.append("'techniques_applied' deve ser uma lista")
    elif len(techniques) < 2:
        errors.append(f"Mínimo de 2 técnicas em 'techniques_applied', encontradas: {len(techniques)}")

    return (len(errors) == 0, errors)


def build_prompt_template(prompt_data: dict) -> ChatPromptTemplate:
    """Constrói ChatPromptTemplate a partir do dict do YAML (system_prompt + user_prompt)."""
    system_prompt = (prompt_data.get("system_prompt") or "").strip()
    user_prompt = (prompt_data.get("user_prompt") or prompt_data.get("human_prompt") or "{bug_report}").strip()
    if not user_prompt.strip():
        user_prompt = "{bug_report}"

    return ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system_prompt),
        HumanMessagePromptTemplate.from_template(user_prompt),
    ])


def push_prompt_to_langsmith(
    prompt_identifier: str,
    prompt_template: ChatPromptTemplate,
    description: str = "",
    tags: list = None,
    is_public: bool = True,
) -> str | None:
    """
    Faz push do prompt para o LangSmith Hub.

    Args:
        prompt_identifier: Nome do prompt (ex: username/bug_to_user_story_v2)
        prompt_template: ChatPromptTemplate a publicar
        description: Descrição do prompt
        tags: Lista de tags
        is_public: Se True, prompt fica público

    Returns:
        URL do prompt no Hub ou None em caso de erro
    """
    client = Client()
    tags = tags or []
    url = client.push_prompt(
        prompt_identifier,
        object=prompt_template,
        description=description or "Prompt otimizado: Bug to User Story",
        tags=tags,
        is_public=is_public,
    )
    return url


def main():
    """Função principal"""
    print_section_header("PUSH DE PROMPTS PARA O LANGSMITH HUB")

    required_vars = ["LANGSMITH_API_KEY", "USERNAME_LANGSMITH_HUB"]
    if not check_env_vars(required_vars):
        return 1

    path = Path(PROMPT_FILE)
    if not path.exists():
        print(f"[ERRO] Arquivo nao encontrado: {PROMPT_FILE}")
        print("\nCrie o arquivo com seu prompt otimizado (a partir do v1) e rode novamente.")
        return 1

    data = load_yaml(PROMPT_FILE)
    if not data:
        print(f"[ERRO] Nao foi possivel carregar o YAML: {PROMPT_FILE}")
        return 1

    prompt_data = data.get(PROMPT_NAME)
    if not prompt_data and isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and value.get("system_prompt"):
                PROMPT_NAME_ACTUAL = key
                prompt_data = value
                break
        else:
            prompt_data = next(iter(data.values()), None) if data else None

    if not prompt_data:
        print(f"[ERRO] Nenhum prompt encontrado em {PROMPT_FILE} (esperada chave '{PROMPT_NAME}' ou similar).")
        return 1

    is_valid, errors = validate_prompt(prompt_data)
    if not is_valid:
        print("[ERRO] Validacao do prompt falhou:")
        for err in errors:
            print(f"   - {err}")
        return 1

    print(f"   Lendo: {PROMPT_FILE}")
    prompt_template = build_prompt_template(prompt_data)
    username = os.getenv("USERNAME_LANGSMITH_HUB", "").strip()
    slug = slugify_username(username)
    prompt_identifier = f"{slug}/{PROMPT_NAME}"

    description = prompt_data.get("description", "Prompt otimizado: Bug to User Story")
    tags = list(prompt_data.get("tags", []))
    if isinstance(prompt_data.get("techniques_applied"), list):
        tags = tags + [f"technique:{t}" for t in prompt_data["techniques_applied"]]

    print(f"   Push: {prompt_identifier} (público)")

    try:
        url = push_prompt_to_langsmith(
            prompt_identifier,
            prompt_template,
            description=description,
            tags=tags,
            is_public=True,
        )
        if url:
            print(f"   [OK] Publicado com sucesso")
            print(f"   URL: {url}")
        else:
            print("   [AVISO] Push concluido mas URL nao retornada.")
    except Exception as e:
        print(f"   [ERRO] Erro no push: {e}")
        return 1

    print("\n[OK] Push concluido. Proximo passo: python src/evaluate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
