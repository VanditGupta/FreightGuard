#!/bin/bash

# Start Kafka Producer Script

set -e

echo "📡 Starting Kafka producer for shipment simulation..."

# Check if Kafka is running
if ! docker-compose ps kafka | grep -q "Up"; then
    echo "🚀 Starting Kafka infrastructure..."
    docker-compose up -d zookeeper kafka
    
    # Wait for Kafka
    echo "⏳ Waiting for Kafka to be ready..."
    sleep 30
fi

# Start producer
echo "📦 Starting shipment data producer..."
docker-compose up -d kafka_producer

echo "✅ Kafka producer started successfully!"
echo "📊 Monitor producer logs:"
echo "  docker-compose logs -f kafka_producer"