FROM python:3.11-slim-bookworm

# Add a non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY main.py sources.json state.json .env* ./

# Give ownership to appuser
RUN chown -R appuser:appgroup /app

USER appuser

ENV PYTHONUNBUFFERED=1
ENV ERROR_LOG_FILE=/app/error.log

CMD ["python", "-u", "main.py"]
