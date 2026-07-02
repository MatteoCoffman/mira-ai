"""LangChain tools for Mira receptionist."""

from agents.tools.lookup_business import lookup_business
from agents.tools.notify_owner import notify_owner
from agents.tools.save_lead import save_lead
from agents.tools.end_call import end_call

# Tools the LLM may call — notify_owner is supervisor-only to avoid duplicate SMS.
AGENT_TOOLS = [lookup_business, save_lead, end_call]
ALL_TOOLS = AGENT_TOOLS + [notify_owner]

__all__ = [
    "lookup_business",
    "save_lead",
    "notify_owner",
    "end_call",
    "AGENT_TOOLS",
    "ALL_TOOLS",
]
