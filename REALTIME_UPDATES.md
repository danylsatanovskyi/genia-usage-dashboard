# Real-Time Dashboard Updates

Your dashboard now supports real-time updates from Supabase!

## Features

### 1. **Auto-Refresh Mode**
Automatically refreshes data from Supabase at regular intervals.

**How to use:**
1. Look in the sidebar for "Auto-Refresh" section
2. Check "Enable Auto-Refresh"
3. Set your refresh interval (10-300 seconds)
4. Watch the countdown timer
5. Dashboard automatically refreshes when timer hits 0

**What happens:**
- Clears the data cache
- Re-queries Supabase for latest usage data
- Re-reads Excel metadata
- Updates all charts and tables

### 2. **Manual Refresh Button**
Instantly refresh data whenever you want.

**How to use:**
1. Click the "🔄 Refresh Now" button in the sidebar
2. Data immediately refreshes from Supabase

### 3. **Last Updated Timestamp**
Shows when data was last refreshed.

**Location:** Bottom of the Auto-Refresh section in sidebar

## Use Cases

### Quick Updates (10-30 seconds)
Perfect for demos or when actively monitoring usage:
- Set interval to 10-30 seconds
- Dashboard updates almost in real-time
- Great for presentations

### Regular Monitoring (60-120 seconds)
Balanced approach for daily use:
- Set interval to 60-120 seconds
- Minimal resource usage
- Stays current without overwhelming Supabase

### Periodic Updates (5 minutes)
For background monitoring:
- Set interval to 300 seconds
- Very light on resources
- Dashboard updates periodically

### Manual Only
For on-demand updates:
- Keep auto-refresh disabled
- Click "Refresh Now" when needed
- Most efficient for resource usage

## Technical Details

**What gets refreshed:**
- All Supabase usage data (queries, events, etc.)
- Monthly aggregations
- All calculated metrics (ROI, savings, etc.)

**What doesn't change:**
- Excel metadata (Investment, ROI goals, etc.)
- Custom columns configuration
- Filter selections
- Visible columns settings

**Performance:**
- Uses Streamlit's cache system
- Cache is cleared on each refresh
- Only queries changed data from Supabase
- Excel file is cached separately

## Tips

- **During demos:** Use 10-30 second intervals
- **Daily work:** Use 60-120 second intervals
- **Background dashboards:** Use 300 second intervals
- **On-demand:** Disable auto-refresh, use manual button

The countdown timer shows you exactly when the next refresh will happen!
