from typing import List, Dict, Optional
from .schemas import NLPQuery

# ── Chat history cache ────────────────────────────────────────────────────────
_HISTORY: Dict[str, List[NLPQuery]] = {}


def add_query(user_id: str, query: NLPQuery):
    if user_id not in _HISTORY:
        _HISTORY[user_id] = []
    _HISTORY[user_id].append(query)
    _HISTORY[user_id] = _HISTORY[user_id][-40:]


def get_history(user_id: str):
    return _HISTORY.get(user_id, [])


# ── Live Redis reader ─────────────────────────────────────────────────────────
import redis
import json
import os
from datetime import datetime, timezone


def get_context_from_redis() -> Optional[dict]:
    """
    Read live venue state from Redis written by the Go backend (P1).
    Returns None if Redis is unavailable or empty — caller uses demo fallback.
    """
    addr = os.getenv("REDIS_ADDR", "localhost:6379")
    host, port = addr.split(":")

    try:
        r = redis.Redis(
            host=host,
            port=int(port),
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
        )

        # Read zone states
        zones = []
        for key in r.scan_iter("zone:*:state"):
            parts = key.split(":")
            if len(parts) < 3:
                continue
            zone_id = parts[1]
            data = r.hgetall(key)
            if data:
                zones.append({
                    "zone_id": zone_id,
                    "occupancy": int(data.get("occupancy", 0)),
                    "density": float(data.get("density", 0.0)),
                    "flow_rate": float(data.get("flow_rate", 0.0)),
                    "status": data.get("status", "normal"),
                })

        if not zones:
            return None

        # Read active alerts
        alert_members = r.zrevrange("alerts:active", 0, 6)
        alerts = []
        for member in alert_members:
            try:
                obj = json.loads(member)
                alerts.append(obj.get("message", str(obj)))
            except Exception:
                alerts.append(str(member))

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_states": zones,
            "alerts": alerts,
        }

    except Exception:
        return None