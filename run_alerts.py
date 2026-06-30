"""
Render Cron Job script — runs daily to send usage alert emails.

Called by Render Cron Job service (see render.yaml).
Loads fresh data, checks for status transitions, sends emails.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, COMPANY_CONFIGS
from modules.data_loader import load_data, calculate_metrics
from modules.email_alerts import check_and_send_alerts

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Load metadata (needed for load_data)
    try:
        meta_rows = sb.table("project_metadata").select("*").execute().data
        metadata  = {r["key"]: {k: v for k, v in r.items() if k != "key"} for r in meta_rows}
    except Exception as e:
        print(f"[alerts] Failed to load metadata: {e}")
        sys.exit(1)

    # Load + compute metrics (same pipeline as the dashboard)
    df = load_data(sb, COMPANY_CONFIGS, metadata)
    if df.empty:
        print("[alerts] No data loaded — exiting.")
        sys.exit(0)
    df = calculate_metrics(df)

    smtp_config = {
        "smtp_server":  os.getenv("SMTP_SERVER",  "smtp.gmail.com"),
        "smtp_port":    int(os.getenv("SMTP_PORT", "587")),
        "smtp_user":    os.getenv("SMTP_USER",     ""),
        "smtp_password":os.getenv("SMTP_PASSWORD", ""),
        "from_email":   os.getenv("ALERT_FROM_EMAIL", ""),
    }

    to_emails_raw = os.getenv("ALERT_TO_EMAILS", "")
    alert_config  = {
        "to_emails":    [e.strip() for e in to_emails_raw.split(",") if e.strip()],
        "dashboard_url": os.getenv("DASHBOARD_URL", "#"),
    }

    sent, skipped = check_and_send_alerts(df, smtp_config, alert_config, sb)

    print(f"[alerts] Sent: {len(sent)}  Skipped: {len(skipped)}")
    for s in sent:
        print(f"  ✓ {s['project']} — {s['status']} → {s['sent_to']} recipient(s)")
    for sk in skipped:
        print(f"  – {sk['project']}: {sk['reason']}")

if __name__ == "__main__":
    main()
