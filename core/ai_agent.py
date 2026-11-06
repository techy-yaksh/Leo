"""
Backward-compatibility adapter for core.ai_agent.
Redirects calls to the modularized services.agent_service module.
"""

from services.agent_service import (
    process_agent_command,
    conversation_history,
    TOOLS,
    TOOL_MAP,
    groq_client
)

__all__ = [
    "process_agent_command",
    "conversation_history",
    "TOOLS",
    "TOOL_MAP",
    "groq_client"
]
