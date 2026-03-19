"""
Script COMPLETO para avaliar prompts otimizados.

Este script:
1. Carrega dataset de avaliação de arquivo .jsonl (datasets/bug_to_user_story.jsonl)
2. Cria/atualiza dataset no LangSmith
3. Puxa prompts otimizados do LangSmith Hub (fonte única de verdade)
4. Executa prompts contra o dataset
5. Calcula as 4 métricas do README (Tone, Acceptance Criteria, User Story Format, Completeness)
6. Publica resultados no dashboard do LangSmith
7. Exibe resumo no terminal

Suporta múltiplos providers de LLM:
- OpenAI (gpt-4o, gpt-4o-mini)
- Google Gemini (gemini-1.5-flash, gemini-1.5-pro)

Configure o provider no arquivo .env através da variável LLM_PROVIDER.
"""

import os
import re
import sys
import json
import time
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate, HumanMessagePromptTemplate
from utils import check_env_vars, format_score, print_section_header, get_llm as get_configured_llm, load_yaml
from metrics import (
    evaluate_tone_score,
    evaluate_acceptance_criteria_score,
    evaluate_user_story_format_score,
    evaluate_completeness_score,
)

load_dotenv()


def get_llm():
    use_strong = os.getenv("EVAL_USE_STRONG_MODEL", "").strip() in ("1", "true", "yes")
    model = os.getenv("EVAL_MODEL", "gpt-4o") if use_strong else None
    return get_configured_llm(temperature=0) if not model else get_configured_llm(temperature=0, model=model)


def _maybe_sleep_for_gemini_rate_limit():
    """Evita 429 no free tier do Gemini (10 req/min): delay de ~7s entre chamadas."""
    if os.getenv("LLM_PROVIDER", "").lower() in ("google", "gemini"):
        time.sleep(7)


def load_dataset_from_jsonl(jsonl_path: str) -> List[Dict[str, Any]]:
    examples = []

    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    example = json.loads(line)
                    examples.append(example)

        return examples

    except FileNotFoundError:
        print(f"[ERRO] Arquivo nao encontrado: {jsonl_path}")
        print("\nCertifique-se de que o arquivo datasets/bug_to_user_story.jsonl existe.")
        return []
    except json.JSONDecodeError as e:
        print(f"[ERRO] Erro ao parsear JSONL: {e}")
        return []
    except Exception as e:
        print(f"[ERRO] Erro ao carregar dataset: {e}")
        return []


def create_evaluation_dataset(client: Client, dataset_name: str, jsonl_path: str) -> str:
    print(f"Criando dataset de avaliação: {dataset_name}...")

    examples = load_dataset_from_jsonl(jsonl_path)

    if not examples:
        print("[ERRO] Nenhum exemplo carregado do arquivo .jsonl")
        return dataset_name

    print(f"   [OK] Carregados {len(examples)} exemplos do arquivo {jsonl_path}")

    try:
        datasets = client.list_datasets(dataset_name=dataset_name)
        existing_dataset = None

        for ds in datasets:
            if ds.name == dataset_name:
                existing_dataset = ds
                break

        if existing_dataset:
            print(f"   [OK] Dataset '{dataset_name}' ja existe, usando existente")
            return dataset_name
        else:
            dataset = client.create_dataset(dataset_name=dataset_name)

            for example in examples:
                client.create_example(
                    dataset_id=dataset.id,
                    inputs=example["inputs"],
                    outputs=example["outputs"]
                )

            print(f"   [OK] Dataset criado com {len(examples)} exemplos")
            return dataset_name

    except Exception as e:
        print(f"   [AVISO] Erro ao criar dataset: {e}")
        return dataset_name


def build_prompt_template_from_dict(prompt_data: dict) -> ChatPromptTemplate:
    """Constrói ChatPromptTemplate a partir do dict do YAML (system_prompt + user_prompt)."""
    system_prompt = (prompt_data.get("system_prompt") or "").strip()
    user_prompt = (prompt_data.get("user_prompt") or prompt_data.get("human_prompt") or "{bug_report}").strip()
    if not user_prompt:
        user_prompt = "{bug_report}"
    return ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system_prompt),
        HumanMessagePromptTemplate.from_template(user_prompt),
    ])


def load_prompt_from_yaml(yaml_path: str) -> tuple[ChatPromptTemplate, str]:
    """
    Carrega prompt do arquivo YAML local (sem LangSmith).
    Retorna (ChatPromptTemplate, nome_do_prompt).
    """
    data = load_yaml(yaml_path)
    if not data or not isinstance(data, dict):
        raise FileNotFoundError(f"Não foi possível carregar YAML: {yaml_path}")
    prompt_data = None
    prompt_name = ""
    for key, value in data.items():
        if isinstance(value, dict) and (value.get("system_prompt") or value.get("user_prompt")):
            prompt_data = value
            prompt_name = key
            break
    if not prompt_data:
        raise ValueError(f"Nenhum bloco de prompt (system_prompt/user_prompt) encontrado em {yaml_path}")
    template = build_prompt_template_from_dict(prompt_data)
    return template, prompt_name


def evaluate_prompt_local(
    yaml_path: str,
    jsonl_path: str,
) -> dict:
    """
    Avalia o prompt carregado do YAML local contra o dataset em JSONL.
    Não usa LangSmith (ideal para testar antes de fazer push).
    """
    print(f"   Carregando prompt local: {yaml_path}")
    prompt_template, prompt_name = load_prompt_from_yaml(yaml_path)
    print(f"   [OK] Prompt carregado: {prompt_name}")

    examples = load_dataset_from_jsonl(jsonl_path)
    if not examples:
        raise ValueError(f"Nenhum exemplo em {jsonl_path}")

    env_max = int(os.getenv("EVAL_MAX_EXAMPLES", "0") or "0")
    max_examples = env_max if env_max > 0 else len(examples)
    examples = examples[:max_examples]
    print(f"   Dataset: {len(examples)} exemplos (arquivo {jsonl_path})")
    llm = get_llm()
    chain = prompt_template | llm

    tone_scores = []
    acceptance_scores = []
    format_scores = []
    completeness_scores = []

    print("   Avaliando exemplos (métricas: Tone, Acceptance Criteria, Format, Completeness)...")

    for i, ex in enumerate(examples, 1):
        inputs = ex.get("inputs") or {}
        outputs = ex.get("outputs") or {}
        bug_report = inputs.get("bug_report", "")
        reference = outputs.get("reference", "") if isinstance(outputs, dict) else ""

        response = chain.invoke({"bug_report": bug_report})
        answer = response.content if hasattr(response, "content") else str(response)

        if answer:
            t = evaluate_tone_score(bug_report, answer, reference, run_name="")
            a = evaluate_acceptance_criteria_score(bug_report, answer, reference, run_name="")
            f = evaluate_user_story_format_score(bug_report, answer, reference, run_name="")
            c = evaluate_completeness_score(bug_report, answer, reference, run_name="")
            tone_scores.append(t["score"])
            acceptance_scores.append(a["score"])
            format_scores.append(f["score"])
            completeness_scores.append(c["score"])
            print(f"      [{i}/{len(examples)}] Tone:{t['score']:.2f} Acceptance:{a['score']:.2f} Format:{f['score']:.2f} Completeness:{c['score']:.2f}")
        _maybe_sleep_for_gemini_rate_limit()

    avg_tone = sum(tone_scores) / len(tone_scores) if tone_scores else 0.0
    avg_acceptance = sum(acceptance_scores) / len(acceptance_scores) if acceptance_scores else 0.0
    avg_format = sum(format_scores) / len(format_scores) if format_scores else 0.0
    avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0

    return {
        "tone_score": round(avg_tone, 4),
        "acceptance_criteria_score": round(avg_acceptance, 4),
        "user_story_format_score": round(avg_format, 4),
        "completeness_score": round(avg_completeness, 4),
    }


def pull_prompt_from_langsmith(prompt_name: str, client: Client) -> ChatPromptTemplate:
    try:
        print(f"   Puxando prompt do LangSmith Hub: {prompt_name}")
        prompt = client.pull_prompt(prompt_name)
        print(f"   [OK] Prompt carregado com sucesso")
        return prompt

    except Exception as e:
        error_msg = str(e).lower()

        print(f"\n{'=' * 70}")
        print(f"[ERRO] Nao foi possivel carregar o prompt '{prompt_name}'")
        print(f"{'=' * 70}\n")

        if "not found" in error_msg or "404" in error_msg:
            print("[AVISO] O prompt nao foi encontrado no LangSmith Hub.\n")
            print("AÇÕES NECESSÁRIAS:")
            print("1. Verifique se você já fez push do prompt otimizado:")
            print(f"   python src/push_prompts.py")
            print()
            print("2. Confirme se o prompt foi publicado com sucesso em:")
            print(f"   https://smith.langchain.com/prompts")
            print()
            print(f"3. Certifique-se de que o nome do prompt está correto: '{prompt_name}'")
            print()
            print("4. Se você alterou o prompt no YAML, refaça o push:")
            print(f"   python src/push_prompts.py")
        else:
            print(f"Erro técnico: {e}\n")
            print("Verifique:")
            print("- LANGSMITH_API_KEY está configurada corretamente no .env")
            print("- Você tem acesso ao workspace do LangSmith")
            print("- Sua conexão com a internet está funcionando")

        print(f"\n{'=' * 70}\n")
        raise


def evaluate_prompt_on_example(
    prompt_template: ChatPromptTemplate,
    example: Any,
    llm: Any,
    run_name: str = "",
) -> Dict[str, Any]:
    try:
        inputs = example.inputs if hasattr(example, 'inputs') else {}
        outputs = example.outputs if hasattr(example, 'outputs') else {}

        chain = prompt_template | llm

        config = {}
        if run_name:
            config["run_name"] = run_name
            config["tags"] = ["eval", "user_story"] + ([run_name] if len(run_name) < 50 else [])

        response = chain.invoke(inputs, config=config or None)
        answer = response.content

        reference = outputs.get("reference", "") if isinstance(outputs, dict) else ""

        if isinstance(inputs, dict):
            question = inputs.get("question", inputs.get("bug_report", inputs.get("pr_title", "N/A")))
        else:
            question = "N/A"

        return {
            "answer": answer,
            "reference": reference,
            "question": question
        }

    except Exception as e:
        print(f"      [AVISO] Erro ao avaliar exemplo: {e}")
        import traceback
        print(f"      Traceback: {traceback.format_exc()}")
        return {
            "answer": "",
            "reference": "",
            "question": ""
        }


def evaluate_prompt(
    prompt_name: str,
    dataset_name: str,
    client: Client
) -> Dict[str, float]:
    print(f"\nAvaliando: {prompt_name}")

    try:
        prompt_template = pull_prompt_from_langsmith(prompt_name, client)

        examples = list(client.list_examples(dataset_name=dataset_name))
        env_max = int(os.getenv("EVAL_MAX_EXAMPLES", "0") or "0")
        max_examples = env_max if env_max > 0 else len(examples)
        examples_to_run = examples[:max_examples]
        print(f"   Dataset: {len(examples)} exemplos (avaliando {len(examples_to_run)})")
        llm = get_llm()

        tone_scores = []
        acceptance_scores = []
        format_scores = []
        completeness_scores = []

        print("   Avaliando exemplos (metricas do README: Tone, Acceptance Criteria, Format, Completeness)...")

        for i, example in enumerate(examples_to_run, 1):
            run_name = f"{prompt_name} - ex {i}"
            result = evaluate_prompt_on_example(prompt_template, example, llm, run_name=run_name)
            _maybe_sleep_for_gemini_rate_limit()
            bug_report = result.get("question", "")
            answer = result.get("answer", "")
            reference = result.get("reference", "")

            if answer:
                t = evaluate_tone_score(bug_report, answer, reference, run_name=f"Tone - ex {i}")
                _maybe_sleep_for_gemini_rate_limit()
                a = evaluate_acceptance_criteria_score(bug_report, answer, reference, run_name=f"Acceptance - ex {i}")
                _maybe_sleep_for_gemini_rate_limit()
                f = evaluate_user_story_format_score(bug_report, answer, reference, run_name=f"Format - ex {i}")
                _maybe_sleep_for_gemini_rate_limit()
                c = evaluate_completeness_score(bug_report, answer, reference, run_name=f"Completeness - ex {i}")
                _maybe_sleep_for_gemini_rate_limit()
                tone_scores.append(t["score"])
                acceptance_scores.append(a["score"])
                format_scores.append(f["score"])
                completeness_scores.append(c["score"])
                print(f"      [{i}/{len(examples_to_run)}] Tone:{t['score']:.2f} Acceptance:{a['score']:.2f} Format:{f['score']:.2f} Completeness:{c['score']:.2f}")

        avg_tone = sum(tone_scores) / len(tone_scores) if tone_scores else 0.0
        avg_acceptance = sum(acceptance_scores) / len(acceptance_scores) if acceptance_scores else 0.0
        avg_format = sum(format_scores) / len(format_scores) if format_scores else 0.0
        avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0

        return {
            "tone_score": round(avg_tone, 4),
            "acceptance_criteria_score": round(avg_acceptance, 4),
            "user_story_format_score": round(avg_format, 4),
            "completeness_score": round(avg_completeness, 4),
        }

    except Exception as e:
        print(f"   [ERRO] Erro na avaliacao: {e}")
        return {
            "tone_score": 0.0,
            "acceptance_criteria_score": 0.0,
            "user_story_format_score": 0.0,
            "completeness_score": 0.0,
        }


MINIMUM_SCORE = float(os.getenv("MINIMUM_METRIC_SCORE", "0.9"))


def display_results(prompt_name: str, scores: Dict[str, float]) -> bool:
    print("\n" + "=" * 32)
    print(f"Prompt: {prompt_name}")
    print("=" * 32)

    print("\nMétricas (Critério de Aprovação - README):")
    print(f"- Tone Score: {scores['tone_score']:.2f}")
    print(f"- Acceptance Criteria Score: {scores['acceptance_criteria_score']:.2f}")
    print(f"- User Story Format Score: {scores['user_story_format_score']:.2f}")
    print(f"- Completeness Score: {scores['completeness_score']:.2f}")

    average_score = sum(scores.values()) / len(scores)
    all_above = all(s >= MINIMUM_SCORE for s in scores.values())

    print(f"\nMÉDIA das 4 métricas: {average_score:.2f}")
    print("=" * 32)

    passed = all_above and average_score >= MINIMUM_SCORE

    if passed:
        print(f"Status: APROVADO ✓ - Todas as métricas atingiram o mínimo de {MINIMUM_SCORE}")
    else:
        print("Status: FALHOU - Métricas abaixo do mínimo de 0.9")
        if not all_above:
            below = [k for k, v in scores.items() if v < MINIMUM_SCORE]
            print(f"  Métricas abaixo de 0.9: {', '.join(below)}")
        if average_score < MINIMUM_SCORE:
            print(f"  Média atual: {average_score:.2f} | Necessário: {MINIMUM_SCORE:.2f}")

    return passed


def main():
    print_section_header("AVALIAÇÃO DE PROMPTS OTIMIZADOS")

    provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    eval_model = os.getenv("EVAL_MODEL", "gpt-4o")

    use_strong = os.getenv("EVAL_USE_STRONG_MODEL", "").strip().lower() in ("1", "true", "yes")
    use_local = "--local" in sys.argv or os.getenv("EVAL_LOCAL", "").strip().lower() in ("1", "true", "yes")

    print(f"Provider: {provider}")
    print(f"Modelo Principal: {eval_model if use_strong else llm_model}" + (" (modelo forte para geracao)" if use_strong else ""))
    print(f"Modelo de Avaliação: {eval_model}\n")
    if provider in ("google", "gemini"):
        print("[AVISO] Gemini free tier: 10 req/min, 250 req/dia. Avaliacao usa delay entre chamadas (pode levar ~15 min para 15 exemplos).")
        print("        Para limitar exemplos: EVAL_MAX_EXAMPLES=N no .env. Para rodar mais rapido sem delay: OpenAI.")
        print("        LLM_PROVIDER=openai  OPENAI_API_KEY=sk-...\n")

    if use_local:
        jsonl_path = "datasets/bug_to_user_story.jsonl"
        yaml_path = os.getenv("EVAL_LOCAL_YAML", "prompts/bug_to_user_story_v2.yml")
        base_dir = Path(__file__).resolve().parent.parent
        yaml_path_abs = base_dir / yaml_path
        jsonl_path_abs = base_dir / jsonl_path
        if not yaml_path_abs.exists():
            print(f"[ERRO] Arquivo nao encontrado: {yaml_path_abs}")
            print("       Defina EVAL_LOCAL_YAML ou use o caminho padrao: prompts/bug_to_user_story_v2.yml")
            return 1
        if not jsonl_path_abs.exists():
            print(f"[ERRO] Arquivo nao encontrado: {jsonl_path_abs}")
            return 1
        required_local = ["LLM_PROVIDER"]
        if provider == "openai":
            required_local.append("OPENAI_API_KEY")
        elif provider in ("google", "gemini"):
            required_local.append("GOOGLE_API_KEY")
        if not check_env_vars(required_local):
            return 1
        print("\n[MODO LOCAL] Usando prompt do YAML e dataset do JSONL (sem LangSmith).")
        print(f"             YAML: {yaml_path}  |  JSONL: {jsonl_path}\n")
        try:
            scores = evaluate_prompt_local(str(yaml_path_abs), str(jsonl_path_abs))
            passed = display_results(f"local ({yaml_path})", scores)
            print("\n" + "=" * 50)
            print("RESUMO (avaliacao local)")
            print("=" * 50)
            if passed:
                print(f"\n[OK] Todas as metricas >= {MINIMUM_SCORE}. Pode fazer push e rodar evaluate completo:")
                print("     python src/push_prompts.py")
                print("     python src/evaluate.py")
            else:
                print("\n[AVISO] Ajuste o prompt no YAML e rode novamente em modo local:")
                print("     python src/evaluate.py --local")
                print("     (ou EVAL_LOCAL=1 python src/evaluate.py)")
            return 0 if passed else 1
        except Exception as e:
            print(f"\n[ERRO] Falha na avaliacao local: {e}")
            import traceback
            traceback.print_exc()
            return 1

    required_vars = ["LANGSMITH_API_KEY", "LLM_PROVIDER"]
    if provider == "openai":
        required_vars.append("OPENAI_API_KEY")
    elif provider in ["google", "gemini"]:
        required_vars.append("GOOGLE_API_KEY")

    if not check_env_vars(required_vars):
        return 1

    client = Client()
    project_name = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT") or "prompt-optimization-challenge-resolved"
    os.environ["LANGCHAIN_PROJECT"] = project_name

    jsonl_path = "datasets/bug_to_user_story.jsonl"

    if not Path(jsonl_path).exists():
        print(f"[ERRO] Arquivo de dataset nao encontrado: {jsonl_path}")
        print("\nCertifique-se de que o arquivo existe antes de continuar.")
        return 1

    dataset_name = f"{project_name}-eval"
    create_evaluation_dataset(client, dataset_name, jsonl_path)

    print("\n" + "=" * 70)
    print("PROMPTS PARA AVALIAR")
    print("=" * 70)
    print("\nEste script irá puxar prompts do LangSmith Hub.")
    print("Certifique-se de ter feito push dos prompts antes de avaliar:")
    print("  python src/push_prompts.py\n")

    username = os.getenv("USERNAME_LANGSMITH_HUB", "").strip()
    slug = re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", username.lower())).strip("-") if username else ""
    prompt_v2_name = f"{slug}/bug_to_user_story_v2" if slug else "bug_to_user_story_v2"
    prompts_to_evaluate = [prompt_v2_name]

    all_passed = True
    evaluated_count = 0
    results_summary = []

    for prompt_name in prompts_to_evaluate:
        evaluated_count += 1

        try:
            scores = evaluate_prompt(prompt_name, dataset_name, client)

            passed = display_results(prompt_name, scores)
            all_passed = all_passed and passed

            results_summary.append({
                "prompt": prompt_name,
                "scores": scores,
                "passed": passed
            })

        except Exception as e:
            print(f"\n[ERRO] Falha ao avaliar '{prompt_name}': {e}")
            all_passed = False

            results_summary.append({
                "prompt": prompt_name,
                "scores": {
                    "tone_score": 0.0,
                    "acceptance_criteria_score": 0.0,
                    "user_story_format_score": 0.0,
                    "completeness_score": 0.0,
                },
                "passed": False
            })

    print("\n" + "=" * 50)
    print("RESUMO FINAL")
    print("=" * 50 + "\n")

    if evaluated_count == 0:
        print("[AVISO] Nenhum prompt foi avaliado")
        return 1

    print(f"Prompts avaliados: {evaluated_count}")
    print(f"Aprovados: {sum(1 for r in results_summary if r['passed'])}")
    print(f"Reprovados: {sum(1 for r in results_summary if not r['passed'])}\n")

    print(f"\nTraces/runs no LangSmith:")
    print(f"  https://smith.langchain.com  -> Projects -> '{project_name}'")
    if all_passed:
        print("\n[OK] Todos os prompts atingiram media >= 0.9!")
        print("\nProximos passos:")
        print("1. Documente o processo no README.md")
        print("2. Capture screenshots das avaliacoes")
        print("3. Faca commit e push para o GitHub")
        return 0
    else:
        print("\n[AVISO] Alguns prompts nao atingiram media >= 0.9")
        print("\nProximos passos:")
        print("1. Refatore os prompts com score baixo")
        print("2. Faca push novamente: python src/push_prompts.py")
        print("3. Execute: python src/evaluate.py novamente")
        return 1

if __name__ == "__main__":
    sys.exit(main())
