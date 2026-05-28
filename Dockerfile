# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

COPY gradle/ gradle/
COPY gradlew settings.gradle.kts build.gradle.kts ./
COPY analyzers/pdfbox/build.gradle.kts analyzers/pdfbox/build.gradle.kts
COPY analyzers/pdfbox/src/ analyzers/pdfbox/src/
RUN ./gradlew :analyzers:pdfbox:fatJar --no-daemon

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRESSCHECK_PDFBOX_ANALYZER_JAR=/opt/presscheck/pdfbox-analyzer.jar

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ghostscript openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin presscheck

COPY --from=builder /dist/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl

RUN mkdir -p /opt/presscheck /work \
    && chown -R presscheck:presscheck /opt/presscheck /work
COPY --from=builder /app/analyzers/pdfbox/build/libs/pdfbox-analyzer.jar /opt/presscheck/pdfbox-analyzer.jar

WORKDIR /work
USER presscheck

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"

CMD ["presscheck-api", "--host", "0.0.0.0", "--port", "8000"]
