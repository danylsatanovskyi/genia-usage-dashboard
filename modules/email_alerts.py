"""
Email alerts module - Send alerts when a project transitions into a bad status.

Persistence is in Supabase project_metadata (last_alert_status, last_alert_sent columns),
so alert state survives Render redeploys.

Alert fires only on TRANSITION: OK → bad status.
When a project recovers, last_alert_status is cleared so the next drop re-triggers.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

BAD_STATUSES = {"Usage Dropped", "No Recent Usage"}


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

def send_email_alert(smtp_config, to_email, subject, body):
    """Send a single HTML email. Returns (success, message)."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = smtp_config["from_email"]
        msg["To"]      = to_email
        msg["Subject"] = subject

        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #d32f2f;">Usage Alert</h2>
                {body}
                <hr>
                <p style="color: #666; font-size: 12px;">
                    Automated alert from the Genia Usage Dashboard.<br>
                    Sent on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S UTC')}
                </p>
            </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_config["smtp_server"], smtp_config["smtp_port"])
        server.starttls()
        server.login(smtp_config["smtp_user"], smtp_config["smtp_password"])
        server.send_message(msg)
        server.quit()
        return True, "Sent"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Email body builders
# ---------------------------------------------------------------------------

def _build_alert_email(row, status, dashboard_url):
    client   = row.get("CLIENT", "")
    project  = row.get("PROJECT", "")
    usage_1mo  = int(row.get("usage_this_month",     0) or 0)
    usage_3mo  = int(row.get("usage_last_3_months",  0) or 0)

    if status == "Usage Dropped":
        subject  = f"⚠️ Usage Drop — {client} / {project}"
        headline = "Usage has dropped significantly"
        color    = "#e65100"
        detail   = f"""
        <p>This project was active but usage has fallen by more than 50% vs its historical average.</p>
        <ul>
            <li><strong>This month:</strong> {usage_1mo} uses</li>
            <li><strong>Last 3 months total:</strong> {usage_3mo} uses</li>
        </ul>"""
    else:  # No Recent Usage
        subject  = f"🔴 No Recent Usage — {client} / {project}"
        headline = "No usage recorded this month"
        color    = "#d32f2f"
        detail   = f"""
        <p>This project had activity in the last 3 months but has recorded zero usage so far this month.</p>
        <ul>
            <li><strong>This month:</strong> 0 uses</li>
            <li><strong>Last 3 months total:</strong> {usage_3mo} uses</li>
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


# ---------------------------------------------------------------------------
# Supabase alert state helpers
# ---------------------------------------------------------------------------

def _get_stored_alert_status(sb, project_key):
    """Return (last_alert_status, last_alert_sent) stored in Supabase, or (None, None)."""
    try:
        rows = sb.table("project_metadata").select("last_alert_status,last_alert_sent") \
                 .eq("key", project_key).execute().data
        if rows:
            r = rows[0]
            return r.get("last_alert_status"), r.get("last_alert_sent")
    except Exception as e:
        print(f"_get_stored_alert_status error for {project_key}: {e}")
    return None, None


def _save_alert_state(sb, project_key, alert_status, sent_at):
    """Upsert last_alert_status + last_alert_sent into project_metadata."""
    try:
        sb.table("project_metadata").upsert({
            "key": project_key,
            "last_alert_status": alert_status,
            "last_alert_sent":   sent_at,
        }).execute()
    except Exception as e:
        print(f"_save_alert_state error for {project_key}: {e}")


def _clear_alert_state(sb, project_key):
    """Clear last_alert_status when a project recovers (so next drop re-triggers)."""
    try:
        sb.table("project_metadata").upsert({
            "key": project_key,
            "last_alert_status": None,
            "last_alert_sent":   None,
        }).execute()
    except Exception as e:
        print(f"_clear_alert_state error for {project_key}: {e}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_and_send_alerts(df, smtp_config, alert_config, sb):
    """
    For each project row:
      - Determine current status (bad or OK)
      - Compare to stored last_alert_status in Supabase
      - Alert only on transition into bad status
      - Clear stored status when project recovers

    Returns (alerts_sent, alerts_skipped) lists for logging.
    """
    alerts_sent    = []
    alerts_skipped = []

    today = datetime.utcnow()
    if today.weekday() >= 5:
        return [], [{"project": "ALL", "reason": f"Skipped — {today.strftime('%A')}"}]

    recipient_list = alert_config.get("to_emails", [])
    if not recipient_list:
        return [], [{"project": "N/A", "reason": "No recipients in ALERT_TO_EMAILS"}]

    dashboard_url = alert_config.get("dashboard_url", "#")

    for _, row in df.iterrows():
        client      = row.get("CLIENT", "") or row.get("COMPANY", "")
        project     = row.get("PROJECT", "")
        project_key = f"{client}_{project}"

        # Determine current alert-worthy status
        roi_status      = row.get("roi_status",      "") or ""
        activity_status = row.get("activity_status", "") or ""
        current_status  = None
        # roi_status can be "Usage Dropped + Below Mo. Target" — check with startswith
        if "Usage Dropped" in roi_status:
            current_status = "Usage Dropped"
        elif activity_status in BAD_STATUSES:
            current_status = activity_status

        stored_status, _ = _get_stored_alert_status(sb, project_key)

        # Recovered — clear stored state so next drop will fire again
        if current_status is None and stored_status is not None:
            _clear_alert_state(sb, project_key)
            alerts_skipped.append({"project": project_key, "reason": "Recovered — state cleared"})
            continue

        # No issue
        if current_status is None:
            alerts_skipped.append({"project": project_key, "reason": "Status OK"})
            continue

        # Already alerted for this status — don't re-send
        if stored_status == current_status:
            alerts_skipped.append({"project": project_key,
                                   "reason": f"Already alerted for: {current_status}"})
            continue

        # Transition into bad status — send alert
        subject, body = _build_alert_email(row, current_status, dashboard_url)
        sent_at = datetime.utcnow().isoformat()

        all_ok = True
        failed = []
        for email in recipient_list:
            ok, msg = send_email_alert(smtp_config, email, subject, body)
            if not ok:
                all_ok = False
                failed.append(f"{email} ({msg})")

        if all_ok:
            _save_alert_state(sb, project_key, current_status, sent_at)
            alerts_sent.append({
                "project":  project_key,
                "status":   current_status,
                "sent_to":  len(recipient_list),
                "sent_at":  sent_at,
            })
        else:
            alerts_skipped.append({
                "project": project_key,
                "reason":  f"Send failed: {', '.join(failed)}",
            })

    return alerts_sent, alerts_skipped
