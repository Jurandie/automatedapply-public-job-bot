from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

from app.config import PROJECT_ROOT


class ClaudeCliError(RuntimeError):
    """Raised when Claude CLI cannot be executed or returns invalid data."""


def claude_available() -> bool:
    return shutil.which("claude") is not None


def run_claude_prompt(
    prompt: str,
    timeout_seconds: int = 120,
    json_schema: dict[str, Any] | None = None,
) -> str:
    claude_path = shutil.which("claude")
    if not claude_path:
        raise ClaudeCliError("Claude CLI nao encontrado no PATH.")

    command = [
        claude_path,
        "-p",
        "--no-session-persistence",
        "--output-format",
        "text",
    ]
    if json_schema:
        command.extend(["--json-schema", json.dumps(json_schema, separators=(",", ":"))])
    command.append(prompt)

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            **_hidden_subprocess_options(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCliError(f"Claude excedeu o tempo limite de {timeout_seconds}s.") from exc
    except OSError as exc:
        raise ClaudeCliError(f"Falha ao iniciar Claude CLI: {exc}") from exc

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        raise ClaudeCliError(error or f"Claude CLI falhou com codigo {completed.returncode}.")
    return completed.stdout.strip()


def classify_post_with_script(post_text: str, timeout_seconds: int = 120) -> dict[str, Any]:
    prompt = build_classification_prompt(post_text)
    response = run_claude_prompt(
        prompt,
        timeout_seconds=timeout_seconds,
    )
    return parse_claude_json_response(response)


def build_classification_prompt(post_text: str) -> str:
    clipped_text = post_text[:18_000]
    return f"""Voce e um classificador de vagas.
Retorne apenas JSON valido, sem markdown, seguindo o schema informado.

Criterios:
- is_job_post: true/false
- target_country_allowed: true somente se a vaga estiver explicitamente ligada a Italy ou Ireland
- remote_allowed: true somente para vagas remotas em Italy ou Ireland
- onsite_or_hybrid_allowed: true somente para presencial/hibrido em Ireland
- currency_allowed: true se houver EUR/USD ou se salario nao informado sem indicio de unpaid/volunteer/commission-only
- is_recent_job_post: true/false quando houver data; true se a pagina nao informar data
- seniority_allowed: true apenas para Junior/Jr/Entry-level/Associate ou Pleno/Mid-level/Mid
- confidence: 0.0 a 1.0
- reason: string curta em portugues
- extracted_role: string|null
- extracted_company: string|null
- extracted_location: string|null
- extracted_currency: string|null
- application_links: array

Regras:
- Aceite apenas vagas com localizacao explicita na Italia ou Irlanda.
- Aceite vagas remotas na Italia ou Irlanda.
- Aceite vagas presenciais ou hibridas apenas na Irlanda.
- Rejeite Europa generica quando Italia ou Irlanda nao estiverem explicitas.
- Rejeite Senior/Sr/Lead/Staff/Principal/Architect/Manager/Head/Director.
- Se a senioridade nao estiver explicita, marque seniority_allowed=false e explique.
- Rejeite remote US only, Canada only, unpaid, volunteer e commission only.
- Nao invente informacoes.

Texto:
{clipped_text}
"""


def parse_claude_json_response(response: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fence(response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        extracted = _extract_first_json_object(cleaned)
        if extracted is None:
            raise ClaudeCliError("Claude retornou JSON invalido.")
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError as exc:
            raise ClaudeCliError("Claude retornou JSON invalido.") from exc
    if not isinstance(parsed, dict):
        raise ClaudeCliError("Claude retornou JSON invalido: objeto esperado.")
    return parsed


def _hidden_subprocess_options() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    options: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    options["startupinfo"] = startupinfo
    return options


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.IGNORECASE | re.DOTALL)
    return fence.group(1).strip() if fence else stripped


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
