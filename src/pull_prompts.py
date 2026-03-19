"""
Script para fazer pull de prompts do LangSmith Prompt Hub.

Este script:
1. Conecta ao LangSmith usando credenciais do .env
2. Faz pull dos prompts do Hub
3. Salva localmente em prompts/bug_to_user_story_v1.yml
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()

PROMPT_HUB_ID = "leonanluppi/bug_to_user_story_v1"
OUTPUT_FILE = "prompts/bug_to_user_story_v1.yml"


def extract_prompt_to_dict(template: ChatPromptTemplate, prompt_key: str) -> dict:
    """
    Extrai system_prompt e user_prompt de um ChatPromptTemplate para o formato YAML do projeto.

    Args:
        template: ChatPromptTemplate retornado pelo hub.pull()
        prompt_key: Nome do prompt (ex: bug_to_user_story_v1)

    Returns:
        Dicionário no formato esperado pelo YAML (description, system_prompt, user_prompt, etc.)
    """
    system_prompt = ""
    user_prompt = ""

    for msg in template.messages:
        if isinstance(msg, SystemMessagePromptTemplate):
            system_prompt = msg.prompt.template
        elif isinstance(msg, HumanMessagePromptTemplate):
            user_prompt = msg.prompt.template

    return {
        prompt_key: {
            "description": "Prompt para converter relatos de bugs em User Stories (versão inicial do Hub)",
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "version": "v1",
            "created_at": "2025-01-15",
            "tags": ["bug-analysis", "user-story", "product-management"],
        }
    }


def pull_prompts_from_langsmith() -> bool:
    """
    Faz pull do prompt no LangSmith Hub e salva em YAML local.

    Returns:
        True se sucesso, False caso contrário
    """
    print(f"   Conectando ao LangSmith Hub...")
    print(f"   Pull: {PROMPT_HUB_ID}")

    client = Client()
    prompt_template = client.pull_prompt(PROMPT_HUB_ID)

    if not isinstance(prompt_template, ChatPromptTemplate):
        print("   [ERRO] O objeto retornado nao e um ChatPromptTemplate.")
        return False

    prompt_key = "bug_to_user_story_v1"
    data = extract_prompt_to_dict(prompt_template, prompt_key)

    if not save_yaml(data, OUTPUT_FILE):
        return False

    print(f"   [OK] Salvo em {OUTPUT_FILE}")
    return True


def main():
    """Função principal"""
    print_section_header("PULL DE PROMPTS DO LANGSMITH HUB")

    required_vars = ["LANGSMITH_API_KEY"]
    if not check_env_vars(required_vars):
        return 1

    print(f"Prompt a ser baixado: {PROMPT_HUB_ID}")
    print(f"Arquivo de saída: {OUTPUT_FILE}\n")

    try:
        if not pull_prompts_from_langsmith():
            return 1
        print("\n[OK] Pull concluido com sucesso.")
        print("Próximo passo: edite prompts/bug_to_user_story_v2.yml (otimizado) e depois rode push_prompts.py")
        return 0
    except Exception as e:
        print(f"\n[ERRO] Erro ao fazer pull: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
