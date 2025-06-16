-- Smart Delay Detection and Escalation System Database Schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types for better data integrity
CREATE TYPE shipment_status AS ENUM ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed', 'Delivered');
CREATE TYPE weather_condition AS ENUM ('Clear', 'Rain', 'Snow', 'Fog', 'Storm');
CREATE TYPE traffic_level AS ENUM ('Light', 'Moderate', 'Heavy', 'Very Heavy');
CREATE TYPE alert_severity AS ENUM ('Low', 'Medium', 'High', 'Critical');

-- Shipments table - stores all shipment records
CREATE TABLE IF NOT EXISTS shipments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_id VARCHAR(50) NOT NULL UNIQUE,
    origin VARCHAR(100) NOT NULL,
    destination VARCHAR(100) NOT NULL,
    current_location VARCHAR(100),
    status shipment_status NOT NULL DEFAULT 'In Transit',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    eta TIMESTAMP WITH TIME ZONE,
    distance_remaining_km INTEGER,
    vehicle_speed_kmph DECIMAL(5,2),
    weather weather_condition,
    traffic_level traffic_level,
    INDEX(shipment_id),
    INDEX(status),
    INDEX(created_at),
    INDEX(eta)
);

-- Shipment history - tracks all updates for each shipment
CREATE TABLE IF NOT EXISTS shipment_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    status shipment_status NOT NULL,
    current_location VARCHAR(100),
    distance_remaining_km INTEGER,
    vehicle_speed_kmph DECIMAL(5,2),
    weather weather_condition,
    traffic_level traffic_level,
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    INDEX(shipment_id),
    INDEX(timestamp),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE
);

-- Delay predictions - stores ML model predictions
CREATE TABLE IF NOT EXISTS delay_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_id VARCHAR(50) NOT NULL,
    prediction_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    delay_probability DECIMAL(5,4) NOT NULL,
    predicted_delay_minutes INTEGER,
    model_version VARCHAR(50),
    features JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    INDEX(shipment_id),
    INDEX(prediction_timestamp),
    INDEX(delay_probability),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE
);

-- Alerts - stores escalation alerts for high-risk shipments
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_id VARCHAR(50) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity alert_severity NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    metadata JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    INDEX(shipment_id),
    INDEX(severity),
    INDEX(triggered_at),
    INDEX(is_active),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE
);

-- Model performance metrics - tracks ML model accuracy over time
CREATE TABLE IF NOT EXISTS model_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(10,6) NOT NULL,
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB,
    INDEX(model_version),
    INDEX(metric_name),
    INDEX(calculated_at)
);

-- System logs - for debugging and monitoring
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component VARCHAR(50) NOT NULL,
    log_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    logged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    INDEX(component),
    INDEX(log_level),
    INDEX(logged_at)
);

-- Create functions for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_shipments_updated_at 
    BEFORE UPDATE ON shipments 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create indexes for performance optimization
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_shipment_history_timestamp 
    ON shipment_history(timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_delay_predictions_probability 
    ON delay_predictions(delay_probability DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_active_severity 
    ON alerts(is_active, severity) WHERE is_active = TRUE;

-- Create views for common queries
CREATE OR REPLACE VIEW active_shipments AS
SELECT 
    s.*,
    dp.delay_probability,
    dp.predicted_delay_minutes,
    CASE 
        WHEN dp.delay_probability >= 0.7 THEN 'High Risk'
        WHEN dp.delay_probability >= 0.4 THEN 'Medium Risk'
        ELSE 'Low Risk'
    END as risk_level
FROM shipments s
LEFT JOIN LATERAL (
    SELECT delay_probability, predicted_delay_minutes
    FROM delay_predictions dp2
    WHERE dp2.shipment_id = s.shipment_id
    ORDER BY dp2.prediction_timestamp DESC
    LIMIT 1
) dp ON true
WHERE s.status IN ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed');

CREATE OR REPLACE VIEW shipment_summary AS
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_shipments,
    COUNT(CASE WHEN status = 'Delivered' THEN 1 END) as delivered,
    COUNT(CASE WHEN status = 'Delayed' THEN 1 END) as delayed,
    ROUND(AVG(CASE WHEN status = 'Delivered' THEN 
        EXTRACT(EPOCH FROM (updated_at - created_at))/3600 
    END), 2) as avg_delivery_time_hours
FROM shipments
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Insert sample data for testing
INSERT INTO shipments (shipment_id, origin, destination, status, eta, distance_remaining_km, vehicle_speed_kmph, weather, traffic_level)
VALUES 
    ('SHIP_TEST_001', 'Los Angeles', 'New York', 'In Transit', NOW() + INTERVAL '2 days', 3000, 65.5, 'Clear', 'Moderate'),
    ('SHIP_TEST_002', 'Chicago', 'Miami', 'At Hub', NOW() + INTERVAL '1 day', 1200, 0, 'Rain', 'Light'),
    ('SHIP_TEST_003', 'Seattle', 'Denver', 'Delayed', NOW() + INTERVAL '6 hours', 800, 45.2, 'Snow', 'Heavy')
ON CONFLICT (shipment_id) DO NOTHING;

-- Grant permissions (adjust as needed for your environment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;