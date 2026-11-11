FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    MPLCONFIGDIR=/tmp

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 calc

COPY src/ src/
USER calc

# Streamable HTTP on :8000 (endpoint /mcp) by default; set MCP_TRANSPORT=stdio to let the client spawn it
ENV MCP_TRANSPORT=streamable-http \
    MCP_PORT=8000
EXPOSE 8000
CMD ["python", "-m", "mcpython.server"]
