"""
Automated Daily Alert Checker
Run this script once per day (e.g., at 11:59 PM) to automatically check and send alerts
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, COMPANY_CONFIGS
from modules.email_alerts import check_and_send_alerts

# Load environment variables
load_dotenv()

def load_data_for_alerts(supabase):
    """Load data from Supabase (simplified version for alerts)"""
    from datetime import date, timedelta
    import pandas as pd
    
    MONTHS_FR = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 
                 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']
    
    all_data = []
    
    for company_name, company_config in COMPANY_CONFIGS.items():
        for project_name, project_config in company_config['projects'].items():
            try:
                table_name = project_config['supabase_table']
                usage_field = project_config['usage_field']
                value_type = project_config['value_type']
                
                # Fetch records
                response = supabase.table(table_name).select("*").execute()
                
                if not response.data:
                    continue
                
                records_df = pd.DataFrame(response.data)
                records_df['created_at'] = pd.to_datetime(records_df['created_at'], errors='coerce')
                records_df = records_df[records_df['created_at'].notna()]
                
                records_df['month'] = records_df['created_at'].dt.month
                records_df['year'] = records_df['created_at'].dt.year
                records_df['date'] = records_df['created_at'].dt.date
                
                # Calculate yesterday's usage
                yesterday = date.today() - timedelta(days=1)
                yesterday_records = records_df[records_df['date'] == yesterday]
                
                if value_type == "boolean":
                    usage_yesterday = yesterday_records[usage_field].sum() if usage_field in yesterday_records.columns else 0
                else:
                    usage_yesterday = yesterday_records[usage_field].sum() if usage_field in yesterday_records.columns else 0
                
                # Calculate 3-month usage
                three_months_ago = date.today() - timedelta(days=90)
                recent_records = records_df[records_df['date'] >= three_months_ago]
                
                if value_type == "boolean":
                    usage_3mo = recent_records[usage_field].sum() if usage_field in recent_records.columns else 0
                else:
                    usage_3mo = recent_records[usage_field].sum() if usage_field in recent_records.columns else 0
                
                recent_monthly_avg = usage_3mo / 3 if usage_3mo > 0 else 0
                
                # Add to results
                all_data.append({
                    'COMPANY': company_name,
                    'CLIENT': company_name,
                    'PROJECT': project_name,
                    'usage_yesterday': usage_yesterday,
                    'usage_last_3_months': usage_3mo,
                    'recent_monthly_avg': recent_monthly_avg,
                    'roi_status': 'Active'
                })
                
            except Exception as e:
                print(f"Error processing {company_name} - {project_name}: {str(e)}")
                continue
    
    return pd.DataFrame(all_data)

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
    
    # Load data
    print("📊 Loading project data...")
    df = load_data_for_alerts(supabase)
    
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
