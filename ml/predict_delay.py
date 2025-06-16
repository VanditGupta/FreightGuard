#!/usr/bin/env python3

import pandas as pd
import numpy as np
import joblib
import os
from datetime import datetime
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

class DelayPredictor:
    """Delay prediction model for real-time inference"""
    
    def __init__(self, model_path=None):
        self.model = None
        self.scaler = None
        self.feature_encoders = {}
        self.feature_columns = []
        self.model_path = model_path or os.getenv('ML_MODEL_PATH', './ml/models/delay_predictor.joblib')
        
        # Load model if it exists
        if os.path.exists(self.model_path):
            self.load_model()
    
    def load_model(self):
        """Load the trained model and preprocessors"""
        try:
            model_data = joblib.load(self.model_path)
            
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_encoders = model_data['feature_encoders']
            self.feature_columns = model_data['feature_columns']
            
            print(f"Model loaded successfully from {self.model_path}")
            return True
            
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def prepare_features(self, shipment_data: Dict) -> pd.DataFrame:
        """Prepare features from raw shipment data"""
        # Create DataFrame from single shipment
        df = pd.DataFrame([shipment_data])
        
        # Handle missing or invalid values
        df['distance_remaining_km'] = pd.to_numeric(df['distance_remaining_km'], errors='coerce').fillna(1000)
        df['vehicle_speed_kmph'] = pd.to_numeric(df['vehicle_speed_kmph'], errors='coerce').fillna(60)
        
        # Encode categorical variables
        for col in ['weather', 'traffic_level']:
            if col in df.columns and col in self.feature_encoders:
                # Handle unknown categories
                encoder = self.feature_encoders[col]
                df[f'{col}_encoded'] = df[col].apply(
                    lambda x: encoder.transform([x])[0] if x in encoder.classes_ else 0
                )
            else:
                # Default encoding if category not seen during training
                df[f'{col}_encoded'] = 0
        
        # Time-based features
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        else:
            df['timestamp'] = pd.to_datetime(datetime.now())
        
        df['hour_of_day'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Route complexity features (simplified for real-time prediction)
        # In production, these could be looked up from historical data
        df['origin_risk_score'] = 0.1  # Default low risk
        df['destination_risk_score'] = 0.1  # Default low risk
        
        # Route complexity based on distance and speed
        df['route_complexity'] = (
            df['distance_remaining_km'] / (df['vehicle_speed_kmph'] + 1)
        ) / 100
        
        # Ensure all required features are present
        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0  # Default value for missing features
        
        return df[self.feature_columns]
    
    def predict_delay(self, shipment_data: Dict) -> Tuple[float, Dict]:
        """Predict delay probability for a single shipment"""
        if self.model is None:
            raise ValueError("Model not loaded. Please load a trained model first.")
        
        try:
            # Prepare features
            features = self.prepare_features(shipment_data)
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Make prediction
            delay_probability = self.model.predict_proba(features_scaled)[0, 1]
            
            # Get feature importance for this prediction
            feature_importance = dict(zip(
                self.feature_columns,
                features.iloc[0].values
            ))
            
            # Calculate estimated delay in minutes (simplified)
            estimated_delay_minutes = 0
            if delay_probability > 0.5:
                # Base delay estimation on probability and distance
                base_delay = delay_probability * 120  # Up to 2 hours
                distance_factor = min(shipment_data.get('distance_remaining_km', 1000) / 1000, 2)
                estimated_delay_minutes = int(base_delay * distance_factor)
            
            # Risk categorization
            if delay_probability >= 0.7:
                risk_level = "High"
            elif delay_probability >= 0.4:
                risk_level = "Medium"
            else:
                risk_level = "Low"
            
            prediction_result = {
                'shipment_id': shipment_data.get('shipment_id'),
                'delay_probability': float(delay_probability),
                'risk_level': risk_level,
                'estimated_delay_minutes': estimated_delay_minutes,
                'prediction_timestamp': datetime.now().isoformat(),
                'features': feature_importance,
                'model_version': '1.0'
            }
            
            return delay_probability, prediction_result
            
        except Exception as e:
            print(f"Error making prediction: {e}")
            # Return default safe prediction
            return 0.5, {
                'shipment_id': shipment_data.get('shipment_id'),
                'delay_probability': 0.5,
                'risk_level': "Medium",
                'estimated_delay_minutes': 60,
                'prediction_timestamp': datetime.now().isoformat(),
                'error': str(e),
                'model_version': '1.0'
            }
    
    def predict_batch(self, shipment_list: List[Dict]) -> List[Dict]:
        """Predict delays for multiple shipments"""
        results = []
        
        for shipment in shipment_list:
            try:
                probability, result = self.predict_delay(shipment)
                results.append(result)
            except Exception as e:
                # Add error result for failed predictions
                results.append({
                    'shipment_id': shipment.get('shipment_id', 'unknown'),
                    'delay_probability': 0.5,
                    'risk_level': "Medium",
                    'estimated_delay_minutes': 60,
                    'prediction_timestamp': datetime.now().isoformat(),
                    'error': str(e),
                    'model_version': '1.0'
                })
        
        return results
    
    def should_trigger_alert(self, prediction_result: Dict, threshold: float = 0.7) -> bool:
        """Determine if an alert should be triggered based on prediction"""
        delay_probability = prediction_result.get('delay_probability', 0)
        return delay_probability >= threshold

def test_prediction():
    """Test function for prediction model"""
    predictor = DelayPredictor()
    
    # Test data
    test_shipment = {
        'shipment_id': 'TEST_PRED_001',
        'origin': 'Los Angeles',
        'destination': 'New York',
        'distance_remaining_km': 2800,
        'vehicle_speed_kmph': 45.5,
        'weather': 'Rain',
        'traffic_level': 'Heavy',
        'timestamp': datetime.now().isoformat()
    }
    
    print("Testing delay prediction...")
    print(f"Test shipment: {test_shipment['shipment_id']}")
    
    try:
        probability, result = predictor.predict_delay(test_shipment)
        
        print(f"\nPrediction Results:")
        print(f"Delay Probability: {probability:.3f}")
        print(f"Risk Level: {result['risk_level']}")
        print(f"Estimated Delay: {result['estimated_delay_minutes']} minutes")
        print(f"Should Alert: {predictor.should_trigger_alert(result)}")
        
        return result
        
    except Exception as e:
        print(f"Test failed: {e}")
        return None

if __name__ == "__main__":
    test_prediction()