#!/usr/bin/env python3

import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import sys

load_dotenv()

def create_database():
    """Create the database if it doesn't exist"""
    # Parse database URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    # Extract components from DATABASE_URL
    # Format: postgresql://user:password@host:port/database
    url_parts = database_url.replace('postgresql://', '').split('/')
    db_name = url_parts[-1]
    connection_parts = url_parts[0].split('@')
    user_pass = connection_parts[0].split(':')
    host_port = connection_parts[1].split(':')
    
    user = user_pass[0]
    password = user_pass[1] if len(user_pass) > 1 else ''
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 5432
    
    # Connect to PostgreSQL server (not specific database)
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'  # Connect to default postgres database
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cursor.fetchone():
            print(f"Creating database: {db_name}")
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"Database {db_name} created successfully")
        else:
            print(f"Database {db_name} already exists")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

def initialize_schema():
    """Initialize database schema from SQL file"""
    database_url = os.getenv('DATABASE_URL')
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Read and execute schema file
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        print("Executing database schema...")
        cursor.execute(schema_sql)
        conn.commit()
        print("Database schema initialized successfully")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error initializing schema: {e}")
        sys.exit(1)

def test_connection():
    """Test database connection and basic operations"""
    database_url = os.getenv('DATABASE_URL')
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT COUNT(*) FROM shipments")
        count = cursor.fetchone()[0]
        print(f"Current shipments in database: {count}")
        
        # Test insert (if no test data exists)
        if count == 0:
            print("Inserting test data...")
            cursor.execute("""
                INSERT INTO shipments (shipment_id, origin, destination, status, eta, distance_remaining_km, vehicle_speed_kmph, weather, traffic_level)
                VALUES ('TEST_INIT_001', 'Test Origin', 'Test Destination', 'In Transit', 
                        NOW() + INTERVAL '1 day', 1000, 60.0, 'Clear', 'Moderate')
                ON CONFLICT (shipment_id) DO NOTHING
            """)
            conn.commit()
            print("Test data inserted successfully")
        
        cursor.close()
        conn.close()
        print("Database connection test passed!")
        
    except Exception as e:
        print(f"Database connection test failed: {e}")
        sys.exit(1)

def main():
    """Main initialization function"""
    print("=== Smart Delay Detection System - Database Initialization ===")
    
    # Check environment variables
    required_vars = ['DATABASE_URL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        sys.exit(1)
    
    # Initialize database
    create_database()
    initialize_schema()
    test_connection()
    
    print("\n✅ Database initialization completed successfully!")
    print("You can now start the Kafka producer and Airflow DAG")

if __name__ == "__main__":
    main()