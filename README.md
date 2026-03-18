# Genia Usage Dashboard

ROI Dashboard for tracking Client Solutions usage and savings, now powered by Supabase!

## Features

- 📊 Real-time usage tracking from Supabase
- 💰 ROI calculations and break-even estimates
- 📈 Monthly trends and analytics
- 🚨 Usage drop alerts
- 📧 Automatic email alerts when usage drops below average
- 🔍 Detailed solution drill-down
- 🎨 Customizable columns and manual project entries

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your Supabase credentials:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
```

**Optional: Email Alerts** (see [Email Alerts Setup](#email-alerts))

```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_FROM_EMAIL=your-email@gmail.com
ALERT_TO_EMAIL=alerts@company.com
```

### 3. Configure Projects

Edit `config.py` to add or modify company/project configurations. Each project needs:

- `supabase_table`: Name of the Supabase table
- `usage_field`: Field name to track (e.g., `queries_sent`)
- `value_type`: Either `"boolean"` (count True values) or `"numeric"` (sum values)
- `investment`: Total project cost
- `monthly_roi_goal`: Monthly savings target
- `hourly_rate`: Client's hourly rate
- `minutes_saved_per_usage`: Time saved per usage instance
- `usage_type`: Description of what's being counted
- `month_activated`: Project start date (YYYY-MM-DD)

### 4. Run the Dashboard

```bash
streamlit run app.py
```

## How It Works

1. **Data Collection**: The app queries Supabase tables configured in `config.py`
2. **Monthly Aggregation**: Records are grouped by month based on the `date` field
3. **Usage Calculation**:
   - For boolean fields: Counts `True` values
   - For numeric fields: Sums the values
4. **Savings Calculation**: `Usage × (Minutes/Use ÷ 60) × Hourly Rate`
5. **ROI Tracking**: Compares cumulative savings vs. investment

## Supabase Table Requirements

Each table must have:
- A `date` field (timestamp/date type)
- A usage tracking field (boolean or numeric)

Example table structure:
```sql
CREATE TABLE genia_analytics_company_project (
    id UUID PRIMARY KEY,
    date TIMESTAMP NOT NULL,
    queries_sent BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Status Legend

- 🟢 **Green**: ROI reached or above monthly target
- 🟡 **Yellow**: On track (70-100% of target)
- 🔴 **Red**: Below target (<70%)
- ⚠️ **Warning**: No usage this month
- 🚨 **Alert**: Usage dropped >50% from historical average
- ⚪ **Inactive**: No usage in last 3 months

## Email Alerts

Get automatic alerts when yesterday's usage drops below the 3-month daily average.

### Quick Setup (5 minutes)

1. **Get Gmail App Password**
   - Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Create password for "ROI Dashboard"
   - Copy the 16-character password

2. **Update .env file** with email settings (see above)

3. **Test in Dashboard**
   - Go to Settings tab → Email Alert Configuration
   - Click "Send Test Email"
   - Verify you received the email

4. **Run Alert Check**
   - Click "Run Alert Check" to manually check all projects
   - Alerts sent when: `yesterday_usage < (3_month_total / 90)`
   - Cooldown: 7 days between alerts per project

**Full Documentation:** See `EMAIL_ALERTS_QUICKSTART.md` and `EMAIL_ALERTS_GUIDE.md`
