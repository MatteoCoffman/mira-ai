"""LangChain tools for Mira receptionist."""

from agents.tools.lookup_business import lookup_business
from agents.tools.notify_owner import notify_owner
from agents.tools.save_lead import save_lead
from agents.tools.end_call import end_call
from agents.tools.save_call_record import save_call_record
from agents.tools.send_call_summary import send_call_summary

AGENT_TOOLS = [lookup_business, save_lead, end_call]
POST_CALL_TOOLS = [save_call_record, send_call_summary]
ALL_TOOLS = AGENT_TOOLS + [notify_owner] + POST_CALL_TOOLS

__all__ = [
    "lookup_business",
    "save_lead",
    "notify_owner",
    "end_call",
    "save_call_record",
    "send_call_summary",
    "AGENT_TOOLS",
    "POST_CALL_TOOLS",
    "ALL_TOOLS",
]
