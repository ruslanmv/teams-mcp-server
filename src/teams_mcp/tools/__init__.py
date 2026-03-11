from .tools_auth import TOOLS as AUTH_TOOLS
from .tools_calendar import TOOLS as CAL_TOOLS
from .tools_chat import TOOLS as CHAT_TOOLS
from .tools_calls import TOOLS as CALL_TOOLS
from .tools_meeting_chat import TOOLS as MEETING_CHAT_TOOLS
from .tools_meeting_join import TOOLS as MEETING_JOIN_TOOLS
from .tools_voice import TOOLS as VOICE_TOOLS
from .tools_acs import TOOLS as ACS_TOOLS
from .tools_persona import TOOLS as PERSONA_TOOLS

ALL_TOOLS = [
    *AUTH_TOOLS,
    *CAL_TOOLS,
    *CHAT_TOOLS,
    *CALL_TOOLS,
    *MEETING_CHAT_TOOLS,
    *MEETING_JOIN_TOOLS,
    *VOICE_TOOLS,
    *ACS_TOOLS,
    *PERSONA_TOOLS,
]
