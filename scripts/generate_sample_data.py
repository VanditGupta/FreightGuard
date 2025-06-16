#!/usr/bin/env python3

import psycopg2
import random
from datetime import datetime, timedelta
import uuid

# Database connection
DATABASE_URL = "postgresql://postgres:postgres@postgres:5432/delay_detection"

# Sample data for realistic values
CITIES = [
    'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia',
    'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville',
    'Fort Worth', 'Columbus', 'Charlotte', 'San Francisco', 'Indianapolis',
    'Seattle', 'Denver', 'Washington DC', 'Boston', 'El Paso', 'Nashville',
    'Detroit', 'Oklahoma City', 'Portland', 'Las Vegas', 'Memphis', 'Louisville',
    'Baltimore', 'Milwaukee', 'Albuquerque', 'Tucson', 'Fresno', 'Sacramento',
    'Kansas City', 'Mesa', 'Atlanta', 'Omaha', 'Colorado Springs', 'Raleigh',
    'Miami', 'Virginia Beach', 'Oakland', 'Minneapolis', 'Tulsa', 'Arlington',
    'Tampa', 'New Orleans', 'Wichita'
]

STATUSES = ['In Transit', 'At Hub', 'Out for Delivery', 'Delayed', 'Delivered']
WEATHER_CONDITIONS = ['Clear', 'Rainy', 'Cloudy', 'Stormy', 'Foggy', 'Snowy']
TRAFFIC_LEVELS = ['Low', 'Medium', 'High']
ALERT_TYPES = ['Weather', 'Traffic', 'Delay', 'Mechanical', 'Route', 'Security']
ALERT_SEVERITIES = ['Low', 'Medium', 'High', 'Critical']

def generate_shipment_id():
    """Generate a unique shipment ID"""
    return f"SH{random.randint(1000, 9999)}"

def generate_shipments(conn, num_records=1000):
    """Generate random shipment records"""
    cursor = conn.cursor()
    
    print(f"Generating {num_records} shipment records...")
    
    for i in range(num_records):
        shipment_id = generate_shipment_id()
        origin = random.choice(CITIES)
        destination = random.choice([city for city in CITIES if city != origin])
        current_location = random.choice([origin, destination, random.choice(CITIES)])
        status = random.choice(STATUSES)
        distance_remaining = round(random.uniform(50, 3000), 2)
        vehicle_speed = round(random.uniform(0, 80), 2) if status != 'At Hub' else 0
        weather = random.choice(WEATHER_CONDITIONS)
        traffic_level = random.choice(TRAFFIC_LEVELS)
        
        # Generate ETA (1 hour to 5 days from now)
        eta = datetime.now() + timedelta(
            hours=random.randint(1, 120)
        )
        
        # Generate updated_at (within last 24 hours)
        updated_at = datetime.now() - timedelta(
            hours=random.uniform(0, 24)
        )
        
        created_at = updated_at - timedelta(
            hours=random.uniform(0, 48)
        )
        
        try:
            cursor.execute("""
                INSERT INTO shipments (
                    shipment_id, origin, destination, current_location, status,
                    distance_remaining_km, vehicle_speed_kmph, weather, traffic_level,
                    eta, updated_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (shipment_id) DO NOTHING
            """, (
                shipment_id, origin, destination, current_location, status,
                distance_remaining, vehicle_speed, weather, traffic_level,
                eta, updated_at, created_at
            ))
        except Exception as e:
            print(f"Error inserting shipment {shipment_id}: {e}")
            continue
        
        if (i + 1) % 100 == 0:
            print(f"  Inserted {i + 1} shipments...")
    
    conn.commit()
    print(f"✅ Generated {num_records} shipment records")

def generate_delay_predictions(conn, num_records=1000):
    """Generate random delay prediction records"""
    cursor = conn.cursor()
    
    # Get existing shipment IDs
    cursor.execute("SELECT shipment_id FROM shipments")
    shipment_ids = [row[0] for row in cursor.fetchall()]
    
    if not shipment_ids:
        print("❌ No shipments found. Generate shipments first.")
        return
    
    print(f"Generating {num_records} delay prediction records...")
    
    for i in range(num_records):
        shipment_id = random.choice(shipment_ids)
        delay_probability = round(random.uniform(0, 1), 4)
        predicted_delay_minutes = random.randint(0, 300) if delay_probability > 0.3 else 0
        model_version = random.choice(['v1.0', 'v1.1', 'v1.2'])
        
        # Generate prediction timestamp (within last 2 hours)
        prediction_timestamp = datetime.now() - timedelta(
            minutes=random.randint(0, 120)
        )
        
        # Generate features JSON
        features = {
            'distance': round(random.uniform(100, 3000), 2),
            'weather_score': round(random.uniform(0, 1), 2),
            'traffic_score': round(random.uniform(0, 1), 2),
            'historical_delay': round(random.uniform(0, 1), 2)
        }
        
        try:
            cursor.execute("""
                INSERT INTO delay_predictions (
                    shipment_id, delay_probability, predicted_delay_minutes,
                    prediction_timestamp, model_version, features
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                shipment_id, delay_probability, predicted_delay_minutes,
                prediction_timestamp, model_version, str(features).replace("'", '"')
            ))
        except Exception as e:
            print(f"Error inserting prediction for {shipment_id}: {e}")
            continue
        
        if (i + 1) % 100 == 0:
            print(f"  Inserted {i + 1} predictions...")
    
    conn.commit()
    print(f"✅ Generated {num_records} delay prediction records")

def generate_alerts(conn, num_records=1000):
    """Generate random alert records"""
    cursor = conn.cursor()
    
    # Get existing shipment IDs
    cursor.execute("SELECT shipment_id FROM shipments")
    shipment_ids = [row[0] for row in cursor.fetchall()]
    
    if not shipment_ids:
        print("❌ No shipments found. Generate shipments first.")
        return
    
    print(f"Generating {num_records} alert records...")
    
    alert_templates = {
        'Weather': [
            ('Severe Weather Alert', 'Heavy rain expected in route'),
            ('Storm Warning', 'Thunderstorm approaching delivery area'),
            ('Snow Alert', 'Heavy snowfall may cause delays'),
            ('Fog Warning', 'Dense fog reducing visibility')
        ],
        'Traffic': [
            ('Traffic Congestion', 'Major traffic jam reported on route'),
            ('Road Closure', 'Highway closure due to construction'),
            ('Accident Alert', 'Multi-vehicle accident causing delays'),
            ('Rush Hour Delay', 'Heavy traffic during peak hours')
        ],
        'Delay': [
            ('Extended Delay', 'Vehicle breakdown causing significant delay'),
            ('Route Deviation', 'Driver taking alternate route'),
            ('Loading Delay', 'Delayed departure from warehouse'),
            ('Customs Delay', 'Package held at customs checkpoint')
        ],
        'Mechanical': [
            ('Vehicle Breakdown', 'Mechanical failure reported'),
            ('Tire Issue', 'Flat tire requiring roadside assistance'),
            ('Engine Problem', 'Engine overheating detected'),
            ('Maintenance Required', 'Scheduled maintenance overdue')
        ],
        'Route': [
            ('Route Optimization', 'Better route found, updating GPS'),
            ('Detour Required', 'Road closure forcing detour'),
            ('GPS Error', 'Navigation system malfunction'),
            ('Address Issue', 'Delivery address needs verification')
        ],
        'Security': [
            ('Security Check', 'Package requires additional screening'),
            ('Theft Alert', 'Suspicious activity reported in area'),
            ('Access Denied', 'Unable to access delivery location'),
            ('Documentation Issue', 'Missing or invalid shipping documents')
        ]
    }
    
    for i in range(num_records):
        shipment_id = random.choice(shipment_ids)
        alert_type = random.choice(ALERT_TYPES)
        severity = random.choice(ALERT_SEVERITIES)
        
        # Get random title and message for the alert type
        title, message = random.choice(alert_templates[alert_type])
        
        # Generate triggered_at (within last 48 hours)
        triggered_at = datetime.now() - timedelta(
            hours=random.uniform(0, 48)
        )
        
        is_active = random.choice([True, False])
        resolved_at = None
        resolution_notes = None
        
        if not is_active:
            resolved_at = triggered_at + timedelta(
                hours=random.uniform(0.5, 24)
            )
            resolution_notes = "Issue resolved automatically"
        
        try:
            cursor.execute("""
                INSERT INTO alerts (
                    shipment_id, alert_type, severity, title, message,
                    triggered_at, is_active, resolved_at, resolution_notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                shipment_id, alert_type, severity, title, message,
                triggered_at, is_active, resolved_at, resolution_notes
            ))
        except Exception as e:
            print(f"Error inserting alert for {shipment_id}: {e}")
            continue
        
        if (i + 1) % 100 == 0:
            print(f"  Inserted {i + 1} alerts...")
    
    conn.commit()
    print(f"✅ Generated {num_records} alert records")

def main():
    """Main function to generate all sample data"""
    try:
        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        print("✅ Connected to database")
        
        # Generate data for each table
        generate_shipments(conn, 1000)
        generate_delay_predictions(conn, 1000)
        generate_alerts(conn, 1000)
        
        # Print final counts
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM shipments")
        shipment_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM delay_predictions")
        prediction_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM alerts")
        alert_count = cursor.fetchone()[0]
        
        print("\n📊 Final Record Counts:")
        print(f"  Shipments: {shipment_count}")
        print(f"  Delay Predictions: {prediction_count}")
        print(f"  Alerts: {alert_count}")
        
        conn.close()
        print("\n🎉 Sample data generation completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 