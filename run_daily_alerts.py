"""
Automated Daily Alert Checker
Run this script once per day (e.g., at 11:59 PM) to automatically check and send alerts
Uses same data loading as dashboard for consistent metrics
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, COMPANY_CONFIGS
from modules.email_alerts import check_and_send_alerts
from modules.data_loader import load_data, calculate_metrics

load_dotenv()

def run_daily_alerts():
    """Main function to run daily alert check"""
    print(f"\n{'='*60}")
    print(f"Daily Alert Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Check environment variables
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('ALERT_FROM_EMAIL')
    
    if not all([smtp_server, smtp_user, smtp_password, from_email]):
        print("❌ ERROR: Email configuration missing in .env file")
        print("   Please configure SMTP_SERVER, SMTP_USER, SMTP_PASSWORD, ALERT_FROM_EMAIL")
        return
    
    # Initialize Supabase
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to Supabase: {str(e)}")
        return
    
    # Load data (same logic as dashboard)
    print("📊 Loading project data...")
    import json as _json
    _metadata_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'project_metadata.json')
    project_metadata = {}
    if os.path.exists(_metadata_file):
        with open(_metadata_file, 'r') as _f:
            project_metadata = _json.load(_f)
    df = load_data(supabase, COMPANY_CONFIGS, project_metadata)
    df = calculate_metrics(df)
    
    if df.empty:
        print("⚠️  No project data found")
        return
    
    print(f"   Found {len(df)} projects")
    
    # Configure SMTP
    smtp_config = {
        'smtp_server': smtp_server,
        'smtp_port': int(os.getenv('SMTP_PORT', 587)),
        'smtp_user': smtp_user,
        'smtp_password': smtp_password,
        'from_email': from_email
    }
    
    # Configure alerts
    alert_config = {
        'dashboard_url': os.getenv('DASHBOARD_URL', 'http://localhost:8501'),
        'to_emails': [email.strip() for email in os.getenv('ALERT_TO_EMAILS', '').split(',') if email.strip()]
    }
    
    # Check for recipients
    if not alert_config['to_emails']:
        print("⚠️  No recipients configured - no alerts will be sent")
        print("   Add ALERT_TO_EMAILS to your .env file")
        print("   Example: ALERT_TO_EMAILS=email1@company.com,email2@company.com")
        return
    
    print(f"📧 Recipients: {len(alert_config['to_emails'])}")
    for email in alert_config['to_emails']:
        print(f"   - {email}")
    
    # Run alert check
    print("\n🔍 Checking for usage drops...")
    alerts_sent, alerts_skipped = check_and_send_alerts(df, smtp_config, alert_config)
    
    # Report results
    print(f"\n{'='*60}")
    if alerts_sent:
        print(f"✅ SENT {len(alerts_sent)} ALERT(S):")
        for alert in alerts_sent:
            print(f"   - {alert['project']}")
            print(f"     Yesterday: {alert['yesterday']:.0f}, Avg: {alert['avg']:.1f}")
            print(f"     Sent to: {alert['sent_to']} subscriber(s)")
    else:
        print("✅ NO ALERTS NEEDED - All projects performing normally")
    
    if alerts_skipped:
        print(f"\n⏭️  SKIPPED {len(alerts_skipped)} PROJECT(S):")
        for skip in alerts_skipped:
            print(f"   - {skip['project']}: {skip['reason']}")
    
    print(f"\n{'='*60}")
    print("Daily alert check complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    try:
        run_daily_alerts()
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
