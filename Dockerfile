# ---- Stage 1: Builder ----
# This stage installs everything we need to run the app.
# It will NOT be part of the final image — only what we copy out survives.
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy requirements first — this layer is cached until requirements.txt changes.
# If only app code changes, Docker skips reinstalling packages entirely.
COPY requirements.txt ./

# Create an isolated virtual environment so we can copy it cleanly to the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install ONLY production dependencies (we will not include pytest, httpx etc. at runtime).
# --no-cache-dir keeps the image smaller by not caching pip downloads.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY . .

# ---- Stage 2: Runtime ----
# This is the FINAL image. It starts fresh — nothing from Stage 1
# exists here unless we explicitly COPY it in.
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment from the builder stage.
# This is the bridge: all the installed packages, no build tools.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the application source code needed at runtime.
COPY --from=builder /app/main.py ./
COPY --from=builder /app/database.py ./
COPY --from=builder /app/models.py ./
COPY --from=builder /app/requirements.txt ./
COPY --from=builder /app/app ./app

# Security Hardening: Create a non-root system user and group.
# Running as root inside a container is dangerous — if an attacker exploits
# your app, they get root. With a non-root user, the blast radius is contained.
# -r = system user (no home directory, no login shell, minimal permissions)
RUN groupadd -r appgroup && useradd -r -g appgroup -s /bin/false appuser

# Switch to the non-root user for all subsequent commands (including CMD)
USER appuser

# Document which port the app listens on (does NOT open traffic by itself).
EXPOSE 3000

# Health check: Docker uses this to determine if the container is healthy.
# A container can be "running" but internally crashed — this distinguishes the two.
# --interval=30s   → check every 30 seconds
# --timeout=5s     → fail the check if no response in 5 seconds
# --start-period=10s → wait 10s after startup before first check (app needs time to boot)
# --retries=3      → mark as unhealthy only after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT:-3000}/health || exit 1

# The command that runs when the container starts.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
