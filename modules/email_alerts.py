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

        msg.attach(MIMEText(body, "html"))

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

BRAND   = "#00c4ce"
DARK    = "#13100d"


def _build_alert_email(row, status, dashboard_url):
    client    = row.get("CLIENT", "")
    project   = row.get("PROJECT", "")
    usage_1mo = int(row.get("usage_this_month",    0) or 0)
    usage_3mo = int(row.get("usage_last_3_months", 0) or 0)
    date_str  = datetime.utcnow().strftime("%B %d, %Y")

    if status == "Usage Dropped":
        subject    = f"Usage Alert — {client} / {project}"
        badge_text = "Usage Dropped"
        badge_bg   = "#fff3e0"
        badge_fg   = "#e65100"
        accent     = "#e65100"
        description = "Usage has fallen by more than 50% compared to this project's historical average."
        stats = [
            ("This month",       f"{usage_1mo} uses"),
            ("Last 3 months",    f"{usage_3mo} uses total"),
            ("Threshold",        "50% drop from historical avg"),
        ]
    else:  # No Recent Usage
        subject    = f"Usage Alert — {client} / {project}"
        badge_text = "No Recent Usage"
        badge_bg   = "#fdecea"
        badge_fg   = "#c62828"
        accent     = "#c62828"
        description = "This project had activity in the last 3 months but has recorded zero usage so far this month."
        stats = [
            ("This month",    "0 uses"),
            ("Last 3 months", f"{usage_3mo} uses total"),
        ]

    stat_rows = "".join(f"""
        <tr>
            <td style="padding: 10px 16px; color: #555; font-size: 13px; border-bottom: 1px solid #f0f0f0;">{label}</td>
            <td style="padding: 10px 16px; font-weight: 600; font-size: 13px; color: {DARK}; border-bottom: 1px solid #f0f0f0; text-align: right;">{value}</td>
        </tr>""" for label, value in stats)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:0; background:#f4f6f8; font-family: 'Helvetica Neue', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8; padding: 40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:{BRAND}; padding: 20px 32px;">
            <span style="font-size: 20px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">genia</span>
            <span style="font-size: 13px; color: rgba(255,255,255,0.7); margin-left: 12px;">Usage Dashboard</span>
          </td>
        </tr>

        <!-- Accent bar -->
        <tr><td style="background:{accent}; height:3px;"></td></tr>

        <!-- Body -->
        <tr>
          <td style="padding: 32px 32px 24px 32px;">
            <span style="display:inline-block; background:{badge_bg}; color:{badge_fg}; font-size:11px;
                         font-weight:700; text-transform:uppercase; letter-spacing:0.8px;
                         padding: 4px 12px; border-radius:20px; margin-bottom:16px;">
              {badge_text}
            </span>
            <h2 style="margin: 0 0 4px 0; font-size: 20px; color:{DARK}; font-weight:700;">{client}</h2>
            <p style="margin: 0 0 20px 0; font-size: 14px; color:#888;">{project}</p>
            <p style="margin: 0 0 24px 0; font-size: 14px; color:#444; line-height:1.6;">{description}</p>

            <!-- Stats table -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border: 1px solid #f0f0f0; border-radius:8px; overflow:hidden; margin-bottom:28px;">
              {stat_rows}
            </table>

            <!-- CTA -->
            <a href="{dashboard_url}"
               style="display:inline-block; background:{BRAND}; color:#ffffff; font-size:14px;
                      font-weight:700; padding:12px 28px; border-radius:8px; text-decoration:none;
                      letter-spacing:0.2px;">
              View Dashboard
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9f9f9; padding:16px 32px; border-top:1px solid #f0f0f0;">
            <p style="margin:0; font-size:11px; color:#aaa;">
              Automated alert from Genia &middot; {date_str}<br>
              To stop receiving alerts, contact your dashboard administrator.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html


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
