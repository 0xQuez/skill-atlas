# Skill Atlas service (JSON API + MCP streamable HTTP at /mcp). Built locally; NOT deployed.
FROM python:3.13-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app.py .
COPY out/full/verdicts_compact.parquet out/full/headline.json /data/
ENV SKILL_ATLAS_DATA=/data/verdicts_compact.parquet SKILL_ATLAS_STATS=/data/headline.json DUCKDB_MEMORY=256MB DUCKDB_THREADS=2
EXPOSE 8765
# Container binds 0.0.0.0 inside the container only; publish it to localhost: docker run -p 127.0.0.1:8765:8765 skill-atlas
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765"]
