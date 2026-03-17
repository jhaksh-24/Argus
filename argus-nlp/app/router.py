import os
import time
import requests
from fastapi import APIRouter
from .schemas import NLPQuery, AIResponse, VenueContext
from .prompt import build_prompt
from .history import add_query, get_history, get_context_from_redis

router = APIRouter()


# ── Intent classifier ─────────────────────────────────────────────────────────
def classify_intent(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ["alert", "critical", "danger", "triggered", "anomaly", "panic", "crush"]):
        return "alert"
    if any(w in q for w in ["forecast", "predict", "in 5 minutes", "egress", "will hit", "going to"]):
        return "forecast"
    if any(w in q for w in ["should", "recommend", "what to do", "action", "do right now"]):
        return "action"
    if any(w in q for w in ["history", "trend", "past", "happened", "last", "recent"]):
        return "history"
    return "status"


# ── Recommended actions per intent ───────────────────────────────────────────
ACTION_MAP = {
    "alert":    ["Investigate flagged zone immediately", "Deploy staff to alert location"],
    "forecast": ["Open auxiliary exits C2/C3", "Assign 2 staff to Gate B"],
    "action":   ["Follow recommended egress protocol", "Contact duty manager"],
    "status":   [],
    "history":  [],
}


# ── Ollama model call ─────────────────────────────────────────────────────────
def call_model(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 220,
        },
    }

    try:
        r = requests.post(
            f"{ollama_url}/api/generate",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("response", "Unable to parse model output.").strip()

    except Exception:
        # Ollama not running — safe stub for demo mode
        if "forecast" in prompt.lower():
            return "Gate B has the highest predicted congestion risk. Open auxiliary exits C2 and C3 and deploy 2 marshals to the north concourse immediately."
        if "alert" in prompt.lower():
            return "Active alert at Gate B: density approaching critical threshold. Create dedicated queue lanes and deploy additional staff."
        if "action" in prompt.lower() or "should" in prompt.lower():
            return "Deploy 2 staff to Gate B now and open auxiliary exit C2. Monitor Zone A density over the next 5 minutes."
        return "All zones are normal except Gate B which is at warning level. Continue monitoring and pre-position staff at high-risk exits."


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/query", response_model=AIResponse)
def query_nlp(query: NLPQuery):
    start = time.time()

    # Step 1 — classify intent
    intent = query.intent or classify_intent(query.query)

    # Step 2 — get venue context
    # Priority: request body context → live Redis → demo fallback
    if query.context:
        context = query.context
    else:
        live = get_context_from_redis()
        if live:
            context = VenueContext(**live)
        else:
            context = VenueContext(
                timestamp="2026-03-17T12:00:00Z",
                zone_states=[
                    {"zone_id": "Gate A", "occupancy": 120, "density": 0.65, "flow_rate": 0.9,  "status": "normal"},
                    {"zone_id": "Gate B", "occupancy": 270, "density": 1.8,  "flow_rate": 2.4,  "status": "warning"},
                ],
                alerts=["Gate B approaching critical density"],
            )

    # Step 3 — build prompt and call model
    prompt = build_prompt(context=context, query=query.query, intent=intent)
    add_query(query.user_id, query)
    assistant_text = call_model(prompt)

    # Step 4 — return with latency
    latency_ms = round((time.time() - start) * 1000)

    return AIResponse(
        assistant=assistant_text,
        detail=f"Intent={intent}; prompt_length={len(prompt)}",
        recommended_actions=ACTION_MAP.get(intent, []),
        latency_ms=latency_ms,
    )


@router.get("/history/{user_id}")
def history(user_id: str):
    return {"user_id": user_id, "history": get_history(user_id)}