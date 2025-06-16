#!/usr/bin/env python3

import unittest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.predict_delay import DelayPredictor
from ml.train_model import DelayPredictor as TrainingPredictor

class TestDelayPredictor(unittest.TestCase):
    
    def setUp(self):
        self.predictor = DelayPredictor()
        
        # Mock model data
        self.predictor.model = Mock()
        self.predictor.scaler = Mock()
        self.predictor.feature_encoders = {
            'weather': Mock(),
            'traffic_level': Mock()
        }
        self.predictor.feature_columns = [
            'distance_remaining_km', 'vehicle_speed_kmph', 'weather_encoded',
            'traffic_level_encoded', 'hour_of_day', 'day_of_week',
            'is_weekend', 'origin_risk_score', 'destination_risk_score',
            'route_complexity'
        ]
        
        # Configure mocks
        self.predictor.feature_encoders['weather'].classes_ = ['Clear', 'Rain', 'Snow']
        self.predictor.feature_encoders['weather'].transform.return_value = [0]
        self.predictor.feature_encoders['traffic_level'].classes_ = ['Light', 'Moderate', 'Heavy']
        self.predictor.feature_encoders['traffic_level'].transform.return_value = [1]
        
        self.predictor.scaler.transform.return_value = np.array([[1, 2, 0, 1, 14, 1, 0, 0.1, 0.1, 0.5]])
        self.predictor.model.predict_proba.return_value = np.array([[0.3, 0.7]])
    
    def test_prepare_features(self):
        """Test feature preparation"""
        test_data = {
            'shipment_id': 'TEST001',
            'distance_remaining_km': 1000,
            'vehicle_speed_kmph': 60.0,
            'weather': 'Rain',
            'traffic_level': 'Heavy',
            'timestamp': '2024-01-15T14:30:00Z'
        }
        
        features = self.predictor.prepare_features(test_data)
        
        # Check that all required features are present
        self.assertEqual(len(features.columns), len(self.predictor.feature_columns))
        for col in self.predictor.feature_columns:
            self.assertIn(col, features.columns)
    
    def test_predict_delay(self):
        """Test delay prediction"""
        test_data = {
            'shipment_id': 'TEST001',
            'distance_remaining_km': 1000,
            'vehicle_speed_kmph': 60.0,
            'weather': 'Rain',
            'traffic_level': 'Heavy',
            'timestamp': '2024-01-15T14:30:00Z'
        }
        
        probability, result = self.predictor.predict_delay(test_data)
        
        # Check return values
        self.assertEqual(probability, 0.7)
        self.assertEqual(result['shipment_id'], 'TEST001')
        self.assertEqual(result['delay_probability'], 0.7)
        self.assertEqual(result['risk_level'], 'High')
        self.assertIn('prediction_timestamp', result)
    
    def test_should_trigger_alert(self):
        """Test alert triggering logic"""
        high_risk_result = {'delay_probability': 0.8}
        low_risk_result = {'delay_probability': 0.3}
        
        self.assertTrue(self.predictor.should_trigger_alert(high_risk_result, 0.7))
        self.assertFalse(self.predictor.should_trigger_alert(low_risk_result, 0.7))
    
    def test_predict_batch(self):
        """Test batch prediction"""
        test_data = [
            {
                'shipment_id': 'TEST001',
                'distance_remaining_km': 1000,
                'vehicle_speed_kmph': 60.0,
                'weather': 'Rain',
                'traffic_level': 'Heavy'
            },
            {
                'shipment_id': 'TEST002',
                'distance_remaining_km': 500,
                'vehicle_speed_kmph': 70.0,
                'weather': 'Clear',
                'traffic_level': 'Light'
            }
        ]
        
        results = self.predictor.predict_batch(test_data)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['shipment_id'], 'TEST001')
        self.assertEqual(results[1]['shipment_id'], 'TEST002')

class TestTrainingPredictor(unittest.TestCase):
    
    def setUp(self):
        self.trainer = TrainingPredictor()
    
    def test_synthetic_data_generation(self):
        """Test synthetic training data generation"""
        df = self.trainer._generate_synthetic_training_data(100)
        
        # Check data shape and columns
        self.assertEqual(len(df), 100)
        required_columns = [
            'shipment_id', 'origin', 'destination', 'distance_remaining_km',
            'vehicle_speed_kmph', 'weather', 'traffic_level', 'is_delayed'
        ]
        
        for col in required_columns:
            self.assertIn(col, df.columns)
        
        # Check data validity
        self.assertTrue(df['distance_remaining_km'].min() >= 0)
        self.assertTrue(df['vehicle_speed_kmph'].min() > 0)
        self.assertIn(df['is_delayed'].dtype, [np.int64, int])
        self.assertTrue(df['is_delayed'].isin([0, 1]).all())
    
    def test_feature_engineering(self):
        """Test feature engineering"""
        # Create sample data
        df = self.trainer._generate_synthetic_training_data(10)
        
        # Engineer features
        df_features = self.trainer.engineer_features(df)
        
        # Check new features
        expected_features = [
            'weather_encoded', 'traffic_level_encoded', 'hour_of_day',
            'day_of_week', 'is_weekend', 'origin_risk_score',
            'destination_risk_score', 'route_complexity'
        ]
        
        for feature in expected_features:
            self.assertIn(feature, df_features.columns)

if __name__ == '__main__':
    unittest.main()