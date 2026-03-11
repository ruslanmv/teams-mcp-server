# Minimal read/write set for Teams + Calendar + Meeting Chat
DEFAULT_SCOPES = [
    "offline_access",
    "User.Read",
    "Chat.Read",
    "Chat.ReadWrite",
    "ChatMessage.Read",       # read meeting chat messages
    "ChatMember.Read",        # list meeting participants
    "ChannelMessage.Send",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
    "Calendars.Read",
    "OnlineMeetings.Read",    # access online meeting metadata
]
