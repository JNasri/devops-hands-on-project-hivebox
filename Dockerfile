# Use an official Python runtime as a parent image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Create a non-root user and group for running the application
RUN addgroup --system hivebox \
    && adduser --system --ingroup hivebox --home /app hivebox
# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Copy application files and set ownership to the non-root user
COPY --chown=hivebox:hivebox main.py ./
COPY --chown=hivebox:hivebox templates ./templates
COPY --chown=hivebox:hivebox static ./static

USER hivebox
EXPOSE 5000

# Set up a health check to monitor the application
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2)"]
# Use Gunicorn to run the application with specified parameters
CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "--threads=8", "--timeout=30", "main:app"]
