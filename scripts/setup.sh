#!/bin/bash

# Smart Delay Detection System Setup Script

set -e

echo "🚀 Setting up Smart Delay Detection and Escalation System..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ Created .env file. Please review and update the configuration."
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs ml/models data

# Pull Docker images
echo "📦 Pulling Docker images..."
docker-compose pull

# Build services
echo "🔨 Building services..."
docker-compose build

# Start PostgreSQL first
echo "🐘 Starting PostgreSQL..."
docker-compose up -d postgres

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until docker-compose exec postgres pg_isready -U postgres; do
    sleep 2
done

# Initialize database
echo "🗃️ Initializing database..."
docker-compose run --rm ml_trainer python db/init_db.py

# Train ML model
echo "🧠 Training ML model..."
docker-compose run --rm --profile training ml_trainer

# Start all services
echo "🚀 Starting all services..."
docker-compose up -d

echo "✅ Setup completed successfully!"
echo ""
echo "🌐 Access the services:"
echo "  - Streamlit Dashboard: http://localhost:8501"
echo "  - Airflow UI: http://localhost:8080 (admin/admin)"
echo "  - PostgreSQL: localhost:5432"
echo ""
echo "📊 Monitor logs:"
echo "  docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "  docker-compose down"