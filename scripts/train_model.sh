#!/bin/bash

# Train ML Model Script

set -e

echo "🧠 Training ML model for delay prediction..."

# Check if environment is set up
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please run setup.sh first."
    exit 1
fi

# Load environment variables
source .env

# Check if database is running
if ! docker-compose ps postgres | grep -q "Up"; then
    echo "🐘 Starting PostgreSQL..."
    docker-compose up -d postgres
    
    # Wait for PostgreSQL
    echo "⏳ Waiting for PostgreSQL..."
    until docker-compose exec postgres pg_isready -U postgres; do
        sleep 2
    done
fi

# Run model training
echo "🔬 Running model training..."
docker-compose run --rm --profile training ml_trainer

echo "✅ Model training completed!"
echo "📊 Model saved to: $ML_MODEL_PATH"