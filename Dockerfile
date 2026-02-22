FROM alt:sisyphus

WORKDIR /app

RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-module-pip \
    gcc \
    libxml2-devel \
    libxslt-devel \
    python3-dev \
    && apt-get clean && \
    rm -rf /var/cache/apt

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY opds_bridge/ ./opds_bridge/

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV ABS_BASE="" \
    ABS_TOKEN="" \
    OPDS_BASIC_USER="" \
    OPDS_BASIC_PASS="" \
    CACHE_TTL_DEFAULT=30

EXPOSE 8000

CMD ["uvicorn", "opds_bridge.main:app", "--host", "0.0.0.0", "--port", "8000"]
