# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# Set working directory
WORKDIR /app

FROM base AS builder

# Install build dependencies (if any are needed, e.g. gcc for some pip packages)
# In this case, requirements are pure Python, so no build deps needed

# Copy requirements file only (for better cache usage)
COPY --link requirement.txt ./

# Create venv and install dependencies using pip cache
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -r requirement.txt

FROM base AS final

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code (excluding .env, .git, etc. via .dockerignore)
COPY --link app.py ./
COPY --link templates ./templates
COPY --link static ./static
#COPY --link SECURITY.md ./
COPY --link requirement.txt ./
#COPY --link .env ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Switch to non-root user
USER appuser

# Expose Flask default port
EXPOSE 5000

# Entrypoint
#CMD ["python", "app.py"]
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
