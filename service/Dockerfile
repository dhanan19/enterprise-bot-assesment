# ---- build stage: compile bytecode so the runtime stage needs nothing else ----
FROM python:3.12.7-slim AS build
WORKDIR /src
COPY app.py .
RUN python -m compileall -q app.py

# ---- runtime stage ----
FROM python:3.12.7-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# fixed numeric UID so Kubernetes runAsNonRoot can verify it
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /src/app.py .
USER 10001:10001
EXPOSE 8080
CMD ["python", "app.py"]
