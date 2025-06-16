#!/usr/bin/env python3

import json
import random
import time
from datetime import datetime, timedelta
from kafka import KafkaProducer
from typing import Dict, List
import os
from dotenv import load_dotenv

load_dotenv()

class ShipmentDataGenerator:
    """Generates realistic shipment data for the supply chain simulation"""
    
    def __init__(self):
        self.cities = [
            "Los Angeles", "New York", "Chicago", "Houston", "Phoenix",
            "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
            "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
            "San Francisco", "Indianapolis", "Seattle", "Denver", "Boston"
        ]
        
        self.weather_conditions = ["Clear", "Rain", "Snow", "Fog", "Storm"]
        self.traffic_levels = ["Light", "Moderate", "Heavy", "Very Heavy"]
        self.statuses = ["In Transit", "At Hub", "Out for Delivery", "Delayed"]
        
        # Distance matrix (simplified - in real world, use routing APIs)
        self.city_distances = self._generate_distance_matrix()
        
    def _generate_distance_matrix(self) -> Dict[str, Dict[str, int]]:
        """Generate approximate distances between major cities"""
        distances = {}
        for origin in self.cities:
            distances[origin] = {}
            for dest in self.cities:
                if origin == dest:
                    distances[origin][dest] = 0
                else:
                    # Simplified distance calculation
                    distances[origin][dest] = random.randint(500, 4000)
        return distances
    
    def generate_shipment(self, shipment_id: str = None) -> Dict:
        """Generate a single shipment record"""
        if not shipment_id:
            shipment_id = f"SHIP{random.randint(1000, 9999)}"
            
        origin = random.choice(self.cities)
        destination = random.choice([city for city in self.cities if city != origin])
        
        # Calculate base ETA (simplified)
        distance = self.city_distances[origin][destination]
        base_travel_time = distance / 70  # Average 70 km/h
        
        current_time = datetime.now()
        eta = current_time + timedelta(hours=base_travel_time)
        
        # Add some realistic variation
        weather = random.choice(self.weather_conditions)
        traffic = random.choice(self.traffic_levels)
        
        # Adjust speed based on conditions
        base_speed = random.uniform(45, 80)
        if weather in ["Rain", "Snow", "Fog"]:
            base_speed *= 0.8
        if traffic in ["Heavy", "Very Heavy"]:
            base_speed *= 0.7
            
        # Calculate remaining distance (shipment in progress)
        progress = random.uniform(0.1, 0.9)
        distance_remaining = int(distance * (1 - progress))
        
        # Choose current location based on progress
        if progress < 0.3:
            current_location = origin
        elif progress > 0.7:
            current_location = destination
        else:
            current_location = random.choice(self.cities)
            
        return {
            "shipment_id": shipment_id,
            "origin": origin,
            "destination": destination,
            "timestamp": current_time.isoformat() + "Z",
            "status": random.choice(self.statuses),
            "eta": eta.isoformat() + "Z",
            "current_location": current_location,
            "vehicle_speed_kmph": round(base_speed, 1),
            "distance_remaining_km": distance_remaining,
            "weather": weather,
            "traffic_level": traffic
        }

class ShipmentProducer:
    """Kafka producer for shipment data"""
    
    def __init__(self):
        self.bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        self.topic = os.getenv('KAFKA_TOPIC', 'shipment_updates')
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            retry_backoff_ms=1000,
            request_timeout_ms=30000
        )
        
        self.data_generator = ShipmentDataGenerator()
        self.active_shipments = {}
        
    def send_shipment_update(self, shipment_data: Dict):
        """Send a single shipment update to Kafka"""
        try:
            future = self.producer.send(
                self.topic,
                key=shipment_data['shipment_id'],
                value=shipment_data
            )
            
            # Optional: wait for confirmation
            record_metadata = future.get(timeout=10)
            print(f"Sent shipment {shipment_data['shipment_id']} to {record_metadata.topic}:{record_metadata.partition}")
            
        except Exception as e:
            print(f"Error sending shipment update: {e}")
    
    def simulate_continuous_updates(self, num_shipments: int = 50, update_interval: int = 30):
        """Simulate continuous shipment updates"""
        print(f"Starting shipment simulation with {num_shipments} active shipments")
        print(f"Updates every {update_interval} seconds")
        
        # Initialize shipments
        for i in range(num_shipments):
            shipment = self.data_generator.generate_shipment()
            self.active_shipments[shipment['shipment_id']] = shipment
            
        try:
            while True:
                # Update and send all shipments
                for shipment_id in list(self.active_shipments.keys()):
                    # Update existing shipment with new data
                    updated_shipment = self._update_shipment(self.active_shipments[shipment_id])
                    
                    if updated_shipment:
                        self.active_shipments[shipment_id] = updated_shipment
                        self.send_shipment_update(updated_shipment)
                    else:
                        # Shipment delivered, create new one
                        new_shipment = self.data_generator.generate_shipment()
                        self.active_shipments[new_shipment['shipment_id']] = new_shipment
                        del self.active_shipments[shipment_id]
                        self.send_shipment_update(new_shipment)
                
                print(f"Updated {len(self.active_shipments)} shipments")
                time.sleep(update_interval)
                
        except KeyboardInterrupt:
            print("Stopping shipment simulation...")
        finally:
            self.producer.close()
    
    def _update_shipment(self, shipment: Dict) -> Dict:
        """Update an existing shipment with new status"""
        # Simulate shipment progress
        current_distance = shipment['distance_remaining_km']
        speed = shipment['vehicle_speed_kmph']
        
        # Reduce distance (simulate movement)
        distance_traveled = random.uniform(10, 50)  # km in update interval
        new_distance = max(0, current_distance - distance_traveled)
        
        if new_distance <= 0:
            # Shipment delivered
            return None
            
        # Update timestamp
        shipment['timestamp'] = datetime.now().isoformat() + "Z"
        shipment['distance_remaining_km'] = int(new_distance)
        
        # Possibly update status and conditions
        if random.random() < 0.1:  # 10% chance to change weather
            shipment['weather'] = random.choice(self.data_generator.weather_conditions)
        
        if random.random() < 0.1:  # 10% chance to change traffic
            shipment['traffic_level'] = random.choice(self.data_generator.traffic_levels)
            
        # Update speed based on conditions
        base_speed = random.uniform(45, 80)
        if shipment['weather'] in ["Rain", "Snow", "Fog"]:
            base_speed *= 0.8
        if shipment['traffic_level'] in ["Heavy", "Very Heavy"]:
            base_speed *= 0.7
        shipment['vehicle_speed_kmph'] = round(base_speed, 1)
        
        return shipment

def main():
    """Main function to start the producer"""
    producer = ShipmentProducer()
    
    # Run continuous simulation
    producer.simulate_continuous_updates(
        num_shipments=int(os.getenv('NUM_SHIPMENTS', 50)),
        update_interval=int(os.getenv('UPDATE_INTERVAL', 30))
    )

if __name__ == "__main__":
    main()