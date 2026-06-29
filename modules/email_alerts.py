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

ROI_ALERT_STATUSES      = {"Usage Dropped"}
ACTIVITY_ALERT_STATUSES = {"No Recent Usage"}


def _get_alert_type(row):
    """Return the alert type for a row, or None if no alert needed."""
    roi      = row.get('roi_status', '')
    activity = row.get('activity_status', '')
    if roi in ROI_ALERT_STATUSES:
        return roi
    if activity in ACTIVITY_ALERT_STATUSES:
        return activity
    return None


def _build_alert_email(row, status, dashboard_url):
    client = row.get('CLIENT', '')
    project = row.get('PROJECT', '')
    usage_1mo = row.get('usage_this_month', 0)
    usage_3mo = row.get('usage_last_3_months', 0)

    if status == "Usage Dropped":
        subject = f"⚠️ Usage Drop — {client} / {project}"
        headline = "Usage has dropped significantly"
        color = "#e65100"
        detail = f"""
        <p>This project was active but usage has fallen by more than 50% compared to its historical average.</p>
        <ul>
            <li><strong>This month:</strong> {int(usage_1mo)} uses</li>
            <li><strong>Last 3 months total:</strong> {int(usage_3mo)} uses</li>
            <li><strong>Alert type:</strong> Usage Dropped (&gt;50% decline from historical average)</li>
        </ul>"""
    else:  # No Recent Usage
        subject = f"🔴 No Recent Usage — {client} / {project}"
        headline = "No usage recorded this month"
        color = "#d32f2f"
        detail = f"""
        <p>This project had activity in the last 3 months but has recorded zero usage so far this month.</p>
        <ul>
            <li><strong>This month:</strong> 0 uses</li>
            <li><strong>Last 3 months total:</strong> {int(usage_3mo)} uses</li>
            <li><strong>Alert type:</strong> No Recent Usage</li>
        </ul>"""

    body = f"""
    <div style="border-left: 4px solid {color}; padding-left: 16px; margin-bottom: 16px;">
        <h3 style="color: {color}; margin: 0 0 4px 0;">{headline}</h3>
        <p style="margin: 0; color: #555; font-size: 14px;"><strong>{client}</strong> — {project}</p>
    </div>
    {detail}
    <p style="margin-top: 20px;">
        <a href="{dashboard_url}" style="background-color: #00c4ce; color: white; padding: 10px 20px;
           text-decoration: none; border-radius: 4px; font-weight: bold;">
            View Dashboard
        </a>
    </p>"""
    return subject, body


def check_and_send_alerts(df, smtp_config, alert_config):
    """Check all projects and send alerts for Usage Dropped / No Recent Usage."""
    alerts_sent = []
    alerts_skipped = []

    today = datetime.now()
    if today.weekday() >= 5:
        return [], [{'project': 'ALL', 'reason': f'Skipped — today is a {today.strftime("%A")}'}]

    recipient_list = alert_config.get('to_emails', [])
    if not recipient_list:
        return [], [{'project': 'N/A', 'reason': 'No recipients configured in ALERT_TO_EMAILS'}]

    dashboard_url = alert_config.get('dashboard_url', '#')

    for _, row in df.iterrows():
        project_key = f"{row['COMPANY']}_{row['PROJECT']}"
        status = _get_alert_type(row)

        if status is None:
            alerts_skipped.append({'project': project_key, 'reason': f'Status OK: {status}'})
            continue

        ok_to_send, reason = should_send_alert(project_key)
        if not ok_to_send:
            alerts_skipped.append({'project': project_key, 'reason': reason})
            continue

        subject, body = _build_alert_email(row, status, dashboard_url)

        all_success = True
        failed = []
        for email in recipient_list:
            success, message = send_email_alert(smtp_config, email, subject, body)
            if not success:
                all_success = False
                failed.append(f"{email} ({message})")

        if all_success:
            record_alert(project_key)
            alerts_sent.append({
                'project': project_key,
                'status': status,
                'sent_to': len(recipient_list),
            })
        else:
            alerts_skipped.append({
                'project': project_key,
                'reason': f"Send failed: {', '.join(failed)}",
            })

    return alerts_sent, alerts_skipped
