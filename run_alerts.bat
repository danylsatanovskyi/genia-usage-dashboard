@echo off
REM Daily Alert Check - Run this script to check usage and send email alerts
REM This can be scheduled with Windows Task Scheduler

echo ============================================================
echo ROI Dashboard - Daily Alert Check
echo ============================================================
echo.

cd /d C:\Users\danyl\genia-usage-dashboard

echo Running alert check...
python run_daily_alerts.py >> alert_logs.txt 2>&1

echo.
echo Check complete! View results in alert_logs.txt
echo.

REM Uncomment to pause and see output (remove for scheduled tasks)
REM pause
