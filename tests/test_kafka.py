#!/usr/bin/env python3

import unittest
import json
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kafka.producer import ShipmentDataGenerator, ShipmentProducer

class TestShipmentDataGenerator(unittest.TestCase):
    
    def setUp(self):
        self.generator = ShipmentDataGenerator()
    
    def test_generate_shipment(self):
        """Test shipment data generation"""
        shipment = self.generator.generate_shipment("TEST001")
        
        # Check required fields
        required_fields = [
            'shipment_id', 'origin', 'destination', 'timestamp',
            'status', 'eta', 'current_location', 'vehicle_speed_kmph',
            'distance_remaining_km', 'weather', 'traffic_level'
        ]
        
        for field in required_fields:
            self.assertIn(field, shipment)
        
        # Check data types
        self.assertEqual(shipment['shipment_id'], "TEST001")
        self.assertIsInstance(shipment['vehicle_speed_kmph'], float)
        self.assertIsInstance(shipment['distance_remaining_km'], int)
        self.assertIn(shipment['weather'], self.generator.weather_conditions)
        self.assertIn(shipment['traffic_level'], self.generator.traffic_levels)
    
    def test_shipment_data_validity(self):
        """Test that generated data is valid"""
        shipment = self.generator.generate_shipment()
        
        # Speed should be reasonable
        self.assertGreater(shipment['vehicle_speed_kmph'], 0)
        self.assertLess(shipment['vehicle_speed_kmph'], 150)
        
        # Distance should be positive
        self.assertGreaterEqual(shipment['distance_remaining_km'], 0)
        
        # Origin and destination should be different
        self.assertNotEqual(shipment['origin'], shipment['destination'])

class TestShipmentProducer(unittest.TestCase):
    
    @patch('kafka.producer.KafkaProducer')
    def setUp(self, mock_kafka_producer):
        self.mock_producer = Mock()
        mock_kafka_producer.return_value = self.mock_producer
        self.producer = ShipmentProducer()
    
    def test_send_shipment_update(self):
        """Test sending shipment update"""
        test_shipment = {
            'shipment_id': 'TEST001',
            'origin': 'Los Angeles',
            'destination': 'New York',
            'status': 'In Transit'
        }
        
        # Mock successful send
        future_mock = Mock()
        future_mock.get.return_value = Mock(topic='shipment_updates', partition=0)
        self.mock_producer.send.return_value = future_mock
        
        # Test send
        self.producer.send_shipment_update(test_shipment)
        
        # Verify producer was called
        self.mock_producer.send.assert_called_once_with(
            'shipment_updates',
            key='TEST001',
            value=test_shipment
        )

if __name__ == '__main__':
    unittest.main()