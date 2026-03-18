# Email Alerts - Quick Reference

## 🎯 Alert Condition
```
yesterday_usage < (3_month_total / 90)
```

## ⚡ Quick Setup
1. Get Gmail App Password → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Add to `.env`:
   ```
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   ALERT_FROM_EMAIL=your@gmail.com
   ALERT_TO_EMAIL=alerts@company.com
   ```
3. Test: Settings → Email Alert Configuration → Send Test Email
4. Use: Settings → Email Alert Configuration → Run Alert Check

## 📋 Files
- `modules/email_alerts.py` - Logic
- `alert_history.json` - Tracking
- `.env` - Config (not in git)

## 🔧 Settings Tab
Location: **Settings → Email Alert Configuration**

**Actions:**
- Send Test Email - Verify SMTP config
- Run Alert Check - Manually check all projects

**Config:**
- SMTP settings (server, port, credentials)
- Cooldown period (default: 7 days)
- Dashboard URL (for email links)

## 📧 Email Contains
- Project name (Company - Project)
- Yesterday's usage vs 3-month avg
- Last 30d, 3mo totals
- ROI status
- Dashboard link

## 🔍 Troubleshooting
| Problem | Solution |
|---------|----------|
| Auth failed | Use App Password, not regular password |
| Connection refused | Check firewall, verify server/port |
| No alerts sent | Check if below threshold & not in cooldown |
| Reset history | Delete `alert_history.json` |

## 📚 Documentation
- **Quick Start:** `EMAIL_ALERTS_QUICKSTART.md`
- **Full Guide:** `EMAIL_ALERTS_GUIDE.md`
- **Implementation:** `EMAIL_ALERTS_IMPLEMENTATION.md`

## ✨ Features
✅ Compares yesterday to 3-month average  
✅ 7-day cooldown prevents spam  
✅ Rich HTML emails  
✅ Test mode  
✅ Manual & auto checks  
✅ Full history tracking  
