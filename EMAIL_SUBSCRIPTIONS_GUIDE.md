# Simple Email Subscriptions - User Guide

## ✨ For Users (Non-Technical)

### How to Get Alerts

1. Open the dashboard
2. Go to the **Settings** tab
3. Find **"Email Alert Subscriptions"** at the top
4. Enter your email address
5. Click **Subscribe**
6. Done! You'll now receive alerts when project usage drops

### What You'll Receive

You'll get an email whenever:
- A project's yesterday usage is below its 3-month average
- Example: If a project usually gets 20 uses/day but yesterday had only 5

### Email Contains:
- Which project has low usage
- Yesterday's number vs. average
- Project details (30-day, 3-month totals)
- Link to view the dashboard

### Unsubscribe

1. Go to Settings → Email Alert Subscriptions
2. Find your email in the list
3. Click **Remove**

---

## 🔧 For Admins (One-Time Setup)

### Initial Configuration

Only needs to be done **once** by the technical person:

1. Get Gmail App Password:
   - Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Create password for "ROI Dashboard"
   - Copy the 16-character password

2. Update `.env` file:
   ```env
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   ALERT_FROM_EMAIL=your-email@gmail.com
   ```

3. Test it:
   - Add yourself as a subscriber
   - Go to Settings → Admin: SMTP Configuration
   - Click "Send Test Email"
   - Verify you receive it

### That's It!

After this setup, **anyone** can subscribe/unsubscribe themselves without touching any technical settings.

---

## 📋 Files

- `alert_subscribers.json` - List of subscribed emails (automatically managed)
- `.env` - SMTP configuration (admin only, not in git)

---

## ❓ FAQ

**Q: Can multiple people subscribe?**  
A: Yes! Unlimited subscribers. All will receive alerts.

**Q: How often do alerts send?**  
A: Only when usage drops below the 3-month average, with a 7-day cooldown per project.

**Q: Do I need to know anything technical to subscribe?**  
A: No! Just enter your email and click Subscribe.

**Q: Who sees my email?**  
A: Only admins can see the subscriber list in the Settings tab.

**Q: Can I change the cooldown period?**  
A: Yes, admins can adjust it in the SMTP Configuration section (1-30 days).

**Q: What if I want to test if it's working?**  
A: Admins can click "Run Alert Check" to manually check all projects and send alerts immediately.

---

## 🎯 Key Benefits

✅ **Simple** - Just enter email, no technical knowledge needed  
✅ **Self-service** - Users can subscribe/unsubscribe themselves  
✅ **Scalable** - Unlimited subscribers  
✅ **Smart** - Only alerts when there's actually a problem  
✅ **No spam** - 7-day cooldown prevents alert fatigue  
✅ **Rich info** - Emails include all project details  
