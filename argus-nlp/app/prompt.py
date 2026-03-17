from .schemas import VenueContext

BASE_PROMPT = """You are ARGUS Operator Assistant for a large stadium venue safety system.
Use ONLY the provided venue context facts. Do not make assumptions or invent numbers.
Answer concisely in actionable language — 2 to 3 sentences maximum.
If asked for decision support, provide a clear recommendation with specific zone or gate names."""

INTENT_TEMPLATES = {
    "status":   "Summarise current zone severity and highlight the single highest-risk zone.",
    "alert":    "Explain the cause of the active alert and recommend one specific mitigation step.",
    "forecast": "State which exit will hit critical density first, the probability, and how many minutes away.",
    "action":   "Give the operator one concrete action right now — name the exact gate or zone.",
    "history":  "Summarise key trends from recent venue state and any recurring alert patterns.",
}


def build_prompt(context: VenueContext, query: str, intent: str = "status") -> str:
    intent_desc = INTENT_TEMPLATES.get(intent.lower(), "Answer the operator question concisely.")

    zones = "\n".join([
        f"  - {z.zone_id}: occupancy={z.occupancy}, density={z.density:.2f}, "
        f"flow={z.flow_rate:.2f}, status={z.status}"
        for z in context.zone_states
    ])

    alerts = "\n".join([f"  - {a}" for a in context.alerts]) or "  None active."

    prompt = (
        f"{BASE_PROMPT}\n\n"
        f"--- VENUE STATE AT {context.timestamp} ---\n"
        f"ZONES:\n{zones}\n\n"
        f"ACTIVE ALERTS:\n{alerts}\n"
        f"--- END VENUE STATE ---\n\n"
        f"TASK: {intent_desc}\n\n"
        f"OPERATOR QUESTION: {query}\n\n"
        f"ARGUS ANSWER:"
    )
    return prompt