from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class ZoneState(BaseModel):
    zone_id: str
    occupancy: int
    density: float
    flow_rate: float
    status: Literal["normal", "warning", "critical"]


class VenueContext(BaseModel):
    timestamp: str
    zone_states: List[ZoneState]
    alerts: List[str]
    forecast: Optional[dict] = None


class NLPQuery(BaseModel):
    user_id: str
    query: str
    intent: Optional[Literal["status", "alert", "forecast", "action", "history"]] = None
    context: Optional[VenueContext] = None


class AIResponse(BaseModel):
    assistant: str
    detail: str
    recommended_actions: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None


class SystemPrompt(BaseModel):
    text: str
    safe: bool = True