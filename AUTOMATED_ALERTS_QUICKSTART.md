# Quick Start: Automated Daily Alerts

## 🚀 5-Minute Setup

### Step 1: Test It Works
```powershell
cd C:\Users\danyl\genia-usage-dashboard
python run_daily_alerts.py
```

You should see output showing the check ran successfully.

---

### Step 2: Create Scheduled Task

**Option A: Quick Setup (PowerShell)**

Run this in PowerShell (as Administrator):

```powershell
# Create scheduled task to run daily at 11:59 PM
$action = New-ScheduledTaskAction -Execute "C:\Users\danyl\genia-usage-dashboard\run_alerts.bat" -WorkingDirectory "C:\Users\danyl\genia-usage-dashboard"
$trigger = New-ScheduledTaskTrigger -Daily -At "11:59PM"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "ROI Dashboard Alerts" -Action $action -Trigger $trigger -Settings $settings -Description "Daily usage alert check"
```

**Option B: Manual Setup (GUI)**

See `AUTOMATED_ALERTS_SETUP.md` for detailed Task Scheduler instructions.

---

### Step 3: Test the Scheduled Task

```powershell
# Run it now to test
Start-ScheduledTask -TaskName "ROI Dashboard Alerts"

# Check if it worked
Get-Content alert_logs.txt -Tail 20
```

---

### Step 4: Done!

The script will now run **automatically every day at 11:59 PM** and:
- ✅ Check all projects
- ✅ Send emails to subscribers if usage dropped
- ✅ Log results to `alert_logs.txt`

---

## 📋 What Time Should I Schedule It?

**Recommended: 11:59 PM**
- Ensures "yesterday" is a complete day
- Alerts arrive in morning inboxes

**Alternative times:**
- `12:01 AM` - Right after midnight
- `8:00 AM` - Morning check (previous day)

---

## 🔍 Check Logs

```powershell
# View recent activity
Get-Content alert_logs.txt -Tail 50

# View today's runs
Select-String -Path alert_logs.txt -Pattern (Get-Date -Format "yyyy-MM-dd")
```

---

## ⚙️ Change Schedule Time

**PowerShell:**
```powershell
Set-ScheduledTask -TaskName "ROI Dashboard Alerts" -Trigger (New-ScheduledTaskTrigger -Daily -At "8:00AM")
```

**Or:** Open Task Scheduler → Find task → Right-click → Properties → Triggers

---

## 🛑 Disable/Enable

```powershell
# Disable
Disable-ScheduledTask -TaskName "ROI Dashboard Alerts"

# Enable
Enable-ScheduledTask -TaskName "ROI Dashboard Alerts"

# Remove completely
Unregister-ScheduledTask -TaskName "ROI Dashboard Alerts"
```

---

## ❓ Troubleshooting

**Alerts not sending?**
1. Check subscribers: Dashboard → Settings → Email Subscriptions
2. Check SMTP config in `.env`
3. View logs: `Get-Content alert_logs.txt -Tail 50`

**Task not running?**
1. Open Task Scheduler (`taskschd.msc`)
2. Find "ROI Dashboard Alerts"
3. Check "Last Run Result" (0x0 = success)
4. Right-click → Run to test manually

---

## 📧 How It Works

Every day at the scheduled time:
1. Loads all project data from Supabase
2. Calculates yesterday's usage for each project
3. Compares to 3-month average
4. Sends email to ALL subscribers if below threshold
5. Logs results

**Email sent when:** `yesterday_usage < (3_month_total / 90)`

---

That's it! Your alerts are now automated. 🎉
