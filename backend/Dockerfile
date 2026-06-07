FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2-binary builds are not strictly needed (it ships wheels),
# but `uv` itself wants a recent CA bundle. Keep the image lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (the locked package manager for this project).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy dependency manifest first so Docker can cache the install layer.
COPY pyproject.toml ./
RUN uv sync --no-install-project

# Now copy the rest of the source.
COPY . .

# Make the project importable when the entrypoint runs.
ENV PYTHONPATH=/app

EXPOSE 8000

# uvicorn with reload disabled — this is a long-running server, not a dev loop.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
