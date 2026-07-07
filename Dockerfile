FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .

RUN useradd --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /data/public /data/cache \
    && chown -R app:app /data

USER app
VOLUME ["/data"]
EXPOSE 8000 8730

HEALTHCHECK --interval=1m --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/stats/dn42/delegated-dn42-latest', timeout=5).close()" || exit 1

ENTRYPOINT ["dn42-rir-statistics"]
CMD ["serve", "--output-dir", "/data/public", "--cache-dir", "/data/cache/dn42-registry", "--web-host", "0.0.0.0", "--web-port", "8000", "--rsync-host", "0.0.0.0", "--rsync-port", "8730", "--rsync-config", "/data/rsyncd.conf", "--daily-at", "03:00"]
