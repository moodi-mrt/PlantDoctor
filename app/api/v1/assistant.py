"""Agricultural assistant — /api/v1/assistant.

Grounding:
  * The vision model's result (crop, condition, confidence, status) is passed as structured data;
    the LLM never makes its own diagnosis from the photo.
  * Only knowledge-base documents retrieved for the question are given to the model, each with an
    id; the answer must cite ids, and citations are mapped back to the real references.
  * The answer is validated (no dose-like quantities, no active ingredients absent from the
    retrieved documents). Failing answers are replaced by the retrieved KB text.
  * Without Claude credentials the endpoint still answers with the most relevant KB articles.
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ...config import CLAUDE_MODEL
from ...core import ratelimit
from ...core.errors import AppError
from ...core.security import current_user
from ...db import Conversation, Diagnosis, Message, User, aware, get_session
from ...knowledge import kb
from ...services import llm, rag

router = APIRouter(tags=["assistant"])
log = logging.getLogger("plantdoctor.assistant")

SYSTEM = """You are PlantDoctor's agricultural assistant for farmers and gardeners, mainly in Pakistan.

Use ONLY the knowledge-base documents provided in <documents> and the diagnosis in <diagnosis> (if any).
Rules:
- If the documents do not contain the answer, say so plainly and suggest asking the local Agriculture Extension office. Do not fill gaps from general knowledge.
- Cite the documents you used with their ids in square brackets, e.g. [Tomato___Late_blight].
- NEVER give pesticide doses, rates, concentrations, mixing ratios, spray intervals or pre-harvest intervals. For chemicals, name only active ingredients that appear in the documents and tell the user to follow the registered product label.
- Never recommend unsafe practices (mixing chemicals, spraying without protection, using products not registered for the crop).
- The image diagnosis comes from a computer-vision model. Respect its status: if it is "tentative", "uncertain", "needs_input" or "unknown", say the diagnosis is not certain and recommend confirming with an expert before treating. Never invent a different diagnosis.
- Set needs_expert=true for uncertain diagnoses, notifiable diseases (e.g. citrus greening), severe or spreading outbreaks, or any safety question.
- Answer in the user's language (English or Urdu). Be concise and practical: short paragraphs or bullet points."""


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    diagnosis_id: int | None = None
    language: str = Field("en", pattern=r"^(en|ur)$")


class Answer(BaseModel):
    answer: str = Field(description="Markdown answer for the user, citing document ids in [brackets].")
    cited_ids: list[str] = Field(description="Ids of the documents actually used.")
    needs_expert: bool = Field(description="True if the user should consult an agronomist / extension officer.")


def _diag_context(d: Diagnosis | None) -> dict | None:
    if not d:
        return None
    e = kb.entry(d.label) if d.label else None
    return {"status": d.status, "crop": (kb.plant_info(d.crop_key) or {}).get("name") if d.crop_key else None,
            "condition": e["name"] if e and d.status in ("confident", "tentative", "uncertain") else None,
            "label": d.label, "confidence": round(d.confidence, 3), "healthy": d.healthy,
            "date": aware(d.created_at).date().isoformat()}


def _validate(text: str, docs: list[dict]) -> list[str]:
    problems = []
    allowed = " ".join(c["ai"].lower() for d in docs for c in d["chemical"])
    for m in llm._DOSE.finditer(text):
        problems.append(f"dose-like text {m.group(0)!r}")
    for ai in kb.all_chemical_ais():
        for part in re.split(r"\s*[+/(),]\s*", ai):
            part = part.strip()
            if len(part) > 4 and part not in allowed and re.search(rf"\b{re.escape(part)}\b", text, re.I):
                problems.append(f"active ingredient not in retrieved documents: {part}")
    return problems


def _kb_fallback(docs: list[dict], reason: str) -> dict:
    if not docs:
        text = ("I couldn't find this in the PlantDoctor knowledge base. Please ask your district Agriculture "
                "Extension office (in Punjab, the Agriculture Department helpline is 0800-17000).")
    else:
        lines = ["Here is what the PlantDoctor knowledge base says:"]
        for d in docs[:3]:
            first = d["text"].split("\n")
            lines.append(f"\n**{d['title']}** [{d['id']}]\n" + "\n".join(f"- {l}" for l in first[:6]))
        text = "\n".join(lines)
    return {"answer": text, "cited_ids": [d["id"] for d in docs[:3]], "needs_expert": True, "mode": "knowledge_base",
            "reason": reason}


def _citations(ids: list[str], docs: list[dict]) -> list[dict]:
    by = {d["id"]: d for d in docs}
    out, seen = [], set()
    for i in ids:
        d = by.get(i)
        if not d:
            continue
        out.append({"doc_id": i, "title": d["title"], "type": d["type"],
                    "link": f"/app/knowledge/{i}" if d["type"] == "disease" else None, "references": d["references"][:4]})
        seen.add(i)
    return out


@router.post("/assistant/chat")
def chat(body: ChatIn, request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    ratelimit.hit(f"assist:{user.id}", 20, 60)
    ratelimit.hit(f"assist-day:{user.id}", 200, 86400, "Daily assistant limit reached. Please try again tomorrow.")
    conv = None
    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if not conv or conv.user_id != user.id:
            raise AppError(404, "Conversation not found.")
    diag = None
    did = body.diagnosis_id or (conv.diagnosis_id if conv else None)
    if did:
        diag = db.get(Diagnosis, did)
        if not diag or diag.user_id != user.id:
            raise AppError(404, "Diagnosis not found.")
    if conv is None:
        conv = Conversation(user_id=user.id, diagnosis_id=diag.id if diag else None, title=body.message[:80])
        db.add(conv)
        db.flush()

    history = [{"role": m.role, "content": m.content} for m in conv.messages][-10:]
    dctx = _diag_context(diag)
    boost = [diag.label] if diag and diag.label else None
    q = body.message + " " + " ".join(m["content"] for m in history[-2:] if m["role"] == "user")
    if dctx and dctx.get("condition"):
        q += f" {dctx['condition']} {dctx['crop']}"
    docs = rag.search(q, k=4, boost=boost)

    result = None
    if llm.available():
        doc_xml = "\n".join(f'<document id="{d["id"]}" title="{d["title"]}">\n{d["text"]}\n</document>' for d in docs)
        system = SYSTEM + f"\n\n<documents>\n{doc_xml}\n</documents>\n\n<diagnosis>{json.dumps(dctx)}</diagnosis>"
        msgs = history + [{"role": "user", "content": body.message + ("\n\n(Please answer in Urdu.)" if body.language == "ur" else "")}]
        try:
            import anthropic
            client = anthropic.Anthropic(max_retries=2, timeout=90.0)
            resp = client.beta.messages.parse(model=CLAUDE_MODEL, max_tokens=4000, system=system, messages=msgs,
                                              output_config={"effort": "medium"}, output_format=Answer,
                                              betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            if resp.stop_reason == "refusal" or resp.parsed_output is None:
                result = _kb_fallback(docs, f"model returned no usable answer ({resp.stop_reason})")
            else:
                a = resp.parsed_output
                problems = _validate(a.answer, docs)
                if problems:
                    log.warning("assistant answer rejected: %s", problems[:3])
                    result = _kb_fallback(docs, "AI answer failed the safety check (" + problems[0] + ")")
                else:
                    result = {"answer": a.answer, "cited_ids": [i for i in a.cited_ids if any(d["id"] == i for d in docs)],
                              "needs_expert": a.needs_expert or (dctx or {}).get("status") not in (None, "confident"),
                              "mode": "ai", "model": resp.model}
        except Exception as e:
            log.exception("assistant call failed")
            result = _kb_fallback(docs, f"AI service error: {type(e).__name__}")
    else:
        result = _kb_fallback(docs, "AI assistant not configured (no Claude API key)")

    cites = _citations(result["cited_ids"], docs)
    db.add(Message(conversation_id=conv.id, role="user", content=body.message))
    db.add(Message(conversation_id=conv.id, role="assistant", content=result["answer"], citations=cites,
                   model=result.get("model")))
    db.commit()
    return {"conversation_id": conv.id, "answer": result["answer"], "citations": cites,
            "needs_expert": result["needs_expert"], "mode": result["mode"], "reason": result.get("reason"),
            "label": "AI-generated explanation grounded in the PlantDoctor knowledge base" if result["mode"] == "ai"
                     else "Knowledge-base excerpt (no AI generation)",
            "expert_help": kb.expert_help() if result["needs_expert"] else []}


@router.get("/assistant/conversations")
def conversations(user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.id.desc()).limit(50))
    return {"items": [{"id": c.id, "title": c.title, "diagnosis_id": c.diagnosis_id,
                       "created_at": aware(c.created_at).isoformat()} for c in rows]}


@router.get("/assistant/conversations/{cid}")
def conversation(cid: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise AppError(404, "Conversation not found.")
    return {"id": c.id, "title": c.title, "diagnosis_id": c.diagnosis_id,
            "messages": [{"role": m.role, "content": m.content, "citations": m.citations,
                          "created_at": aware(m.created_at).isoformat()} for m in c.messages]}


@router.delete("/assistant/conversations/{cid}", status_code=204)
def delete_conversation(cid: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise AppError(404, "Conversation not found.")
    db.delete(c)
    db.commit()
    return Response(status_code=204)
