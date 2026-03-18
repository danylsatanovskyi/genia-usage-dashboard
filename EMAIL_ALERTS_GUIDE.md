# Email Alerts Setup Guide

## Overview

The ROI Dashboard can send automatic email alerts when a project's usage drops below its 3-month average. This helps you catch issues early and maintain high solution adoption.

## Alert Condition

**An alert is sent when:**
```
Yesterday's Usage < (3-Month Total Usage / 90 days)
```

For example:
- If a project has 900 usages over the last 3 months (3-month daily avg = 10)
- And yesterday had only 3 usages
- An alert will be sent (3 < 10)

## Features

### 1. Automatic Alert Detection
- Compares yesterday's complete usage (midnight to midnight) with the 3-month daily average
- Checks all active projects in your dashboard

### 2. Cooldown Period
- Prevents alert fatigue by limiting alerts per project
- Default: 7 days between alerts for the same project
- Configurable from 1-30 days

### 3. Alert History Tracking
- Stores when alerts were sent in `alert_history.json`
- Tracks alert count per project

### 4. Rich Email Content
- Project details (company, name, usage stats)
- Yesterday's usage vs. average comparison
- Last 30 days, 3 months, and 12 months totals
- ROI status
- Direct link to dashboard

## Setup Instructions

### Step 1: Configure Email Settings

Edit your `.env` file with your email provider's settings:

```env
# Email Alert Settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_FROM_EMAIL=your-email@gmail.com
ALERT_TO_EMAIL=recipient@company.com
```

### Step 2: Gmail Setup (Recommended)

1. **Enable 2-Factor Authentication**
   - Go to [myaccount.google.com/security](https://myaccount.google.com/security)
   - Enable 2-Step Verification

2. **Generate App Password**
   - Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Select "Mail" and "Other (Custom name)"
   - Name it "ROI Dashboard"
   - Copy the 16-character password

3. **Update .env file**
   ```env
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop  # Your 16-char App Password
   ALERT_FROM_EMAIL=your.email@gmail.com
   ALERT_TO_EMAIL=alerts@yourcompany.com
   ```

### Step 3: Other Email Providers

**Microsoft Outlook / Office 365:**
```env
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-password
```

**Yahoo Mail:**
```env
SMTP_SERVER=smtp.mail.yahoo.com
SMTP_PORT=587
SMTP_USER=your-email@yahoo.com
SMTP_PASSWORD=your-app-password  # Generate at account.yahoo.com/account/security
```

**Custom SMTP Server:**
```env
SMTP_SERVER=mail.yourcompany.com
SMTP_PORT=587  # or 465 for SSL
SMTP_USER=alerts@yourcompany.com
SMTP_PASSWORD=your-password
```

### Step 4: Test Your Configuration

1. Go to **Settings** tab in the dashboard
2. Expand **Email Alert Configuration**
3. Verify your SMTP settings are loaded
4. Click **Send Test Email**
5. Check your inbox for the test email

If the test fails, check:
- SMTP server and port are correct
- Username and password are correct
- App Password is used (not regular password for Gmail)
- Firewall/network allows SMTP connections

## Usage

### Manual Alert Check

1. Go to **Settings** tab
2. Expand **Email Alert Configuration**
3. Click **Run Alert Check**
4. Review which alerts were sent/skipped

### Automated Alerts (Coming Soon)

To set up automatic daily checks, you can:
- Deploy the dashboard to a server with a cron job
- Use a task scheduler to run the alert check
- Set up a webhook trigger

Example cron job (runs daily at 9 AM):
```bash
0 9 * * * curl -X POST https://your-dashboard-url.com/run-alerts
```

## Alert Email Example

```
Subject: ⚠️ Usage Drop Alert: CELLCOM - HR CHATBOT

Project: CELLCOM - HR CHATBOT
Yesterday's Usage: 3
3-Month Daily Average: 15.5
Status: Below Average

Details:
• Last 30 days usage: 425
• Last 3 months total: 1,395
• ROI Status: Goal Achieved

[View Dashboard]
```

## Troubleshooting

### Test Email Not Sending

**Problem:** "Authentication failed"
- **Solution:** Use App Password instead of regular password
- **Gmail:** Generate at myaccount.google.com/apppasswords
- **Yahoo:** Generate at account.yahoo.com/account/security

**Problem:** "Connection refused"
- **Solution:** Check firewall/network settings
- Verify SMTP server and port are correct
- Try port 465 (SSL) instead of 587 (TLS)

**Problem:** "Sender address rejected"
- **Solution:** Ensure From Email matches SMTP User
- Some providers require matching addresses

### No Alerts Being Sent

**Check:**
1. Are projects actually below their 3-month average?
2. Is the project in cooldown period? (Check `alert_history.json`)
3. Does the project have at least 3 months of data?
4. Run manual check to see why alerts are skipped

### Alert History Issues

If you need to reset alert history:
```bash
# Delete alert history
rm alert_history.json

# Or manually edit
{
  "alerts": []
}
```

## Files

- `modules/email_alerts.py` - Alert logic and email sending
- `alert_history.json` - Tracks sent alerts and cooldowns
- `.env` - Email configuration (not committed to git)
- `.env.example` - Template for email settings

## Security Best Practices

1. **Never commit `.env` to git** - Keep credentials private
2. **Use App Passwords** - More secure than regular passwords
3. **Limit recipient list** - Only send to authorized team members
4. **Rotate passwords** - Update App Passwords periodically
5. **Monitor alert history** - Review `alert_history.json` regularly

## Customization

### Change Alert Threshold

Edit `modules/email_alerts.py`:
```python
# Current: yesterday < 3-month avg
daily_avg_3mo = recent_avg / 30

# Option 1: Use 1-month average instead
daily_avg_1mo = row.get('usage_last_30_days', 0) / 30
if yesterday_usage < daily_avg_1mo:
    # send alert

# Option 2: Add percentage threshold (e.g., 50% below average)
threshold = daily_avg_3mo * 0.5
if yesterday_usage < threshold:
    # send alert
```

### Customize Email Template

Edit the `body` variable in `check_and_send_alerts()`:
```python
body = f"""
<p><strong>Project:</strong> {row['CLIENT']} - {row['PROJECT']}</p>
<!-- Add your custom content here -->
"""
```

## FAQ

**Q: Can I send alerts to multiple recipients?**
A: Yes, set `ALERT_TO_EMAIL` to comma-separated addresses:
```env
ALERT_TO_EMAIL=manager@company.com,ops@company.com
```

**Q: How do I disable alerts temporarily?**
A: Either:
1. Don't configure email settings in `.env`
2. Set a very high cooldown period (30 days)
3. Comment out email env variables

**Q: Can I get alerts for specific projects only?**
A: Yes, edit `check_and_send_alerts()` to filter by company or project name:
```python
if row['COMPANY'] != 'CELLCOM':
    continue  # Skip non-CELLCOM projects
```

**Q: What if I want alerts immediately (not just yesterday)?**
A: You can add real-time usage tracking by:
1. Setting up Supabase webhooks
2. Creating a separate monitoring service
3. Using the Refresh button + manual alert check

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review `alert_history.json` for cooldown status
3. Test with a simple Gmail setup first
4. Check Streamlit logs for error messages
