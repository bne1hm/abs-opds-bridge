FROM python:3.13-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY opds_bridge/ ./opds_bridge/

RUN adduser -D -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV ABS_BASE="http://localhost:13378" \
    ABS_TOKEN="" \
    OPDS_BASIC_USER="" \
    OPDS_BASIC_PASS="" \
    CACHE_TTL_DEFAULT=30

EXPOSE 8000

CMD ["uvicorn", "opds_bridge.main:app", "--host", "0.0.0.0", "--port", "8000"]
