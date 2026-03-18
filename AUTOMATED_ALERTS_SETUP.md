# Automatic Daily Email Alerts Setup

## Overview

There are **two ways** to automatically send daily email alerts:

1. **Windows Task Scheduler** (Recommended) - Runs script once per day
2. **Background Service** - Continuously running inside Streamlit

---

## Option 1: Windows Task Scheduler (Recommended)

### ✅ **Pros:**
- Clean separation from dashboard
- Runs even if dashboard is closed
- Easy to monitor and troubleshoot
- Standard Windows solution

### **Setup Instructions:**

#### 1. Test the Script First

Open PowerShell and run:
```powershell
cd C:\Users\danyl\genia-usage-dashboard
python run_daily_alerts.py
```

You should see output like:
```
============================================================
Daily Alert Check - 2026-03-18 23:59:00
============================================================

✅ Connected to Supabase
📊 Loading project data...
   Found 5 projects
📧 Subscribers: 2
   - alice@company.com
   - bob@company.com

🔍 Checking for usage drops...

============================================================
✅ NO ALERTS NEEDED - All projects performing normally
============================================================
```

#### 2. Create Batch File

Create `run_alerts.bat` in your project folder:

```batch
@echo off
cd /d C:\Users\danyl\genia-usage-dashboard
python run_daily_alerts.py >> alert_logs.txt 2>&1
```

This will run the script and save logs to `alert_logs.txt`.

#### 3. Open Task Scheduler

1. Press `Win + R`
2. Type `taskschd.msc`
3. Press Enter

#### 4. Create New Task

1. Click **"Create Task"** (not "Create Basic Task")
2. **General Tab:**
   - Name: `ROI Dashboard Daily Alerts`
   - Description: `Check for usage drops and send email alerts`
   - Run whether user is logged on or not: ☑️
   - Run with highest privileges: ☑️

3. **Triggers Tab:**
   - Click **"New"**
   - Begin the task: `On a schedule`
   - Settings: `Daily`
   - Start: `11:59 PM` (or your preferred time)
   - Enabled: ☑️

4. **Actions Tab:**
   - Click **"New"**
   - Action: `Start a program`
   - Program/script: `C:\Users\danyl\genia-usage-dashboard\run_alerts.bat`
   - Start in: `C:\Users\danyl\genia-usage-dashboard`

5. **Conditions Tab:**
   - Uncheck: `Start the task only if the computer is on AC power`
   - Check: `Wake the computer to run this task` (optional)

6. **Settings Tab:**
   - Allow task to be run on demand: ☑️
   - If task fails, restart every: `10 minutes`
   - Attempt to restart up to: `3 times`

7. Click **OK** and enter your Windows password

#### 5. Test the Scheduled Task

Right-click the task → **Run**

Check `alert_logs.txt` for output.

---

## Option 2: Background Service in Streamlit

### ✅ **Pros:**
- No Task Scheduler needed
- Runs automatically with dashboard
- Simple deployment

### ❌ **Cons:**
- Dashboard must be running 24/7
- Uses more resources

### **Setup:**

I can add a background thread to `app.py` that:
1. Checks the time every minute
2. At 11:59 PM, runs the alert check
3. Logs results to console

Would you like me to implement this option?

---

## Environment Variables

Add to your `.env` file (optional, for customization):

```env
# Alert Configuration (optional)
ALERT_COOLDOWN_DAYS=7
DASHBOARD_URL=http://localhost:8501

# Timezone (optional, if you want specific timezone)
TIMEZONE=America/New_York
```

---

## Recommended Schedule

**Best time to run:** `11:59 PM` or `12:01 AM`

**Why:** 
- Ensures "yesterday" is a complete day
- Won't interfere with business hours
- Alerts arrive first thing in the morning

**Alternative schedules:**
- `8:00 AM` - Morning alerts (checks previous day)
- `9:00 PM` - Evening alerts (checks same day)

---

## Monitoring

### View Logs

```powershell
# View recent logs
Get-Content alert_logs.txt -Tail 50

# View today's logs
Select-String -Path alert_logs.txt -Pattern (Get-Date -Format "yyyy-MM-dd")

# Clear old logs
Clear-Content alert_logs.txt
```

### Check Last Run

In Task Scheduler:
1. Find your task
2. Check **"Last Run Time"** and **"Last Run Result"**
3. `0x0` = Success

---

## Troubleshooting

### Task doesn't run

**Check:**
1. Task is **Enabled**
2. Trigger time is correct
3. User has permissions
4. Check Task History (View → Show Task History)

### Script errors

**Check `alert_logs.txt` for errors:**
```powershell
Get-Content alert_logs.txt -Tail 20
```

Common issues:
- Missing `.env` file
- Wrong Python path
- Missing dependencies

### No emails sent

**Check:**
1. Subscribers configured? (dashboard → Settings)
2. SMTP settings correct? (test with dashboard first)
3. Projects below threshold? (check logs)
4. Cooldown period? (check `alert_history.json`)

---

## What I Recommend

**For You (Windows, Local):**
1. Use **Windows Task Scheduler**
2. Schedule for **11:59 PM** daily
3. Monitor `alert_logs.txt` weekly

**For Production (Cloud):**
- Deploy to **Streamlit Cloud** or **AWS/Azure**
- Use their built-in schedulers (CloudWatch Events, Azure Functions, etc.)

---

## Testing

To manually test the daily check:

```powershell
# Test now
python run_daily_alerts.py

# Or run the batch file
.\run_alerts.bat

# Check output
Get-Content alert_logs.txt -Tail 50
```

---

## Next Steps

1. Test `run_daily_alerts.py` manually first
2. Set up Task Scheduler
3. Test the scheduled task (right-click → Run)
4. Check logs to verify it worked
5. Let it run automatically!

---

Need help with any step? Let me know!
