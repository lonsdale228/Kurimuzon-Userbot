FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PIP_NO_CACHE_DIR=1

RUN apt update && apt install -y --no-install-recommends \
    libcairo2 \
    git \
    build-essential \
    ffmpeg && \
    rm -rf /var/lib/apt/lists /var/cache/apt/archives /tmp/*

# Create application directory
RUN mkdir /app

# Copy application code to the container
COPY . /app
WORKDIR /app

# Upgrade pip and install required Python packages
RUN pip3 install --upgrade pip setuptools wheel
RUN pip3 install --no-warn-script-location --no-cache-dir -U uvloop -r requirements.txt

# Set timezone
ENV TZ=Europe/Kyiv

EXPOSE 8080

# Start the application
CMD ["python3", "main.py"]
