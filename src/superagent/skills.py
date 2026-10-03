from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


Tool = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    tools: dict[str, Tool]


async def telecom_timeline(arguments: dict) -> dict:
    events = arguments.get("events", ["LINK_FLAP", "REGISTRATION_RETRY", "RECOVERED"])
    return {"domain": "telecom", "timeline": [{"index": i, "event": event} for i, event in enumerate(events)], "synthetic": True}


async def refinery_scenario(arguments: dict) -> dict:
    demand = float(arguments.get("demand", 100))
    capacity = float(arguments.get("capacity", 120))
    return {"domain": "refinery", "feasible": demand <= capacity, "margin": capacity - demand, "synthetic": True}


async def legal_research(arguments: dict) -> dict:
    question = str(arguments.get("question", ""))
    return {"domain": "legal", "question": question, "citations": ["fictional-provision:8"], "requires_professional_review": True}


async def propose_change(arguments: dict) -> dict:
    return {"proposal": arguments, "executed": False, "message": "Advisory proposal only; no operational system was modified."}


def default_skills() -> dict[str, Skill]:
    return {
        "telecom": Skill("telecom", "Synthetic incident timeline analysis", {"build_timeline": telecom_timeline, "propose_change": propose_change}),
        "refinery": Skill("refinery", "Synthetic planning scenario validation", {"check_scenario": refinery_scenario}),
        "legal": Skill("legal", "Citation-first fictional legal research", {"research": legal_research}),
    }
