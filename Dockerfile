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

# stdio by default (LM Studio spawns the container); set MCP_TRANSPORT=streamable-http for HTTP
CMD ["python", "-m", "mcpython.server"]
