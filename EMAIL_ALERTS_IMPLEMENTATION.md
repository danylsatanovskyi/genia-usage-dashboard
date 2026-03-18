# Email Alerts Implementation - Complete

## ✅ What Was Implemented

Automatic email alerts that trigger when **yesterday's usage is below the 3-month daily average**.

## 📋 Files Created/Modified

### New Files:
1. `modules/email_alerts.py` - Core alert logic and email sending
2. `modules/__init__.py` - Python package initialization
3. `alert_history.json` - Tracks sent alerts and cooldown periods
4. `EMAIL_ALERTS_GUIDE.md` - Comprehensive documentation
5. `EMAIL_ALERTS_QUICKSTART.md` - Quick setup guide

### Modified Files:
1. `app.py` - Added email alerts UI in Settings tab
2. `.env` - Added email configuration variables
3. `.env.example` - Updated with email settings template
4. `README.md` - Added email alerts section

## 🎯 How It Works

### Alert Trigger Condition:
```python
IF yesterday_usage < (3_month_total_usage / 90):
    SEND EMAIL ALERT
```

### Example:
- Project has 1,800 usages over last 3 months
- Daily average = 1,800 / 90 = 20 usages/day
- Yesterday had 8 usages
- **→ Alert sent** (8 < 20)

### Cooldown System:
- Default: 7 days between alerts for the same project
- Prevents alert fatigue
- Configurable in Settings (1-30 days)
- Tracked in `alert_history.json`

## 🚀 How to Use

### 1. Configure Email (One-time setup)

**For Gmail (Recommended):**

1. Enable 2-Factor Authentication at [myaccount.google.com/security](https://myaccount.google.com/security)
2. Generate App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Update `.env` file:
   ```env
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop  # 16-char App Password
   ALERT_FROM_EMAIL=your.email@gmail.com
   ALERT_TO_EMAIL=alerts@company.com
   ```

### 2. Test Email Configuration

1. Run `streamlit run app.py`
2. Go to **Settings** tab
3. Expand **Email Alert Configuration**
4. Click **Send Test Email**
5. Verify you receive the test email

### 3. Run Alert Check (Manual)

1. In **Settings** → **Email Alert Configuration**
2. Click **Run Alert Check**
3. System will:
   - Check all projects
   - Compare yesterday's usage to 3-month average
   - Send alerts for projects below threshold
   - Respect cooldown period

### 4. Review Results

- **Alerts Sent:** Shows which projects triggered alerts
- **Alerts Skipped:** Shows why alerts weren't sent (cooldown, above threshold, etc.)
- **Alert History:** Check `alert_history.json` for full history

## 📧 Email Content

Each alert email includes:

- **Project identification** (Company + Project Name)
- **Usage comparison:**
  - Yesterday's usage count
  - 3-month daily average
- **Additional context:**
  - Last 30 days total
  - Last 3 months total
  - ROI status
- **Action button:** Direct link to dashboard

## 🔧 Configuration Options

### Settings Tab Options:

1. **SMTP Settings:**
   - Server address
   - Port (587 for TLS, 465 for SSL)
   - Username/password
   - From/To email addresses

2. **Alert Settings:**
   - Cooldown period (1-30 days)
   - Dashboard URL (for email links)

3. **Test Functions:**
   - Send test email
   - Run manual alert check

## 📊 Alert Tracking

### alert_history.json Structure:
```json
{
  "alerts": [
    {
      "project": "CELLCOM_HR CHATBOT",
      "last_sent": "2026-03-17T10:30:45.123456",
      "count": 3
    }
  ]
}
```

- **project:** Company_ProjectName identifier
- **last_sent:** ISO timestamp of last alert
- **count:** Total alerts sent for this project

## 🔍 Troubleshooting

### Test Email Fails

**"Authentication failed"**
- Use App Password, not regular password
- Gmail: Generate at myaccount.google.com/apppasswords
- Yahoo: Generate at account.yahoo.com/account/security

**"Connection refused"**
- Verify SMTP server and port
- Check firewall allows SMTP connections
- Try port 465 (SSL) if 587 (TLS) fails

**"Sender address rejected"**
- Ensure From Email matches SMTP User
- Some providers require matching addresses

### No Alerts Being Sent

**Possible reasons:**
1. Projects are above their 3-month average (working normally)
2. Projects are in cooldown period (check `alert_history.json`)
3. Projects don't have 3 months of data yet
4. Yesterday's usage is 0 (might be expected)

**To debug:**
- Run manual alert check
- Review "Skipped Alerts" section
- Check `alert_history.json` for cooldown status

## 🎨 Customization Options

### Change Alert Threshold

Edit `modules/email_alerts.py` line 114:

```python
# Current: 3-month daily average
daily_avg_3mo = recent_avg / 30 if recent_avg > 0 else 0

# Option 1: Use 1-month average instead
daily_avg_1mo = row.get('usage_last_30_days', 0) / 30
if yesterday_usage < daily_avg_1mo:

# Option 2: Add percentage threshold (e.g., 50% below)
threshold = daily_avg_3mo * 0.5
if yesterday_usage < threshold:
```

### Customize Email Template

Edit `modules/email_alerts.py` line 123-143 to modify:
- Subject line
- Email body HTML
- Colors and styling
- Button text/URL

### Multiple Recipients

Update `.env`:
```env
ALERT_TO_EMAIL=manager@company.com,ops@company.com,alerts@company.com
```

## 📈 Future Enhancements

Possible improvements:
1. **Scheduled checks:** Daily cron job for automatic alerts
2. **Slack integration:** Send alerts to Slack channels
3. **SMS alerts:** Critical alerts via Twilio
4. **Custom thresholds per project:** Different alert rules
5. **Alert templates:** Multiple email templates
6. **Alert dashboard:** UI to view alert history

## 📚 Additional Documentation

- **Quick Start:** `EMAIL_ALERTS_QUICKSTART.md`
- **Full Guide:** `EMAIL_ALERTS_GUIDE.md`
- **Main README:** `README.md`

## ✨ Key Features

✅ **Smart Detection:** Compares yesterday to 3-month average
✅ **Cooldown System:** Prevents alert fatigue
✅ **Rich Emails:** HTML formatted with project details
✅ **Test Mode:** Test before going live
✅ **Manual Control:** Run checks on demand
✅ **History Tracking:** Full audit trail
✅ **Gmail Ready:** Optimized for Gmail App Passwords
✅ **Customizable:** Easy to modify thresholds and templates

## 🎉 Ready to Use!

Your email alerts system is now fully configured and ready to use. Just:
1. Add your email settings to `.env`
2. Test with "Send Test Email"
3. Run "Alert Check" whenever you want

The system will catch usage drops early and keep your team informed!
