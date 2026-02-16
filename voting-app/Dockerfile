FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files but exclude data directory
COPY *.py .
COPY static/ static/
COPY templates/ templates/

# Create empty data directory (will be mounted as volume in production)
RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "app.py"]
