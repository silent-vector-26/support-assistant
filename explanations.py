"""Optional, opt-in language-model explanations grounded in retrieved evidence.

The deterministic workflow never depends on this module. Output is accepted only
when it cites passages that were actually retrieved and stays close to their text;
anything else is rejected so the technician sees the limitation instead of a
fabricated explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fieldtech_assistant import STOP_WORDS

API_VERSION = "2024-10-21"
MIN_GROUNDED_RATIO = 0.6
MAX_EXPLANATION_CHARS = 1200
SOURCE_ID_PATTERN = re.compile(r"\[?(DEMO-[A-Z0-9.\-]+)\]?")

SYSTEM_PROMPT = (
    "You explain HVAC troubleshooting guidance to a field technician. Use ONLY the "
    "numbered evidence passages provided. Do not add procedures, causes, part numbers, "
    "or safety advice that are not in the passages. Never help bypass safety protections. "
    "If the passages do not support an explanation, set \"explanation\" to an empty string. "
    "Respond as JSON: {\"explanation\": string, \"citations\": [source_id strings used]}. "
    "Keep the explanation under 120 words and do not quote more than one short phrase verbatim."
)


class ExplanationNotConfigured(RuntimeError):
    """The optional model integration is disabled or incompletely configured."""


class ExplanationError(RuntimeError):
    """The model call failed or its output was rejected."""


@dataclass(frozen=True)
class ModelConfig:
    endpoint: str
    key: str
    deployment: str
    timeout: int = 20


@dataclass(frozen=True)
class Explanation:
    text: str
    citations: tuple[str, ...]


def config_from_env(env: dict[str, str] | None = None) -> ModelConfig:
    env = os.environ if env is None else env
    if env.get("AI_EXPLANATIONS_ENABLED", "").strip().lower() != "true":
        raise ExplanationNotConfigured(
            "AI explanations are disabled. The documented checks above are unaffected."
        )
    values = {name: env.get(name, "").strip() for name in (
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT")}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ExplanationNotConfigured(
            "AI explanations are enabled but not fully configured; missing "
            + ", ".join(missing) + ". The documented checks above are unaffected."
        )
    endpoint = values["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    if not (endpoint.startswith("https://") or endpoint.startswith("http://127.0.0.1")):
        raise ExplanationNotConfigured("AZURE_OPENAI_ENDPOINT must use https.")
    return ModelConfig(endpoint, values["AZURE_OPENAI_KEY"], values["AZURE_OPENAI_DEPLOYMENT"])


def build_messages(question: str, evidence: list[dict[str, str]]) -> list[dict[str, str]]:
    passages = "\n\n".join(
        f"[{item['source_id']}] {item['citation']}\n{item['excerpt']}" for item in evidence
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nEvidence passages:\n{passages}"},
    ]


def call_model(config: ModelConfig, messages: list[dict[str, str]]) -> str:
    url = (
        f"{config.endpoint}/openai/deployments/{quote(config.deployment, safe='')}"
        f"/chat/completions?api-version={API_VERSION}"
    )
    body = json.dumps({
        "messages": messages,
        "temperature": 0,
        "max_tokens": 350,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "api-key": config.key, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]
    except HTTPError as exc:
        raise ExplanationError(f"The model service returned HTTP {exc.code}.") from exc
    except TimeoutError as exc:
        raise ExplanationError("The model request timed out.") from exc
    except URLError as exc:
        raise ExplanationError("The model service could not be reached.") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExplanationError("The model service returned an unreadable response.") from exc


def _content_tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", text)
            if len(t) > 2 and t.lower() not in STOP_WORDS}


def validate_output(raw: str, evidence: list[dict[str, str]]) -> Explanation:
    """Accept only a cited, evidence-grounded explanation; otherwise raise."""
    try:
        data = json.loads(raw)
        text = data["explanation"]
        citations = data["citations"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ExplanationError("The model output was not valid explanation JSON.") from exc
    if not isinstance(text, str) or not isinstance(citations, list) \
            or not all(isinstance(c, str) for c in citations):
        raise ExplanationError("The model output had an invalid shape.")
    text = text.strip()
    if not text:
        raise ExplanationError("The model declined to explain from the available evidence.")
    if len(text) > MAX_EXPLANATION_CHARS:
        raise ExplanationError("The model explanation was too long and was rejected.")
    allowed = {item["source_id"] for item in evidence}
    if not citations or not set(citations) <= allowed:
        raise ExplanationError("The model cited missing or unretrieved sources and was rejected.")
    mentioned = set(SOURCE_ID_PATTERN.findall(text))
    if not mentioned <= allowed:
        raise ExplanationError("The explanation referenced unretrieved sources and was rejected.")
    cited_text = " ".join(
        f"{item['excerpt']} {item['citation']}" for item in evidence if item["source_id"] in citations)
    tokens = _content_tokens(text)
    if tokens and len(tokens & _content_tokens(cited_text)) / len(tokens) < MIN_GROUNDED_RATIO:
        raise ExplanationError("The explanation was not sufficiently grounded in the cited passages.")
    return Explanation(text=text, citations=tuple(dict.fromkeys(citations)))


def explain(
    question: str,
    guidance: dict[str, Any],
    config: ModelConfig,
    model: Callable[[ModelConfig, list[dict[str, str]]], str] | None = None,
) -> Explanation:
    """Explain supported guidance only; unsupported or escalated results never reach the model."""
    if guidance.get("status") != "supported" or not guidance.get("evidence"):
        raise ExplanationError("No documented evidence is available to explain.")
    raw = (model or call_model)(config, build_messages(question, guidance["evidence"]))
    return validate_output(raw, guidance["evidence"])
