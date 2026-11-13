# Skill Atlas API: read-only JSON + MCP on port 7860 (Hugging Face Docker Space).
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py entrypoint.py ./
ENV PORT=7860 DUCKDB_MEMORY=1GB DUCKDB_THREADS=2 ATLAS_PRODUCTION=1 \
    RATE_LIMIT_PER_MIN=60 CORS_ORIGINS=* MAX_REQUEST_BODY=1048576 \
    SKILL_ATLAS_DATA_DIR=/data
EXPOSE 7860
CMD ["python", "entrypoint.py"]
