FROM python:3.12-alpine

# Build-time proxy args (for users in network-restricted regions)
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Install system dependencies
RUN apk add --no-cache \
    bash \
    tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime 2>/dev/null || true \
    && echo "Asia/Shanghai" > /etc/timezone 2>/dev/null || true

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create wrapper script for simplified CLI
RUN echo '#!/bin/bash' > /usr/local/bin/reset-2fa && \
    echo 'python -m app.cli reset-2fa "$@"' >> /usr/local/bin/reset-2fa && \
    chmod +x /usr/local/bin/reset-2fa

# Create necessary directories
RUN mkdir -p /data /userdata

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

# Run the application
CMD ["python", "-m", "app.main"]
