#!/usr/bin/env python3

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from kafka import KafkaConsumer
import json
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys

# Add project root to path for imports
sys.path.append('/opt/airflow/dags')
sys.path.append('/home/project')

from ml.predict_delay import DelayPredictor
from utils.alerting import AlertManager

# Default arguments for the DAG
default_args = {
    'owner': 'supply-chain-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Create DAG
dag = DAG(
    'delay_prediction_pipeline',
    default_args=default_args,
    description='Smart Delay Detection and Escalation System',
    schedule_interval=timedelta(hours=1),  # Run every hour
    catchup=False,
    max_active_runs=1,
    tags=['ml', 'supply-chain', 'prediction']
)

def consume_kafka_data(**context):
    """Consume shipment data from Kafka topic"""
    print("Starting Kafka consumer...")
    
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    topic = os.getenv('KAFKA_TOPIC', 'shipment_updates')
    
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=30000,  # 30 second timeout
            auto_offset_reset='latest'
        )
        
        messages = []
        message_count = 0
        
        print(f"Consuming from topic: {topic}")
        
        for message in consumer:
            try:
                shipment_data = message.value
                messages.append(shipment_data)
                message_count += 1
                
                # Process in batches to avoid memory issues
                if message_count >= 1000:
                    break
                    
            except Exception as e:
                print(f"Error processing message: {e}")
                continue
        
        consumer.close()
        
        print(f"Consumed {len(messages)} messages from Kafka")
        
        # Store data for next task
        context['task_instance'].xcom_push(key='kafka_messages', value=messages)
        
        return len(messages)
        
    except Exception as e:
        print(f"Error consuming from Kafka: {e}")
        # Return empty list if Kafka is not available
        context['task_instance'].xcom_push(key='kafka_messages', value=[])
        return 0

def store_shipment_data(**context):
    """Store consumed shipment data in PostgreSQL"""
    print("Storing shipment data in database...")
    
    # Get data from previous task
    messages = context['task_instance'].xcom_pull(
        task_ids='consume_kafka_data', 
        key='kafka_messages'
    )
    
    if not messages:
        print("No messages to process")
        return 0
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        stored_count = 0
        
        for message in messages:
            try:
                # Insert or update shipment
                cursor.execute("""
                    INSERT INTO shipments (
                        shipment_id, origin, destination, current_location, 
                        status, eta, distance_remaining_km, vehicle_speed_kmph, 
                        weather, traffic_level, updated_at
                    ) VALUES (
                        %(shipment_id)s, %(origin)s, %(destination)s, %(current_location)s,
                        %(status)s, %(eta)s, %(distance_remaining_km)s, %(vehicle_speed_kmph)s,
                        %(weather)s, %(traffic_level)s, %(timestamp)s
                    )
                    ON CONFLICT (shipment_id) DO UPDATE SET
                        current_location = EXCLUDED.current_location,
                        status = EXCLUDED.status,
                        eta = EXCLUDED.eta,
                        distance_remaining_km = EXCLUDED.distance_remaining_km,
                        vehicle_speed_kmph = EXCLUDED.vehicle_speed_kmph,
                        weather = EXCLUDED.weather,
                        traffic_level = EXCLUDED.traffic_level,
                        updated_at = EXCLUDED.updated_at
                """, message)
                
                # Insert history record
                cursor.execute("""
                    INSERT INTO shipment_history (
                        shipment_id, timestamp, status, current_location,
                        distance_remaining_km, vehicle_speed_kmph, weather,
                        traffic_level, raw_data
                    ) VALUES (
                        %(shipment_id)s, %(timestamp)s, %(status)s, %(current_location)s,
                        %(distance_remaining_km)s, %(vehicle_speed_kmph)s, %(weather)s,
                        %(traffic_level)s, %(raw_data)s
                    )
                """, {
                    **message,
                    'raw_data': json.dumps(message)
                })
                
                stored_count += 1
                
            except Exception as e:
                print(f"Error storing message {message.get('shipment_id', 'unknown')}: {e}")
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Stored {stored_count} shipment records")
        return stored_count
        
    except Exception as e:
        print(f"Database error: {e}")
        raise

def predict_delays(**context):
    """Run ML model to predict shipment delays"""
    print("Running delay prediction model...")
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    
    try:
        # Load predictor
        predictor = DelayPredictor()
        
        # Get active shipments from database
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT shipment_id, origin, destination, current_location,
                   distance_remaining_km, vehicle_speed_kmph, weather,
                   traffic_level, updated_at as timestamp
            FROM shipments
            WHERE status IN ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed')
            AND distance_remaining_km > 0
        """)
        
        active_shipments = cursor.fetchall()
        print(f"Found {len(active_shipments)} active shipments")
        
        if not active_shipments:
            cursor.close()
            conn.close()
            return 0
        
        # Convert to list of dictionaries
        shipment_list = [dict(shipment) for shipment in active_shipments]
        
        # Make predictions
        predictions = predictor.predict_batch(shipment_list)
        
        # Store predictions in database
        prediction_count = 0
        
        for prediction in predictions:
            try:
                cursor.execute("""
                    INSERT INTO delay_predictions (
                        shipment_id, delay_probability, predicted_delay_minutes,
                        model_version, features
                    ) VALUES (
                        %(shipment_id)s, %(delay_probability)s, %(estimated_delay_minutes)s,
                        %(model_version)s, %(features)s
                    )
                """, {
                    'shipment_id': prediction['shipment_id'],
                    'delay_probability': prediction['delay_probability'],
                    'estimated_delay_minutes': prediction['estimated_delay_minutes'],
                    'model_version': prediction['model_version'],
                    'features': json.dumps(prediction.get('features', {}))
                })
                
                prediction_count += 1
                
            except Exception as e:
                print(f"Error storing prediction for {prediction.get('shipment_id')}: {e}")
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Stored {prediction_count} predictions")
        
        # Store predictions for alerting task
        context['task_instance'].xcom_push(key='predictions', value=predictions)
        
        return prediction_count
        
    except Exception as e:
        print(f"Error in prediction task: {e}")
        raise

def trigger_alerts(**context):
    """Trigger alerts for high-risk shipments"""
    print("Processing alerts for high-risk shipments...")
    
    # Get predictions from previous task
    predictions = context['task_instance'].xcom_pull(
        task_ids='predict_delays',
        key='predictions'
    )
    
    if not predictions:
        print("No predictions to process")
        return 0
    
    try:
        alert_manager = AlertManager()
        threshold = float(os.getenv('PREDICTION_THRESHOLD', 0.7))
        
        alert_count = 0
        
        for prediction in predictions:
            delay_probability = prediction.get('delay_probability', 0)
            
            if delay_probability >= threshold:
                # Create alert
                alert_data = {
                    'shipment_id': prediction['shipment_id'],
                    'alert_type': 'delay_prediction',
                    'severity': 'High' if delay_probability >= 0.8 else 'Medium',
                    'title': f"High Delay Risk - {prediction['shipment_id']}",
                    'message': f"Shipment has {delay_probability:.1%} probability of delay. "
                              f"Estimated delay: {prediction['estimated_delay_minutes']} minutes.",
                    'metadata': prediction
                }
                
                if alert_manager.create_alert(alert_data):
                    alert_count += 1
        
        print(f"Triggered {alert_count} alerts")
        return alert_count
        
    except Exception as e:
        print(f"Error in alerting task: {e}")
        raise

def cleanup_old_data(**context):
    """Clean up old data to prevent database bloat"""
    print("Cleaning up old data...")
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Delete old history records (keep last 30 days)
        cursor.execute("""
            DELETE FROM shipment_history 
            WHERE created_at < NOW() - INTERVAL '30 days'
        """)
        
        # Delete old predictions (keep last 7 days)
        cursor.execute("""
            DELETE FROM delay_predictions 
            WHERE created_at < NOW() - INTERVAL '7 days'
        """)
        
        # Archive resolved alerts (keep last 30 days)
        cursor.execute("""
            DELETE FROM alerts 
            WHERE resolved_at IS NOT NULL 
            AND resolved_at < NOW() - INTERVAL '30 days'
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Data cleanup completed")
        return True
        
    except Exception as e:
        print(f"Error in cleanup task: {e}")
        return False

# Define tasks
consume_kafka_task = PythonOperator(
    task_id='consume_kafka_data',
    python_callable=consume_kafka_data,
    dag=dag,
)

store_data_task = PythonOperator(
    task_id='store_shipment_data',
    python_callable=store_shipment_data,
    dag=dag,
)

predict_task = PythonOperator(
    task_id='predict_delays',
    python_callable=predict_delays,
    dag=dag,
)

alert_task = PythonOperator(
    task_id='trigger_alerts',
    python_callable=trigger_alerts,
    dag=dag,
)

cleanup_task = PythonOperator(
    task_id='cleanup_old_data',
    python_callable=cleanup_old_data,
    dag=dag,
)

# Health check task
health_check_task = BashOperator(
    task_id='health_check',
    bash_command='echo "Pipeline completed successfully at $(date)"',
    dag=dag,
)

# Define task dependencies
consume_kafka_task >> store_data_task >> predict_task >> alert_task >> cleanup_task >> health_check_task

# Add task documentation
consume_kafka_task.doc_md = """
## Consume Kafka Data

This task consumes real-time shipment updates from the Kafka topic 'shipment_updates'.
It processes messages in batches and passes them to the next task for storage.
"""

store_data_task.doc_md = """
## Store Shipment Data

This task stores the consumed shipment data in PostgreSQL, maintaining both current
shipment status and historical records for trend analysis.
"""

predict_task.doc_md = """
## Predict Delays

This task runs the trained machine learning model to predict delay probabilities
for all active shipments. Predictions are stored in the database for tracking.
"""

alert_task.doc_md = """
## Trigger Alerts

This task evaluates predictions and triggers alerts for shipments with high delay
probability. Alerts can be sent via Slack or other configured channels.
"""

cleanup_task.doc_md = """
## Cleanup Old Data

This task removes old historical data to prevent database bloat while maintaining
recent data for analysis and reporting.
"""