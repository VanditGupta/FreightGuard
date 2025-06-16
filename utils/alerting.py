#!/usr/bin/env python3

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

class AlertManager:
    """Manages alert creation, notification, and tracking"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.slack_token = os.getenv('SLACK_BOT_TOKEN')
        self.slack_channel = os.getenv('SLACK_CHANNEL', '#alerts')
        
        # Initialize Slack client if token is available
        self.slack_client = None
        if self.slack_token:
            try:
                self.slack_client = WebClient(token=self.slack_token)
                # Test connection
                response = self.slack_client.auth_test()
                print(f"Connected to Slack as: {response['user']}")
            except Exception as e:
                print(f"Failed to initialize Slack client: {e}")
                self.slack_client = None
    
    def create_alert(self, alert_data: Dict) -> bool:
        """Create a new alert in the database"""
        if not self.database_url:
            print("DATABASE_URL not configured")
            return False
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            # Check if similar alert already exists and is active
            cursor.execute("""
                SELECT id FROM alerts 
                WHERE shipment_id = %s 
                AND alert_type = %s 
                AND is_active = TRUE
                AND triggered_at > NOW() - INTERVAL '1 hour'
            """, (alert_data['shipment_id'], alert_data['alert_type']))
            
            if cursor.fetchone():
                print(f"Similar alert already exists for {alert_data['shipment_id']}")
                cursor.close()
                conn.close()
                return False
            
            # Insert new alert
            cursor.execute("""
                INSERT INTO alerts (
                    shipment_id, alert_type, severity, title, message, metadata
                ) VALUES (
                    %(shipment_id)s, %(alert_type)s, %(severity)s, 
                    %(title)s, %(message)s, %(metadata)s
                )
                RETURNING id
            """, {
                **alert_data,
                'metadata': json.dumps(alert_data.get('metadata', {}))
            })
            
            alert_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Created alert {alert_id} for shipment {alert_data['shipment_id']}")
            
            # Send notification
            self._send_notification(alert_data)
            
            return True
            
        except Exception as e:
            print(f"Error creating alert: {e}")
            return False
    
    def _send_notification(self, alert_data: Dict):
        """Send alert notification via configured channels"""
        # Console notification (always available)
        self._send_console_notification(alert_data)
        
        # Slack notification (if configured)
        if self.slack_client:
            self._send_slack_notification(alert_data)
    
    def _send_console_notification(self, alert_data: Dict):
        """Send alert to console/logs"""
        severity = alert_data.get('severity', 'Medium')
        shipment_id = alert_data.get('shipment_id', 'Unknown')
        title = alert_data.get('title', 'Alert')
        message = alert_data.get('message', '')
        
        print("\n" + "="*60)
        print(f"🚨 ALERT - {severity.upper()} SEVERITY")
        print(f"Shipment: {shipment_id}")
        print(f"Title: {title}")
        print(f"Message: {message}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")
    
    def _send_slack_notification(self, alert_data: Dict):
        """Send alert to Slack channel"""
        try:
            severity = alert_data.get('severity', 'Medium')
            shipment_id = alert_data.get('shipment_id', 'Unknown')
            title = alert_data.get('title', 'Alert')
            message = alert_data.get('message', '')
            
            # Choose emoji and color based on severity
            emoji_map = {
                'Low': '🟡',
                'Medium': '🟠', 
                'High': '🔴',
                'Critical': '🚨'
            }
            
            color_map = {
                'Low': '#ffcc00',
                'Medium': '#ff9900',
                'High': '#ff3300',
                'Critical': '#cc0000'
            }
            
            emoji = emoji_map.get(severity, '⚠️')
            color = color_map.get(severity, '#ff9900')
            
            # Create Slack message blocks
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {title}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Shipment ID:*\n{shipment_id}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Severity:*\n{severity}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{message}"
                    }
                }
            ]
            
            # Add prediction details if available
            metadata = alert_data.get('metadata', {})
            if 'delay_probability' in metadata:
                blocks.append({
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Delay Probability:*\n{metadata['delay_probability']:.1%}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Est. Delay:*\n{metadata.get('estimated_delay_minutes', 0)} mins"
                        }
                    ]
                })
            
            # Send message
            response = self.slack_client.chat_postMessage(
                channel=self.slack_channel,
                text=f"{emoji} {title}",  # Fallback text
                blocks=blocks,
                attachments=[{
                    "color": color,
                    "fields": [{
                        "title": "Timestamp",
                        "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "short": True
                    }]
                }]
            )
            
            print(f"Sent Slack notification: {response['ts']}")
            
        except SlackApiError as e:
            print(f"Slack API error: {e.response['error']}")
        except Exception as e:
            print(f"Error sending Slack notification: {e}")
    
    def get_active_alerts(self, limit: int = 50) -> List[Dict]:
        """Get active alerts from database"""
        if not self.database_url:
            return []
        
        try:
            conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    a.*,
                    s.origin,
                    s.destination,
                    s.current_location,
                    s.status as shipment_status
                FROM alerts a
                JOIN shipments s ON a.shipment_id = s.shipment_id
                WHERE a.is_active = TRUE
                ORDER BY a.triggered_at DESC
                LIMIT %s
            """, (limit,))
            
            alerts = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [dict(alert) for alert in alerts]
            
        except Exception as e:
            print(f"Error fetching active alerts: {e}")
            return []
    
    def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Mark alert as resolved"""
        if not self.database_url:
            return False
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE alerts 
                SET is_active = FALSE, 
                    resolved_at = NOW(),
                    resolved_by = %s
                WHERE id = %s
                AND is_active = TRUE
            """, (resolved_by, alert_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                print(f"Resolved alert {alert_id}")
                result = True
            else:
                print(f"Alert {alert_id} not found or already resolved")
                result = False
            
            cursor.close()
            conn.close()
            
            return result
            
        except Exception as e:
            print(f"Error resolving alert: {e}")
            return False
    
    def get_alert_summary(self, hours: int = 24) -> Dict:
        """Get summary of alerts in the last N hours"""
        if not self.database_url:
            return {}
        
        try:
            conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    severity,
                    COUNT(*) as count,
                    COUNT(CASE WHEN is_active THEN 1 END) as active_count
                FROM alerts
                WHERE triggered_at > NOW() - INTERVAL '%s hours'
                GROUP BY severity
                ORDER BY 
                    CASE severity 
                        WHEN 'Critical' THEN 4
                        WHEN 'High' THEN 3
                        WHEN 'Medium' THEN 2
                        WHEN 'Low' THEN 1
                        ELSE 0
                    END DESC
            """, (hours,))
            
            severity_summary = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(*) as total_alerts,
                       COUNT(CASE WHEN is_active THEN 1 END) as active_alerts,
                       COUNT(CASE WHEN resolved_at IS NOT NULL THEN 1 END) as resolved_alerts
                FROM alerts
                WHERE triggered_at > NOW() - INTERVAL '%s hours'
            """, (hours,))
            
            total_summary = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return {
                'summary': dict(total_summary),
                'by_severity': [dict(row) for row in severity_summary],
                'period_hours': hours
            }
            
        except Exception as e:
            print(f"Error getting alert summary: {e}")
            return {}

def test_alerting():
    """Test alert system functionality"""
    print("Testing alert system...")
    
    alert_manager = AlertManager()
    
    # Create test alert
    test_alert = {
        'shipment_id': 'TEST_ALERT_001',
        'alert_type': 'delay_prediction',
        'severity': 'High',
        'title': 'Test Alert - High Delay Risk',
        'message': 'This is a test alert for the delay detection system.',
        'metadata': {
            'delay_probability': 0.85,
            'estimated_delay_minutes': 120,
            'test': True
        }
    }
    
    success = alert_manager.create_alert(test_alert)
    print(f"Alert creation: {'SUCCESS' if success else 'FAILED'}")
    
    # Get active alerts
    active_alerts = alert_manager.get_active_alerts(10)
    print(f"Active alerts: {len(active_alerts)}")
    
    # Get summary
    summary = alert_manager.get_alert_summary(24)
    print(f"Alert summary: {summary}")

if __name__ == "__main__":
    test_alerting()