"""Test configuration — set required env vars before any imports."""
import os

from cryptography.fernet import Fernet

# Generate a valid Fernet key for tests (required by TokenStore)
os.environ.setdefault("TEAMS_MCP_TOKEN_KEY", Fernet.generate_key().decode())
