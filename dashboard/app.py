#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import numpy as np

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Smart Delay Detection System",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main {
        padding-top: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .risk-high {
        background: linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%);
    }
    .risk-medium {
        background: linear-gradient(135deg, #feca57 0%, #ff9ff3 100%);
    }
    .risk-low {
        background: linear-gradient(135deg, #48dbfb 0%, #0abde3 100%);
    }
    .alert-card {
        border-left: 4px solid #ff6b6b;
        padding: 1rem;
        margin: 0.5rem 0;
        background: #fff5f5;
        border-radius: 5px;
    }
    .sidebar .sidebar-content {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
</style>
""", unsafe_allow_html=True)

def get_database_connection():
    """Get database connection (fallback to hardcoded connection if DATABASE_URL is not set)"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        st.warning("DATABASE_URL not configured; falling back to hardcoded connection.")
        database_url = "postgresql://postgres:postgres@db:5432/delay_detection"
    try:
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def fetch_active_shipments():
    """Fetch active shipments with latest predictions"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = "postgresql://postgres:postgres@postgres:5432/delay_detection"
    
    try:
        # Use regular connection for pandas (not RealDictCursor)
        conn = psycopg2.connect(database_url)
        
        query = """
        SELECT 
            s.shipment_id,
            s.origin,
            s.destination,
            s.current_location,
            s.status,
            s.distance_remaining_km,
            s.vehicle_speed_kmph,
            s.weather,
            s.traffic_level,
            s.eta::text,
            s.updated_at::text,
            COALESCE(dp.delay_probability, 0) as delay_probability,
            COALESCE(dp.predicted_delay_minutes, 0) as predicted_delay_minutes,
            CASE 
                WHEN COALESCE(dp.delay_probability, 0) >= 0.7 THEN 'High'
                WHEN COALESCE(dp.delay_probability, 0) >= 0.4 THEN 'Medium'
                ELSE 'Low'
            END as risk_level
        FROM shipments s
        LEFT JOIN (
            SELECT DISTINCT ON (shipment_id) 
                shipment_id, delay_probability, predicted_delay_minutes
            FROM delay_predictions
            ORDER BY shipment_id, prediction_timestamp DESC
        ) dp ON s.shipment_id = dp.shipment_id
        WHERE s.status IN ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed')
        ORDER BY dp.delay_probability DESC NULLS LAST, s.updated_at DESC
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Convert timestamps
        if not df.empty:
            df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce')
            df['eta'] = pd.to_datetime(df['eta'], errors='coerce')
            df['delay_probability'] = pd.to_numeric(df['delay_probability'], errors='coerce').fillna(0)
            df['predicted_delay_minutes'] = pd.to_numeric(df['predicted_delay_minutes'], errors='coerce').fillna(0)
        
        return df
        
    except Exception as e:
        st.error(f"Error fetching shipments: {e}")
        return pd.DataFrame()

def fetch_alerts(hours=24):
    """Fetch recent alerts"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = "postgresql://postgres:postgres@postgres:5432/delay_detection"
    
    try:
        # Use regular connection for pandas (not RealDictCursor)
        conn = psycopg2.connect(database_url)
        
        query = """
        SELECT 
            a.id,
            a.shipment_id,
            a.alert_type,
            a.severity,
            a.title,
            a.message,
            a.triggered_at::text,
            a.is_active,
            s.origin,
            s.destination,
            s.current_location
        FROM alerts a
        JOIN shipments s ON a.shipment_id = s.shipment_id
        WHERE a.triggered_at > NOW() - INTERVAL '%s hours'
        ORDER BY a.triggered_at DESC
        LIMIT 100
        """
        
        df = pd.read_sql(query, conn, params=(hours,))
        conn.close()
        
        if not df.empty:
            df['triggered_at'] = pd.to_datetime(df['triggered_at'], errors='coerce')
        
        return df
        
    except Exception as e:
        st.error(f"Error fetching alerts: {e}")
        return pd.DataFrame()

def fetch_system_metrics():
    """Fetch system performance metrics"""
    conn = get_database_connection()
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor()
        
        # Total shipments
        cursor.execute("SELECT COUNT(*) FROM shipments")
        total_shipments = cursor.fetchone()['count']
        
        # Active shipments
        cursor.execute("""
            SELECT COUNT(*) FROM shipments 
            WHERE status IN ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed')
        """)
        active_shipments = cursor.fetchone()['count']
        
        # High risk shipments
        cursor.execute("""
            SELECT COUNT(*) FROM shipments s
            JOIN delay_predictions dp ON s.shipment_id = dp.shipment_id
            WHERE s.status IN ('In Transit', 'At Hub', 'Out for Delivery', 'Delayed')
            AND dp.delay_probability >= 0.7
            AND dp.prediction_timestamp > NOW() - INTERVAL '1 hour'
        """)
        high_risk_shipments = cursor.fetchone()['count']
        
        # Active alerts
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE is_active = TRUE")
        active_alerts = cursor.fetchone()['count']
        
        # Recent predictions
        cursor.execute("""
            SELECT COUNT(*) FROM delay_predictions 
            WHERE prediction_timestamp > NOW() - INTERVAL '1 hour'
        """)
        recent_predictions = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        return {
            'total_shipments': total_shipments,
            'active_shipments': active_shipments,
            'high_risk_shipments': high_risk_shipments,
            'active_alerts': active_alerts,
            'recent_predictions': recent_predictions
        }
        
    except Exception as e:
        st.error(f"Error fetching metrics: {e}")
        return {}

def create_risk_distribution_chart(df):
    """Create risk distribution pie chart"""
    if df.empty:
        return None
    
    risk_counts = df['risk_level'].value_counts()
    
    colors = {
        'High': '#ff6b6b',
        'Medium': '#feca57',
        'Low': '#48dbfb'
    }
    
    fig = px.pie(
        values=risk_counts.values,
        names=risk_counts.index,
        title="Shipment Risk Distribution",
        color_discrete_map=colors
    )
    
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(height=400)
    
    return fig

def create_delay_probability_histogram(df):
    """Create delay probability distribution histogram"""
    if df.empty or 'delay_probability' not in df.columns:
        return None
    
    fig = px.histogram(
        df,
        x='delay_probability',
        nbins=20,
        title="Delay Probability Distribution",
        labels={'delay_probability': 'Delay Probability', 'count': 'Number of Shipments'}
    )
    
    fig.update_layout(height=400)
    fig.add_vline(x=0.7, line_dash="dash", line_color="red", 
                  annotation_text="Alert Threshold")
    
    return fig

def create_shipment_timeline(df):
    """Create shipment status timeline"""
    if df.empty:
        return None
    
    # Group by hour and status
    df['hour'] = df['updated_at'].dt.floor('H')
    timeline_data = df.groupby(['hour', 'status']).size().reset_index(name='count')
    
    fig = px.line(
        timeline_data,
        x='hour',
        y='count',
        color='status',
        title="Shipment Activity Timeline (Last 24 Hours)"
    )
    
    fig.update_layout(height=400)
    
    return fig

def create_geographic_distribution(df):
    """Create geographic distribution of shipments"""
    if df.empty:
        return None
    
    # Count shipments by origin and destination
    origin_counts = df['origin'].value_counts().head(10)
    dest_counts = df['destination'].value_counts().head(10)
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Top Origins', 'Top Destinations'),
        specs=[[{"type": "bar"}, {"type": "bar"}]]
    )
    
    fig.add_trace(
        go.Bar(x=origin_counts.values, y=origin_counts.index, orientation='h'),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(x=dest_counts.values, y=dest_counts.index, orientation='h'),
        row=1, col=2
    )
    
    fig.update_layout(height=400, title_text="Geographic Distribution")
    
    return fig

def main():
    """Main dashboard function"""
    st.title("🚚 Smart Delay Detection System")
    st.markdown("Real-time supply chain monitoring and delay prediction")
    
    # Sidebar filters
    st.sidebar.header("📊 Dashboard Controls")
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)
    if auto_refresh:
        st.rerun()
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    
    # Risk level filter
    risk_filter = st.sidebar.multiselect(
        "Filter by Risk Level",
        ['High', 'Medium', 'Low'],
        default=['High', 'Medium', 'Low']
    )
    
    # Time range for alerts
    alert_hours = st.sidebar.slider("Alert Time Range (hours)", 1, 72, 24)
    
    # Fetch data
    with st.spinner("Loading data..."):
        shipments_df = fetch_active_shipments()
        alerts_df = fetch_alerts(alert_hours)
        metrics = fetch_system_metrics()
    
    # Filter shipments by risk level
    if not shipments_df.empty:
        shipments_df = shipments_df[shipments_df['risk_level'].isin(risk_filter)]
    
    # Display key metrics
    st.header("📈 System Overview")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "Total Shipments",
            metrics.get('total_shipments', 0),
            delta=None
        )
    
    with col2:
        st.metric(
            "Active Shipments",
            metrics.get('active_shipments', 0),
            delta=None
        )
    
    with col3:
        st.metric(
            "High Risk",
            metrics.get('high_risk_shipments', 0),
            delta=None,
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            "Active Alerts",
            metrics.get('active_alerts', 0),
            delta=None,
            delta_color="inverse"
        )
    
    with col5:
        st.metric(
            "Recent Predictions",
            metrics.get('recent_predictions', 0),
            delta=None
        )
    
    # Charts section
    st.header("📊 Analytics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        risk_chart = create_risk_distribution_chart(shipments_df)
        if risk_chart:
            st.plotly_chart(risk_chart, use_container_width=True)
    
    with col2:
        delay_chart = create_delay_probability_histogram(shipments_df)
        if delay_chart:
            st.plotly_chart(delay_chart, use_container_width=True)
    
    # Timeline and geographic distribution
    timeline_chart = create_shipment_timeline(shipments_df)
    if timeline_chart:
        st.plotly_chart(timeline_chart, use_container_width=True)
    
    geo_chart = create_geographic_distribution(shipments_df)
    if geo_chart:
        st.plotly_chart(geo_chart, use_container_width=True)
    
    # Active shipments table
    st.header("🚛 Active Shipments")
    
    if not shipments_df.empty:
        # Style the dataframe
        def style_risk(val):
            if val == 'High':
                return 'background-color: #ffebee; color: #c62828'
            elif val == 'Medium':
                return 'background-color: #fff8e1; color: #f57c00'
            else:
                return 'background-color: #e8f5e8; color: #2e7d32'
        
        styled_df = shipments_df[['shipment_id', 'origin', 'destination', 'status', 
                                 'risk_level', 'delay_probability', 'predicted_delay_minutes']].style.applymap(
            style_risk, subset=['risk_level']
        ).format({
            'delay_probability': '{:.1%}',
            'predicted_delay_minutes': '{:.0f} min'
        })
        
        st.dataframe(styled_df, use_container_width=True)
        
        # Download button
        csv = shipments_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Shipments CSV",
            data=csv,
            file_name=f"active_shipments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No active shipments match the current filters.")
    
    # Alerts section
    st.header("🚨 Recent Alerts")
    
    if not alerts_df.empty:
        # Filter active alerts
        active_alerts_df = alerts_df[alerts_df['is_active'] == True]
        
        if not active_alerts_df.empty:
            st.subheader("Active Alerts")
            for _, alert in active_alerts_df.iterrows():
                severity_color = {
                    'Critical': '#c62828',
                    'High': '#f57c00',
                    'Medium': '#fbc02d',
                    'Low': '#388e3c'
                }.get(alert['severity'], '#666')
                
                st.markdown(f"""
                <div style="border-left: 4px solid {severity_color}; padding: 1rem; margin: 0.5rem 0; 
                            background: #f8f9fa; border-radius: 5px;">
                    <strong>{alert['title']}</strong><br>
                    <small>Shipment: {alert['shipment_id']} | 
                    Route: {alert['origin']} → {alert['destination']}<br>
                    Triggered: {alert['triggered_at'].strftime('%Y-%m-%d %H:%M:%S')}</small><br>
                    {alert['message']}
                </div>
                """, unsafe_allow_html=True)
        
        # All alerts summary
        st.subheader(f"All Alerts (Last {alert_hours} hours)")
        
        alert_summary = alerts_df.groupby(['severity', 'is_active']).size().reset_index(name='count')
        st.dataframe(alert_summary, use_container_width=True)
        
    else:
        st.info("No alerts found for the selected time range.")
    
    # System health section
    st.header("🔧 System Health")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Database Status")
        if metrics:
            st.success("✅ Database Connected")
            st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.error("❌ Database Connection Failed")
    
    with col2:
        st.subheader("Data Freshness")
        if not shipments_df.empty:
            latest_update = shipments_df['updated_at'].max()
            time_diff = datetime.now() - latest_update.replace(tzinfo=None)
            
            if time_diff.total_seconds() < 300:  # 5 minutes
                st.success(f"✅ Data is fresh ({time_diff.total_seconds():.0f}s ago)")
            else:
                st.warning(f"⚠️ Data may be stale ({time_diff.total_seconds():.0f}s ago)")
        else:
            st.warning("⚠️ No recent shipment data")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666;'>"
        "Smart Delay Detection System | Real-time Supply Chain Monitoring"
        "</div>",
        unsafe_allow_html=True
    )
    
    # Auto-refresh mechanism
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()