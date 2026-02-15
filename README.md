# Teams MCP Server (HomePilot-Compatible)

A standalone MCP server that exposes Microsoft Teams + Calendar capabilities using Microsoft Graph.

## Why this repo exists
HomePilot already supports MCP servers using a JSON-RPC style `/rpc` endpoint.
This server runs independently and can be registered in HomePilot's MCP gateway/catalog.

## Features (v0.1)
- Device Code auth (no callback server needed)
- List Teams chats, send chat messages
- List joined teams + channels, send channel messages
- List calendar events (for meetings), fetch join link
- Scaffold tool for joining calls (requires Azure Bot/Calling infra)

## Setup

### 1) Create Entra app (Azure AD)
Create an app registration:
- Platform: **Mobile and desktop applications** (public client)
- Enable **Allow public client flows**
- Record **Client ID**

Tenant can be `common` for personal accounts or your tenant id for org.

### 2) Configure env
Copy `.env.example` to `.env` and fill:
- `MS_CLIENT_ID`
- `TEAMS_MCP_TOKEN_KEY`

Generate a token key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3) Run locally
```bash
pip install -e .
teams-mcp
```

### 4) Authenticate

Call tools:
- `teams.auth.device_code_start`
- `teams.auth.device_code_poll`

## HomePilot integration

Register this server in your MCP catalog / gateway config (example):

```json
{
  "name": "teams-mcp-server",
  "url": "http://localhost:9106/rpc"
}
```

Then your Persona can call:
- `teams.meetings.list_today`
- `teams.chats.list_recent`
- `teams.chats.send_message`
- `teams.channels.send_message`

## Docker deployment

```bash
cd docker
docker compose up -d
```

## Call participation (real-time voice)

To have the persona *join a Teams call as a participant* you must add cloud infra:
- Bot Framework registration + Graph Communications API
- or Azure Communication Services (Teams interop)

This repo already defines `teams.calls.join_meeting` so you can keep the contract stable.

## Tool reference

### Authentication
- `teams.auth.device_code_start()` - Start device code flow
- `teams.auth.device_code_poll(device_code)` - Poll for completion
- `teams.auth.status()` - Check auth status
- `teams.auth.logout()` - Clear tokens

### Chats
- `teams.chats.list_recent(top=10)` - List recent chats
- `teams.chats.send_message(chat_id, text)` - Send chat message

### Teams & Channels
- `teams.teams.list_joined()` - List joined teams
- `teams.channels.list(team_id)` - List team channels
- `teams.channels.send_message(team_id, channel_id, text)` - Send channel message

### Meetings
- `teams.meetings.list_today()` - Today's calendar events
- `teams.meetings.list_range(time_min, time_max)` - Events in range
- `teams.meetings.get_join_link(event_id)` - Get join URL

### Calls (Scaffold)
- `teams.calls.join_meeting(meeting_join_url)` - Join as bot (requires Azure infra)

## License

MIT
