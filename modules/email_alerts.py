"""
Email alerts module - Send alerts when usage drops below thresholds
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import json
import os

ALERTS_FILE = 'alert_history.json'
SUBSCRIBERS_FILE = 'alert_subscribers.json'

def load_alert_history():
    """Load alert history to track sent alerts"""
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, 'r') as f:
            return json.load(f)
    return {"alerts": []}

def save_alert_history(history):
    """Save alert history"""
    with open(ALERTS_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def should_send_alert(project_key, cooldown_days=7):
    """Check if we should send an alert for this project (cooldown logic)"""
    history = load_alert_history()
    
    # Check if we've sent an alert recently
    for alert in history['alerts']:
        if alert['project'] == project_key:
            last_sent = datetime.fromisoformat(alert['last_sent'])
            days_since = (datetime.now() - last_sent).days
            
            if days_since < cooldown_days:
                return False, f"Alert sent {days_since} days ago"
    
    return True, "OK to send"

def record_alert(project_key):
    """Record that an alert was sent"""
    history = load_alert_history()
    
    # Update or add alert record
    found = False
    for alert in history['alerts']:
        if alert['project'] == project_key:
            alert['last_sent'] = datetime.now().isoformat()
            alert['count'] = alert.get('count', 0) + 1
            found = True
            break
    
    if not found:
        history['alerts'].append({
            'project': project_key,
            'last_sent': datetime.now().isoformat(),
            'count': 1
        })
    
    save_alert_history(history)

def send_email_alert(smtp_config, to_email, subject, body):
    """Send email alert via SMTP"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = smtp_config['from_email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Create HTML body
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #d32f2f;">Usage Alert</h2>
                {body}
                <hr>
                <p style="color: #666; font-size: 12px;">
                    This is an automated alert from the Client Solutions ROI Dashboard.<br>
                    Sent on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
                </p>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        # Connect to SMTP server
        server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'])
        server.starttls()
        server.login(smtp_config['smtp_user'], smtp_config['smtp_password'])
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        return True, "Email sent successfully"
    
    except Exception as e:
        return False, f"Error sending email: {str(e)}"

def load_subscribers():
    """Load subscriber email list"""
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r') as f:
            return json.load(f)
    return {"subscribers": []}

def save_subscribers(subscribers_data):
    """Save subscriber email list"""
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(subscribers_data, f, indent=2)

def add_subscriber(email):
    """Add an email to the subscriber list"""
    subscribers = load_subscribers()
    email = email.strip().lower()
    
    if email not in subscribers['subscribers']:
        subscribers['subscribers'].append(email)
        save_subscribers(subscribers)
        return True, "Subscribed successfully!"
    return False, "Email already subscribed"

def remove_subscriber(email):
    """Remove an email from the subscriber list"""
    subscribers = load_subscribers()
    email = email.strip().lower()
    
    if email in subscribers['subscribers']:
        subscribers['subscribers'].remove(email)
        save_subscribers(subscribers)
        return True, "Unsubscribed successfully!"
    return False, "Email not found"

def check_and_send_alerts(df, smtp_config, alert_config):
    """Check all projects and send alerts if needed"""
    alerts_sent = []
    alerts_skipped = []

    # Don't alert on weekends — yesterday's low usage is expected
    yesterday = datetime.now() - timedelta(days=1)
    if yesterday.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return [], [{'project': 'ALL', 'reason': f'Skipped — yesterday was a {yesterday.strftime("%A")}'}]

    # Get recipients from config (comma-separated list)
    recipient_list = alert_config.get('to_emails', [])
    
    if not recipient_list:
        return [], [{'project': 'N/A', 'reason': 'No recipients configured in ALERT_TO_EMAILS'}]
    
    for _, row in df.iterrows():
        project_key = f"{row['COMPANY']}_{row['PROJECT']}"
        
        # Check if yesterday's usage is below 3-month average
        yesterday_usage = row.get('usage_yesterday', 0)
        recent_avg = row.get('recent_monthly_avg', 0)
        
        # Alert condition: yesterday < 3-month daily average (strictly less than)
        # daily_avg = total_3mo_usage / 90 days (approx 3 months)
        usage_3mo = row.get('usage_last_3_months', 0)
        daily_avg_3mo = usage_3mo / 90 if usage_3mo > 0 else 0
        if daily_avg_3mo == 0:
            alerts_skipped.append({'project': project_key, 'reason': 'No 3-month baseline (avg=0)'})
            continue
        
        if yesterday_usage < daily_avg_3mo:
            # Prepare email
            subject = f"⚠️ Usage Drop Alert: {row['CLIENT']} - {row['PROJECT']}"
            body = f"""
            <p><strong>Project:</strong> {row['CLIENT']} - {row['PROJECT']}</p>
            <p><strong>Yesterday's Usage:</strong> {yesterday_usage:.0f}</p>
            <p><strong>3-Month Daily Average:</strong> {daily_avg_3mo:.2f} ({usage_3mo:.0f} usages / 90 days)</p>
            <p><strong>Status:</strong> <span style="color: #d32f2f;">Below Average</span></p>
            
            <h3>Details:</h3>
            <ul>
                <li>Last 30 days usage: {row.get('usage_last_30_days', 0):.0f}</li>
                <li>Last 3 months total: {row.get('usage_last_3_months', 0):.0f}</li>
                <li>ROI Status: {row.get('roi_status', 'Unknown')}</li>
            </ul>
            
            <p style="margin-top: 20px;">
                <a href="{alert_config.get('dashboard_url', '#')}" 
                   style="background-color: #1976d2; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 4px;">
                    View Dashboard
                </a>
            </p>
            """
            
            # Send email to ALL recipients
            all_success = True
            failed_recipients = []
            
            for recipient_email in recipient_list:
                success, message = send_email_alert(
                    smtp_config,
                    recipient_email,
                    subject,
                    body
                )
                
                if not success:
                    all_success = False
                    failed_recipients.append(f"{recipient_email} ({message})")
            
            if all_success:
                alerts_sent.append({
                    'project': project_key,
                    'yesterday': yesterday_usage,
                    'avg': daily_avg_3mo,
                    'sent_to': len(recipient_list)
                })
            else:
                alerts_skipped.append({
                    'project': project_key,
                    'reason': f"Failed to send to: {', '.join(failed_recipients)}"
                })
        else:
            alerts_skipped.append({
                'project': project_key,
                'reason': f'Above average ({yesterday_usage:.0f} >= {daily_avg_3mo:.1f})'
            })
    
    return alerts_sent, alerts_skipped
