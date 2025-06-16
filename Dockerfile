# Multi-stage Dockerfile for Smart Delay Detection System

# Base Python image
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for logs and models
RUN mkdir -p /app/logs /app/ml/models

# Default command
CMD ["python", "--version"]

# Kafka Producer Stage
FROM base as producer
WORKDIR /app
CMD ["python", "kafka/producer.py"]

# Airflow Stage
FROM base as airflow
RUN pip install --no-cache-dir apache-airflow==2.8.1 apache-airflow-providers-postgres
ENV AIRFLOW_HOME=/opt/airflow
WORKDIR /opt/airflow
COPY dags/ /opt/airflow/dags/
COPY ml/ /opt/airflow/ml/
COPY utils/ /opt/airflow/utils/
CMD ["airflow", "webserver"]

# Streamlit Stage
FROM base as streamlit
WORKDIR /app
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# ML Training Stage
FROM base as ml
WORKDIR /app
CMD ["python", "ml/train_model.py"]