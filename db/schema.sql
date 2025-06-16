-- Create shipments table
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id VARCHAR(50) PRIMARY KEY,
    origin VARCHAR(100) NOT NULL,
    destination VARCHAR(100) NOT NULL,
    current_location VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    distance_remaining_km DECIMAL(10,2),
    vehicle_speed_kmph DECIMAL(10,2),
    weather VARCHAR(50),
    traffic_level VARCHAR(50),
    eta TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create delay_predictions table
CREATE TABLE IF NOT EXISTS delay_predictions (
    id SERIAL PRIMARY KEY,
    shipment_id VARCHAR(50) REFERENCES shipments(shipment_id),
    delay_probability DECIMAL(5,4),
    predicted_delay_minutes INTEGER,
    prediction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_version VARCHAR(50),
    features JSONB
);

-- Create alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    shipment_id VARCHAR(50) REFERENCES shipments(shipment_id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
CREATE INDEX IF NOT EXISTS idx_shipments_updated_at ON shipments(updated_at);
CREATE INDEX IF NOT EXISTS idx_delay_predictions_shipment_timestamp ON delay_predictions(shipment_id, prediction_timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX IF NOT EXISTS idx_alerts_is_active ON alerts(is_active);

-- Insert some sample data
INSERT INTO shipments (shipment_id, origin, destination, current_location, status, distance_remaining_km, vehicle_speed_kmph, weather, traffic_level, eta)
VALUES 
    ('SH001', 'New York', 'Los Angeles', 'Chicago', 'In Transit', 2500.00, 65.00, 'Clear', 'Medium', NOW() + INTERVAL '2 days'),
    ('SH002', 'Chicago', 'Miami', 'Atlanta', 'At Hub', 1200.00, 0.00, 'Rainy', 'High', NOW() + INTERVAL '1 day'),
    ('SH003', 'Seattle', 'San Francisco', 'Portland', 'Out for Delivery', 300.00, 45.00, 'Foggy', 'Low', NOW() + INTERVAL '6 hours'),
    ('SH004', 'Boston', 'Washington DC', 'Philadelphia', 'Delayed', 400.00, 30.00, 'Stormy', 'High', NOW() + INTERVAL '12 hours'),
    ('SH005', 'Denver', 'Phoenix', 'Albuquerque', 'In Transit', 800.00, 70.00, 'Clear', 'Medium', NOW() + INTERVAL '1 day');

-- Insert sample delay predictions
INSERT INTO delay_predictions (shipment_id, delay_probability, predicted_delay_minutes, model_version)
VALUES 
    ('SH001', 0.85, 120, 'v1.0'),
    ('SH002', 0.45, 45, 'v1.0'),
    ('SH003', 0.15, 10, 'v1.0'),
    ('SH004', 0.95, 180, 'v1.0'),
    ('SH005', 0.30, 30, 'v1.0');

-- Insert sample alerts
INSERT INTO alerts (shipment_id, alert_type, severity, title, message, triggered_at)
VALUES 
    ('SH001', 'Weather', 'High', 'Severe Weather Alert', 'Heavy snow expected in route', NOW() - INTERVAL '2 hours'),
    ('SH002', 'Traffic', 'Medium', 'Traffic Congestion', 'Major traffic jam reported', NOW() - INTERVAL '1 hour'),
    ('SH004', 'Delay', 'Critical', 'Extended Delay', 'Vehicle breakdown causing significant delay', NOW() - INTERVAL '30 minutes'); 