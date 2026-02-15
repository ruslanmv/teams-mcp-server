FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src

RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

ENV TEAMS_MCP_HOST=0.0.0.0
ENV TEAMS_MCP_PORT=9106

EXPOSE 9106
CMD ["teams-mcp"]
