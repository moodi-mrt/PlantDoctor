"""Plain-language, plant-specific explanation of a diagnosis, written by Claude.

Grounding rules (enforced in code, not just in the prompt):
  * Claude only receives the curated KB entry and the model's result; it is asked to rewrite,
    not to add facts.
  * Output is structured (Pydantic schema).
  * A validator rejects the answer if it contains dose-like numbers/units, or names an active
    ingredient that is in the KB but NOT in this disease's entry. Rejected or failed calls fall
    back to the KB text, so the app never shows unvalidated chemical advice.
  * Results are cached per (label, crop, status, severity, language) in the API cache.

The feature is optional: without credentials the endpoint returns {"available": false}.
"""
import hashlib
import json
import logging
import re

from pydantic import BaseModel, Field

from ..config import CLAUDE_MODEL, LLM_ENABLED, LLM_TTL_S
from ..knowledge import kb
from .cache import cached

log = logging.getLogger("plantdoctor.llm")


class Explanation(BaseModel):
    summary: str = Field(description="2-3 sentence plain-language summary of what is wrong (or that the plant looks healthy) and how sure the system is.")
    what_to_do_now: list[str] = Field(description="3-6 short, ordered action steps for the next few days, taken from the knowledge-base entry.")
    why_it_happened: str = Field(description="Short explanation of causes and favourable conditions, from the entry.")
    prevention: list[str] = Field(description="3-5 prevention / long-term care steps from the entry.")
    caution: str = Field(description="One sentence on uncertainty and when to consult an agronomist.")


SYSTEM = """You explain plant-health diagnoses to farmers and home gardeners in Pakistan.

You will receive a JSON object with the image model's result and a curated knowledge-base entry.
Rewrite the entry as clear, practical advice for this specific plant.

Hard rules:
- Use ONLY facts present in the provided entry and result. Do not add diseases, causes, products, brand names or active ingredients that are not in the entry.
- NEVER give doses, rates, concentrations, mixing ratios, spray intervals or pre-harvest intervals. If chemical control is relevant, name the active ingredients from the entry and say to follow the registered product label.
- If the result status is "tentative" or "uncertain", say clearly that the diagnosis is not certain and recommend confirming with an agronomist before spraying.
- Keep sentences short and concrete. No marketing language."""

_DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|mL|g|gm|gram|kg|l|L|litre|liter|ltr|%|percent|ppm|oz|cc|acre|hectare|ha)\b"
                   r"|\bper\s+(?:acre|litre|liter|hectare|tank|kanal)\b", re.I)


def _client():
    try:
        import anthropic
    except ImportError:
        return None
    try:
        return anthropic.Anthropic(max_retries=2, timeout=60.0)
    except Exception as e:  # no credentials configured
        log.info("Claude API not configured: %s", e)
        return None


def _has_credentials() -> bool:
    import os
    from pathlib import Path
    if any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE")):
        return True
    return (Path.home() / ".config" / "anthropic").exists()   # `ant auth login` profile


def available() -> bool:
    return LLM_ENABLED and _has_credentials() and _client() is not None


def validate(out: Explanation, entry: dict) -> list[str]:
    """Return a list of problems; empty means the text may be shown."""
    text = " ".join([out.summary, out.why_it_happened, out.caution, *out.what_to_do_now, *out.prevention])
    problems = []
    kb_text = json.dumps(entry, ensure_ascii=False)
    for m in _DOSE.finditer(text):
        if m.group(0) not in kb_text:
            problems.append(f"dose-like text: {m.group(0)!r}")
    allowed = " ".join(c["ai"].lower() for c in entry["treatment"]["chemical"])
    for ai in kb.all_chemical_ais():
        for part in re.split(r"\s*[+/(),]\s*", ai):
            part = part.strip()
            if len(part) > 4 and part not in allowed and re.search(rf"\b{re.escape(part)}\b", text, re.I):
                problems.append(f"active ingredient not in this entry: {part}")
    return problems


def explain(result: dict, entry: dict, lang: str = "en") -> dict:
    """Return {"available", "text"?, "source", "fetched_at", "fallback_reason"?}."""
    if not LLM_ENABLED:
        return {"available": False, "reason": "disabled (PD_LLM=0)"}
    client = _client() if _has_credentials() else None
    if client is None:
        return {"available": False, "reason": "no Claude API credentials configured"}

    best = (result.get("top") or [{}])[0]
    payload = {
        "result": {"status": result.get("status"), "plant": (result.get("plant") or {}).get("crop"),
                   "condition": best.get("disease"), "confidence": round(best.get("prob", 0), 3),
                   "severity": (result.get("severity") or {}).get("level"),
                   "other_possible_problems": [f["disease"] for f in result.get("findings", [])]},
        "entry": {k: entry[k] for k in ("crop", "name", "kind", "pathogen", "affected_parts", "symptoms",
                                        "causes", "conditions", "treatment")},
        "language": "Urdu (Urdu script)" if lang == "ur" else "English",
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    key = "llm:" + CLAUDE_MODEL + ":" + hashlib.sha256(blob.encode()).hexdigest()[:32]

    def fetch():
        resp = client.beta.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"Write the explanation in {payload['language']}.\n\n{blob}"}],
            output_format=Explanation,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise RuntimeError(f"no usable output (stop_reason={resp.stop_reason})")
        out = resp.parsed_output
        problems = validate(out, entry)
        if problems:
            raise ValueError("; ".join(problems[:3]))
        return {"text": out.model_dump(), "model": resp.model}

    try:
        r = cached(key, f"Claude ({CLAUDE_MODEL}) — grounded in PlantDoctor knowledge base", LLM_TTL_S, fetch,
                   allow_stale=False)
        return {"available": True, **r["data"], "source": r["source"], "fetched_at": r["fetched_at"]}
    except Exception as e:
        log.warning("LLM explanation rejected/failed: %s", e)
        return {"available": True, "text": None, "fallback_reason": str(e)[:200]}
