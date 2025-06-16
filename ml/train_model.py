#!/usr/bin/env python3

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
import joblib
import os
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

class DelayPredictor:
    """Machine Learning model for predicting shipment delays"""
    
    def __init__(self):
        self.model = None
        self.feature_encoders = {}
        self.scaler = StandardScaler()
        self.feature_columns = [
            'distance_remaining_km',
            'vehicle_speed_kmph',
            'weather_encoded',
            'traffic_level_encoded',
            'hour_of_day',
            'day_of_week',
            'is_weekend',
            'origin_risk_score',
            'destination_risk_score',
            'route_complexity'
        ]
        
    def load_training_data(self):
        """Load and prepare training data from database"""
        database_url = os.getenv('DATABASE_URL')
        
        try:
            conn = psycopg2.connect(database_url)
            
            # Query historical shipment data with actual outcomes
            query = """
            SELECT 
                s.shipment_id,
                s.origin,
                s.destination,
                sh.distance_remaining_km,
                sh.vehicle_speed_kmph,
                sh.weather,
                sh.traffic_level,
                sh.timestamp,
                s.eta,
                s.updated_at,
                CASE 
                    WHEN s.status = 'Delayed' OR s.updated_at > s.eta THEN 1 
                    ELSE 0 
                END as is_delayed
            FROM shipments s
            JOIN shipment_history sh ON s.shipment_id = sh.shipment_id
            WHERE s.status IN ('Delivered', 'Delayed')
            AND sh.distance_remaining_km > 0
            ORDER BY sh.timestamp
            """
            
            df = pd.read_sql(query, conn)
            conn.close()
            
            if len(df) < 100:
                print("Insufficient training data, generating synthetic data...")
                df = self._generate_synthetic_training_data()
            
            return df
            
        except Exception as e:
            print(f"Error loading training data: {e}")
            print("Generating synthetic training data...")
            return self._generate_synthetic_training_data()
    
    def _generate_synthetic_training_data(self, n_samples=5000):
        """Generate synthetic training data for initial model training"""
        np.random.seed(42)
        
        cities = [
            "Los Angeles", "New York", "Chicago", "Houston", "Phoenix",
            "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
            "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte"
        ]
        
        weather_conditions = ["Clear", "Rain", "Snow", "Fog", "Storm"]
        traffic_levels = ["Light", "Moderate", "Heavy", "Very Heavy"]
        
        data = []
        
        for i in range(n_samples):
            # Basic features
            distance = np.random.randint(100, 4000)
            base_speed = np.random.uniform(40, 80)
            weather = np.random.choice(weather_conditions)
            traffic = np.random.choice(traffic_levels)
            
            # Adjust speed based on conditions
            if weather in ["Rain", "Snow", "Fog"]:
                base_speed *= np.random.uniform(0.6, 0.9)
            if weather == "Storm":
                base_speed *= np.random.uniform(0.4, 0.7)
            if traffic in ["Heavy", "Very Heavy"]:
                base_speed *= np.random.uniform(0.5, 0.8)
            
            # Time features
            timestamp = datetime.now() - timedelta(days=np.random.randint(1, 365))
            
            # Calculate delay probability based on conditions
            delay_factors = 0
            
            if distance > 2000:
                delay_factors += 0.2
            if base_speed < 50:
                delay_factors += 0.3
            if weather in ["Rain", "Snow", "Storm"]:
                delay_factors += 0.25
            if traffic in ["Heavy", "Very Heavy"]:
                delay_factors += 0.2
            if timestamp.hour in [6, 7, 8, 17, 18, 19]:  # Rush hours
                delay_factors += 0.15
            
            # Add some randomness
            delay_probability = min(delay_factors + np.random.uniform(-0.1, 0.1), 0.9)
            is_delayed = 1 if np.random.random() < delay_probability else 0
            
            data.append({
                'shipment_id': f'SYNTH_{i:06d}',
                'origin': np.random.choice(cities),
                'destination': np.random.choice(cities),
                'distance_remaining_km': distance,
                'vehicle_speed_kmph': round(base_speed, 1),
                'weather': weather,
                'traffic_level': traffic,
                'timestamp': timestamp,
                'eta': timestamp + timedelta(hours=distance/base_speed),
                'updated_at': timestamp + timedelta(hours=distance/base_speed + (2 if is_delayed else 0)),
                'is_delayed': is_delayed
            })
        
        return pd.DataFrame(data)
    
    def engineer_features(self, df):
        """Create engineered features from raw data"""
        df = df.copy()
        
        # Encode categorical variables
        for col in ['weather', 'traffic_level']:
            if col not in self.feature_encoders:
                self.feature_encoders[col] = LabelEncoder()
                df[f'{col}_encoded'] = self.feature_encoders[col].fit_transform(df[col])
            else:
                df[f'{col}_encoded'] = self.feature_encoders[col].transform(df[col])
        
        # Time-based features
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['hour_of_day'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Route complexity (simplified)
        origin_counts = df['origin'].value_counts()
        destination_counts = df['destination'].value_counts()
        
        df['origin_risk_score'] = df['origin'].map(
            lambda x: origin_counts.get(x, 1) / len(df)
        )
        df['destination_risk_score'] = df['destination'].map(
            lambda x: destination_counts.get(x, 1) / len(df)
        )
        
        # Route complexity based on distance and speed
        df['route_complexity'] = (
            df['distance_remaining_km'] / (df['vehicle_speed_kmph'] + 1)
        ) / 100  # Normalize
        
        return df
    
    def train_model(self, df):
        """Train the delay prediction model"""
        print("Engineering features...")
        df_features = self.engineer_features(df)
        
        # Prepare features and target
        X = df_features[self.feature_columns]
        y = df_features['is_delayed']
        
        print(f"Training data shape: {X.shape}")
        print(f"Delay rate: {y.mean():.2%}")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model with hyperparameter tuning
        print("Training Random Forest model...")
        
        param_grid = {
            'n_estimators': [100, 200],
            'max_depth': [10, 15, 20],
            'min_samples_split': [5, 10],
            'min_samples_leaf': [2, 4]
        }
        
        rf = RandomForestClassifier(random_state=42)
        grid_search = GridSearchCV(
            rf, param_grid, cv=5, scoring='roc_auc', n_jobs=-1
        )
        
        grid_search.fit(X_train_scaled, y_train)
        self.model = grid_search.best_estimator_
        
        # Evaluate model
        print("\n=== Model Evaluation ===")
        print(f"Best parameters: {grid_search.best_params_}")
        
        # Cross-validation scores
        cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=5, scoring='roc_auc')
        print(f"Cross-validation AUC: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")
        
        # Test set evaluation
        y_pred = self.model.predict(X_test_scaled)
        y_pred_proba = self.model.predict_proba(X_test_scaled)[:, 1]
        
        print(f"Test AUC: {roc_auc_score(y_test, y_pred_proba):.3f}")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred))
        
        # Feature importance
        feature_importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print("\nFeature Importance:")
        print(feature_importance)
        
        return self.model
    
    def save_model(self, model_path=None):
        """Save the trained model and encoders"""
        if model_path is None:
            model_path = os.getenv('ML_MODEL_PATH', './ml/models/delay_predictor.joblib')
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_encoders': self.feature_encoders,
            'feature_columns': self.feature_columns,
            'trained_at': datetime.now(),
            'version': '1.0'
        }
        
        joblib.dump(model_data, model_path)
        print(f"Model saved to: {model_path}")
        
        return model_path
    
    def load_model(self, model_path=None):
        """Load a trained model"""
        if model_path is None:
            model_path = os.getenv('ML_MODEL_PATH', './ml/models/delay_predictor.joblib')
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        model_data = joblib.load(model_path)
        
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.feature_encoders = model_data['feature_encoders']
        self.feature_columns = model_data['feature_columns']
        
        print(f"Model loaded from: {model_path}")
        print(f"Model version: {model_data.get('version', 'Unknown')}")
        print(f"Trained at: {model_data.get('trained_at', 'Unknown')}")
        
        return self.model

def main():
    """Main training function"""
    print("=== Smart Delay Detection - Model Training ===")
    
    predictor = DelayPredictor()
    
    # Load training data
    print("Loading training data...")
    df = predictor.load_training_data()
    print(f"Loaded {len(df)} training samples")
    
    # Train model
    model = predictor.train_model(df)
    
    # Save model
    model_path = predictor.save_model()
    
    print(f"\n✅ Model training completed successfully!")
    print(f"Model saved to: {model_path}")
    print("You can now use this model in the Airflow DAG for predictions")

if __name__ == "__main__":
    main()