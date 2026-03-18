# Email Alerts - Quick Start

## What It Does

Automatically sends email alerts when **yesterday's usage is below the 3-month daily average**.

## Setup (5 minutes)

### 1. Get Gmail App Password
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Create password for "ROI Dashboard"
3. Copy the 16-character password

### 2. Update .env file
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
ALERT_FROM_EMAIL=your.email@gmail.com
ALERT_TO_EMAIL=alerts@yourcompany.com
```

### 3. Test in Dashboard
1. Run your Streamlit app
2. Go to **Settings** tab
3. Expand **Email Alert Configuration**
4. Click **Send Test Email**
5. Verify you received the test email

### 4. Run Alert Check
- Click **Run Alert Check** to manually check all projects
- Alerts will be sent for any project below its 3-month average
- Cooldown period: 7 days (prevents duplicate alerts)

## Alert Condition

```
IF yesterday_usage < (3_month_total / 90):
    SEND ALERT
```

Example:
- 3-month total: 1,800 usages
- 3-month daily average: 20 usages/day
- Yesterday: 8 usages
- **→ Alert sent** (8 < 20)

## What's Included in Alert Email

- Project name and company
- Yesterday's usage vs. 3-month average
- Last 30 days, 3 months, 12 months totals
- ROI status
- Direct link to dashboard

## Cooldown System

- Default: 7 days between alerts for same project
- Tracks in `alert_history.json`
- Prevents alert fatigue
- Configurable in Settings (1-30 days)

## Files Created

- `modules/email_alerts.py` - Alert logic
- `alert_history.json` - Tracks sent alerts
- `EMAIL_ALERTS_GUIDE.md` - Full documentation

## Next Steps

For automated daily checks, see the full guide: `EMAIL_ALERTS_GUIDE.md`

## Troubleshooting

**Test email fails?**
- Make sure you used App Password (not regular password)
- Check SMTP settings match your provider
- Verify firewall allows SMTP connections

**No alerts sent?**
- Check if projects are actually below average
- Verify cooldown period hasn't been triggered
- Ensure projects have 3+ months of data

## Support

Full documentation: `EMAIL_ALERTS_GUIDE.md`
