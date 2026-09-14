# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jre-jammy@sha256:bce52ea7da1f72e6bf5bec505e63b6eb55ba79ad1226903579f77eab1a80139a AS graphhopper
ADD --checksum=sha256:b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar /opt/graphhopper.jar
WORKDIR /data
COPY data/corridor/graphhopper/real_evidence/v3/graphhopper-config.yml /data/
COPY data/corridor/graphhopper/real_evidence/v3/*.json /data/
CMD ["java", "-Xmx3g", "-jar", "/opt/graphhopper.jar", "server", "/data/graphhopper-config.yml"]

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS api
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data
RUN useradd --create-home app && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" NER_LENS_ENV_FILE=""
CMD ["uvicorn", "ner_lens.app:app", "--host", "0.0.0.0", "--port", "8000"]
