# Multi-stage Dockerfile for React Performance Code Review Agent
# Stage 1: Build TypeScript Parser
FROM node:20-alpine AS parser-builder

WORKDIR /app/parser

# Copy parser files
COPY parser/package*.json ./
COPY parser/tsconfig.json ./
COPY parser/src ./src

# Install dependencies and build
RUN npm ci && npm run build

# Stage 2: Python Runtime
FROM python:3.12-slim

WORKDIR /app

# Install Node.js (needed to run parser)
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy parser build from stage 1
COPY --from=parser-builder /app/parser/dist /app/parser/dist
COPY --from=parser-builder /app/parser/package.json /app/parser/package.json

# Copy Python agent files
COPY agents/requirements.txt /app/agents/
COPY agents/*.py /app/agents/

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/agents/requirements.txt

# Copy remaining files
COPY review-pr.sh /app/
COPY .github /app/.github
COPY examples /app/examples

# Make scripts executable
RUN chmod +x /app/review-pr.sh

# Set working directory
WORKDIR /app

# Environment variables (override in docker-compose or runtime)
ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import sys; sys.exit(0)"

# Default command
CMD ["python3", "agents/main.py", "--help"]

