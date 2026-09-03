FROM python:3.11-slim

# Prevent Python from writing pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8501

WORKDIR /app

# Install system utilities required for headless browser setup
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements
COPY requirements.txt .

# Install Python packages and Chromium dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy all application code
COPY . .

# Ensure storage directories exist
RUN mkdir -p saved_leads

EXPOSE 8501

# Launch Streamlit server bound to 0.0.0.0
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
