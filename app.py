"""
ROI Dashboard - Client Solutions Usage & Savings Tracker
Reads from Supabase with CLIENT, PROJECT, Investment, and monthly usage/savings columns
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
from supabase import create_client, Client
import os
import json
import time
from config import SUPABASE_URL, SUPABASE_KEY, COMPANY_CONFIGS

# Page config
st.set_page_config(
    page_title="Client Solutions ROI Dashboard",
    page_icon="📊",
    layout="wide"
)

# Constants
MONTHS_FR = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 
             'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']
MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June',
             'July', 'August', 'September', 'October', 'November', 'December']
CUSTOM_COLUMNS_FILE = 'custom_columns_config.json'
CUSTOM_PROJECTS_FILE = 'custom_projects.json'

# Initialize Supabase client
@st.cache_resource
def get_supabase_client():
    """Initialize and cache Supabase client"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_KEY environment variables.")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# Custom columns management
def load_custom_columns_config():
    """Load custom columns configuration"""
    if os.path.exists(CUSTOM_COLUMNS_FILE):
        with open(CUSTOM_COLUMNS_FILE, 'r') as f:
            return json.load(f)
    return {
        "data_columns": {},
        "calculated_columns": {},
        "visible_columns": [
            "CLIENT", "PROJECT", "Month Activated", "Investment",
            "usage_last_30_days", "time_saved_hours_30d",
            "Monthly ROI Goal", "cost_saved_30d", "roi_goal_achieved",
            "cumulative_cost_saved", "roi_reached", "roi_status"
        ]
    }

def save_custom_columns_config(config):
    """Save custom columns configuration"""
    with open(CUSTOM_COLUMNS_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def add_custom_data_columns(df, config):
    """Add custom data columns to dataframe"""
    data_columns = config.get('data_columns', {})
    
    for col_name, col_config in data_columns.items():
        # Create column with default value for each project
        default_value = col_config.get('default_value', '')
        df[col_name] = df.apply(
            lambda row: col_config.get('values', {}).get(
                f"{row['COMPANY']}_{row['PROJECT']}", default_value
            ), 
            axis=1
        )
    
    return df

def add_custom_calculated_columns(df, config):
    """Add custom calculated columns to dataframe"""
    calc_columns = config.get('calculated_columns', {})
    
    for col_name, formula in calc_columns.items():
        try:
            # Safe eval with limited scope
            df[col_name] = df.eval(formula, engine='python')
        except Exception as e:
            st.warning(f"Error calculating column '{col_name}': {e}")
            df[col_name] = None
    
    return df

def load_custom_projects():
    """Load custom projects configuration"""
    if os.path.exists(CUSTOM_PROJECTS_FILE):
        with open(CUSTOM_PROJECTS_FILE, 'r') as f:
            return json.load(f)
    return {"custom_projects": []}

def save_custom_projects(projects_config):
    """Save custom projects configuration"""
    with open(CUSTOM_PROJECTS_FILE, 'w') as f:
        json.dump(projects_config, f, indent=2)

def add_custom_projects_to_data(df):
    """Add manually created custom projects to the dataframe"""
    custom_projects_config = load_custom_projects()
    custom_projects = custom_projects_config.get('custom_projects', [])
    
    if not custom_projects:
        return df
    
    # Convert custom projects to dataframe rows
    for project in custom_projects:
        project_row = {
            'COMPANY': project.get('company', 'Custom'),
            'CLIENT': project.get('client', project.get('company', 'Custom')),
            'PROJECT': project.get('project_name', 'Unnamed Project'),
            'Investment': project.get('investment'),
            'Monthly ROI Goal': project.get('monthly_roi_goal'),
            'Client Hourly Rate': project.get('hourly_rate'),
            'Minutes Saved per usage': project.get('minutes_saved'),
            'Month Activated': project.get('month_activated'),
            'Usage Type': project.get('usage_type'),
            'Months Active': None
        }
        
        # Add monthly usage data (from manual input or zeros)
        for month in MONTHS_FR:
            project_row[month] = project.get('monthly_usage', {}).get(month, 0)
        
        # Add to dataframe
        df = pd.concat([df, pd.DataFrame([project_row])], ignore_index=True)
    
    return df

@st.cache_data
def load_excel_metadata():
    """Load project metadata from Excel file"""
    try:
        excel_file = 'data.xlsx'
        metadata_dict = {}
        
        # Read each sheet
        company_sheets = ['HEMA-QUEBEC', 'CELLCOM', 'SERIE CONSEIL', 'TECHO BLOC', 'DIGITAD', 'RETROMTL', 'CHEMTECH']
        
        for sheet_name in company_sheets:
            try:
                # Read the sheet with header at row 2 (0-indexed)
                df = pd.read_excel(excel_file, sheet_name=sheet_name, header=2)
                
                # Clean up column names
                df.columns = df.columns.str.strip()
                
                # Forward-fill CLIENT column
                df['CLIENT'] = df['CLIENT'].ffill()
                
                # Filter valid projects
                df = df[df['PROJECT'].notna() & (df['PROJECT'] != '')]
                
                # Remove header rows and invalid projects
                exclude_projects = ['TYPE D\'ECONOMIE', 'PROJET', 'TOTAL', 'SCREENSHOT FOR EMAIL']
                df = df[~df['PROJECT'].isin(exclude_projects)]
                df = df[~df['PROJECT'].str.contains('🔍|⚙️|💰', na=False)]
                
                # Extract metadata for each project
                for _, row in df.iterrows():
                    project_key = f"{sheet_name}_{row['PROJECT']}"
                    
                    # Clean currency columns
                    investment = pd.to_numeric(str(row.get('Investment', '')).replace('$', '').replace(',', ''), errors='coerce')
                    monthly_roi = pd.to_numeric(str(row.get('Monthly ROI Goal', '')).replace('$', '').replace(',', ''), errors='coerce')
                    hourly_rate = pd.to_numeric(str(row.get('Client Hourly Rate', '')).replace('$', '').replace(',', ''), errors='coerce')
                    minutes_saved = pd.to_numeric(row.get('Minutes Saved per usage', ''), errors='coerce')
                    
                    metadata_dict[project_key] = {
                        'Investment': investment if pd.notna(investment) else None,
                        'Monthly ROI Goal': monthly_roi if pd.notna(monthly_roi) else None,
                        'Client Hourly Rate': hourly_rate if pd.notna(hourly_rate) else None,
                        'Minutes Saved per usage': minutes_saved if pd.notna(minutes_saved) else None,
                        'Month Activated': row.get('Month Activated'),
                        'Usage Type': row.get('Usage Type'),
                        'Months Active': row.get('Months Active')
                    }
            except Exception as e:
                st.warning(f"Could not read metadata from sheet {sheet_name}: {e}")
                continue
        
        return metadata_dict
    except Exception as e:
        st.error(f"Error loading Excel metadata: {e}")
        return {}

@st.cache_data
def load_data():
    """Load data from Supabase - aggregate usage by month for each project"""
    supabase = get_supabase_client()
    if not supabase:
        return pd.DataFrame()
    
    # Load metadata from Excel
    excel_metadata = load_excel_metadata()
    
    all_data = []
    
    for company_name, company_config in COMPANY_CONFIGS.items():
        for project_name, project_config in company_config['projects'].items():
            try:
                # Query data from Supabase
                table_name = project_config['supabase_table']
                usage_field = project_config['usage_field']
                value_type = project_config['value_type']
                
                # Fetch all records from the table
                response = supabase.table(table_name).select("*").execute()
                
                if not response.data:
                    st.warning(f"No data found for {company_name} - {project_name}")
                    continue
                
                # Convert to DataFrame
                records_df = pd.DataFrame(response.data)
                
                # Ensure 'created_at' column exists and convert to datetime
                if 'created_at' not in records_df.columns:
                    st.error(f"'created_at' column not found in {table_name}")
                    continue
                
                records_df['created_at'] = pd.to_datetime(records_df['created_at'], errors='coerce')
                records_df = records_df[records_df['created_at'].notna()]
                
                # Extract month and year
                records_df['month'] = records_df['created_at'].dt.month
                records_df['year'] = records_df['created_at'].dt.year
                
                # Aggregate by month
                monthly_usage = {}
                for month_idx in range(12):
                    month_name = MONTHS_FR[month_idx]
                    
                    # Filter records for this month (across all years, or just current year)
                    # Using 2025-2026 data (Jan 2025 = Janvier, Feb 2026 = Fevrier, etc.)
                    if month_idx >= 0:  # January onwards
                        month_records = records_df[
                            ((records_df['month'] == month_idx + 1) & (records_df['year'] == 2025)) |
                            ((records_df['month'] == month_idx + 1) & (records_df['year'] == 2026))
                        ]
                    
                    # Calculate usage based on value_type
                    if value_type == "boolean":
                        # Count how many times the field is True
                        if usage_field in month_records.columns:
                            usage_count = month_records[usage_field].sum() if month_records[usage_field].dtype == bool else len(month_records[month_records[usage_field] == True])
                        else:
                            usage_count = 0
                    else:  # numeric
                        # Sum the numeric values
                        if usage_field in month_records.columns:
                            usage_count = month_records[usage_field].sum()
                        else:
                            usage_count = 0
                    
                    monthly_usage[month_name] = usage_count
                
                # Get metadata from Excel (if available)
                project_key = f"{company_name}_{project_name}"
                metadata = excel_metadata.get(project_key, {})
                
                # Hardcoded overrides for specific projects (if Excel has errors)
                usage_type_override = None
                if company_name == "TECHO BLOC" and project_name == "MATCHING":
                    usage_type_override = "Matched Companies"
                
                # Create row for this project - use Excel metadata
                project_row = {
                    'COMPANY': company_name,
                    'CLIENT': company_config.get('client_name', company_name),
                    'PROJECT': project_name,
                    'Investment': metadata.get('Investment'),
                    'Monthly ROI Goal': metadata.get('Monthly ROI Goal'),
                    'Client Hourly Rate': metadata.get('Client Hourly Rate'),
                    'Minutes Saved per usage': metadata.get('Minutes Saved per usage'),
                    'Month Activated': metadata.get('Month Activated'),
                    'Usage Type': usage_type_override if usage_type_override else metadata.get('Usage Type'),
                    'Months Active': metadata.get('Months Active')
                }
                
                # Add monthly usage data
                project_row.update(monthly_usage)
                
                all_data.append(project_row)
                
            except Exception as e:
                st.error(f"Error fetching data for {company_name} - {project_name}: {e}")
                import traceback
                st.text(traceback.format_exc())
                continue
    
    if all_data:
        combined_df = pd.DataFrame(all_data)
        return combined_df
    else:
        return pd.DataFrame()

def calculate_metrics(df):
    """Calculate usage, savings, and ROI metrics"""
    
    if df.empty:
        return df
    
    # Get current month index (February 2026 = index 1)
    current_month_idx = datetime.now().month - 1  # 0-indexed
    
    # Calculate usage for each timeframe
    df['usage_last_30_days'] = df[MONTHS_FR[current_month_idx]] if current_month_idx < 12 else 0
    
    # Last 3 months usage
    month_cols_3mo = []
    for i in range(3):
        month_idx = (current_month_idx - i) % 12
        if MONTHS_FR[month_idx] in df.columns:
            month_cols_3mo.append(MONTHS_FR[month_idx])
    df['usage_last_3_months'] = df[month_cols_3mo].sum(axis=1) if month_cols_3mo else 0
    
    # Last 12 months usage (all available months)
    available_months = [m for m in MONTHS_FR if m in df.columns]
    df['usage_last_12_months'] = df[available_months].sum(axis=1) if available_months else 0
    
    # Historical average (first 6 months of data vs last 3 months)
    # Get first 6 non-zero months for historical baseline
    def get_historical_avg(row):
        usage_values = [row[m] for m in available_months if pd.notna(row[m]) and row[m] > 0]
        if len(usage_values) >= 6:
            return np.mean(usage_values[:6])  # First 6 active months
        elif len(usage_values) > 0:
            return np.mean(usage_values)
        return 0
    
    df['historical_monthly_avg'] = df.apply(get_historical_avg, axis=1)
    df['recent_monthly_avg'] = df['usage_last_3_months'] / 3
    
    # Calculate drop percentage
    df['usage_drop_percent'] = ((df['historical_monthly_avg'] - df['recent_monthly_avg']) / 
                                 (df['historical_monthly_avg'] + 0.01) * 100)
    
    # MoM change
    prev_month_idx = (current_month_idx - 1) % 12
    if MONTHS_FR[prev_month_idx] in df.columns and MONTHS_FR[current_month_idx] in df.columns:
        df['usage_prev_month'] = df[MONTHS_FR[prev_month_idx]]
        df['mom_usage_percent'] = ((df['usage_last_30_days'] - df['usage_prev_month']) / 
                                    (df['usage_prev_month'] + 0.01) * 100)
    else:
        df['usage_prev_month'] = 0
        df['mom_usage_percent'] = 0
    
    # Average monthly usage (last 3 months)
    df['trailing_3mo_monthly_avg_usage'] = df['usage_last_3_months'] / 3
    
    # Time saved (hours) - handle None values
    minutes_saved = df['Minutes Saved per usage'].fillna(0)
    df['time_saved_hours_30d'] = df['usage_last_30_days'] * minutes_saved / 60
    df['time_saved_hours_3mo'] = df['usage_last_3_months'] * minutes_saved / 60
    df['time_saved_hours_12mo'] = df['usage_last_12_months'] * minutes_saved / 60
    
    # Cost saved ($) - handle None values
    hourly_rate = df['Client Hourly Rate'].fillna(0)
    df['cost_saved_30d'] = df['time_saved_hours_30d'] * hourly_rate
    df['cost_saved_3mo'] = df['time_saved_hours_3mo'] * hourly_rate
    df['cost_saved_12mo'] = df['time_saved_hours_12mo'] * hourly_rate
    df['cumulative_cost_saved'] = df['cost_saved_12mo']
    
    # ROI tracking - handle None values
    project_cost = df['Investment'].fillna(0)
    df['project_cost'] = project_cost
    df['roi_net'] = df['cumulative_cost_saved'] - df['project_cost']
    df['roi_reached'] = (df['project_cost'] > 0) & (df['roi_net'] >= 0)
    df['roi_progress_percent'] = ((df['cumulative_cost_saved'] / (df['project_cost'] + 0.01) * 100).clip(upper=200)).fillna(0)
    
    # ROI status badge with alerts - handle None values
    monthly_target = df['Monthly ROI Goal'].fillna(0)
    
    def get_status(row):
        # If no financial config, just report usage status
        if row['project_cost'] == 0 or monthly_target[row.name] == 0:
            if row['usage_last_30_days'] == 0 and row['usage_last_3_months'] == 0:
                return 'Inactive'
            elif row['usage_last_30_days'] == 0:
                return 'No Recent Usage'
            elif row['usage_drop_percent'] > 50 and row['historical_monthly_avg'] > 5:
                return 'Usage Dropped'
            else:
                return 'Active (Config Needed)'
        
        # Check for major usage drop (>50% from historical)
        if row['usage_drop_percent'] > 50 and row['historical_monthly_avg'] > 5:
            return 'Usage Dropped'
        elif row['usage_last_30_days'] == 0 and row['usage_last_3_months'] == 0:
            return 'Inactive'
        elif row['usage_last_30_days'] == 0:
            return 'No Recent Usage'
        elif row['roi_reached']:
            return 'ROI Reached'
        elif row['cost_saved_30d'] >= monthly_target[row.name]:
            return 'Above Target'
        elif row['cost_saved_30d'] >= monthly_target[row.name] * 0.7:
            return 'On Track'
        else:
            return 'Below Target'
    
    df['roi_status'] = df.apply(get_status, axis=1)
    
    # Add status color for styling
    def get_status_color(status):
        if 'Dropped' in status or 'Inactive' in status:
            return 'darkred'
        elif 'No Recent' in status:
            return 'orange'
        elif 'ROI Reached' in status or 'Above Target' in status:
            return 'green'
        elif 'On Track' in status:
            return 'orange'
        elif 'Below Target' in status:
            return 'red'
        return 'gray'
    
    df['status_color'] = df['roi_status'].apply(get_status_color)
    
    # Enhanced break-even estimate
    def estimate_breakeven(row):
        if row['roi_reached']:
            return "ROI Reached"
        if row['cost_saved_3mo'] <= 0:
            if row['usage_last_12_months'] > 0:
                return "Was active, now inactive"
            else:
                return "Never used"
        monthly_avg = row['cost_saved_3mo'] / 3
        
        # Check if usage is extremely low
        if monthly_avg < 10 and row['historical_monthly_avg'] > monthly_avg * 10:
            return f"~{((row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg):.0f} months (project appears abandoned)"
        elif monthly_avg < 50:
            return f"{((row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg):.0f} months (very low usage)"
        
        months_to_break_even = (row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg
        if months_to_break_even > 100:
            return f"{months_to_break_even:.0f} months (needs attention)"
        elif months_to_break_even > 24:
            return f"{months_to_break_even:.1f} months"
        else:
            return f"{months_to_break_even:.1f} months"
    
    df['breakeven_estimate'] = df.apply(estimate_breakeven, axis=1)
    
    return df

def main():
    st.title("Client Solutions ROI & Adoption Dashboard")
    
    # Manual refresh button in sidebar
    with st.sidebar:
        st.markdown("---")
        
        # Manual refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        # Show last refresh time
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = time.time()
        
        last_refresh_time = datetime.fromtimestamp(st.session_state.last_refresh)
        st.caption(f"📅 Last updated: {last_refresh_time.strftime('%H:%M:%S')}")
    
    st.markdown("---")
    
    # Load data
    with st.spinner("Loading data from Supabase..."):
        df = load_data()
    
    if df.empty:
        st.error("No data found in Supabase. Please check your configuration and database.")
        return
    
    # Add custom projects (manual entries)
    df = add_custom_projects_to_data(df)
    
    # Calculate metrics
    df_metrics = calculate_metrics(df)
    
    # Add custom columns
    custom_config = load_custom_columns_config()
    df_metrics = add_custom_data_columns(df_metrics, custom_config)
    df_metrics = add_custom_calculated_columns(df_metrics, custom_config)
    
    # Sidebar - Filters
    st.sidebar.header("Filters")
    
    companies = ['All'] + sorted(df_metrics['COMPANY'].unique().tolist())
    selected_company = st.sidebar.selectbox("Filter by Company", companies)
    
    clients = ['All'] + sorted(df_metrics['CLIENT'].dropna().unique().tolist())
    selected_client = st.sidebar.selectbox("Filter by Client", clients)
    
    status_options = ['All'] + sorted(df_metrics['roi_status'].unique().tolist())
    selected_status = st.sidebar.selectbox("Filter by ROI Status", status_options)
    
    # Apply filters
    filtered_df = df_metrics.copy()
    if selected_company != 'All':
        filtered_df = filtered_df[filtered_df['COMPANY'] == selected_company]
    if selected_client != 'All':
        filtered_df = filtered_df[filtered_df['CLIENT'] == selected_client]
    if selected_status != 'All':
        filtered_df = filtered_df[filtered_df['roi_status'] == selected_status]
    
    # Top metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric(
            "Total Solutions", 
            len(filtered_df),
            help="Number of solutions tracked"
        )
    
    with col2:
        total_hours = filtered_df['time_saved_hours_12mo'].sum()
        st.metric(
            "Hours Saved (12mo)", 
            f"{total_hours:,.0f}h",
            help="Total hours saved across all solutions"
        )
    
    with col3:
        total_savings = filtered_df['cost_saved_12mo'].sum()
        st.metric(
            "Total Savings (12mo)", 
            f"${total_savings:,.0f}",
            help="Total cost savings across all solutions"
        )
    
    with col4:
        total_investment = filtered_df['project_cost'].sum()
        st.metric(
            "Total Investment", 
            f"${total_investment:,.0f}",
            help="Total project costs"
        )
    
    with col5:
        roi_reached_count = filtered_df['roi_reached'].sum()
        st.metric(
            "ROI Reached", 
            f"{roi_reached_count} / {len(filtered_df)}",
            help="Solutions that have reached ROI"
        )
    
    with col6:
        # Count projects needing attention
        needs_attention = len(filtered_df[
            (filtered_df['roi_status'].str.contains('Dropped|Inactive|No Recent', na=False))
        ])
        st.metric(
            "Needs Attention",
            needs_attention,
            help="Projects with usage drops or inactive"
        )
    
    # Alert section for projects needing attention
    if needs_attention > 0:
        st.warning(f"**{needs_attention} project(s) need attention!**")
        alert_df = filtered_df[
            filtered_df['roi_status'].str.contains('Dropped|Inactive|No Recent', na=False)
        ][['CLIENT', 'PROJECT', 'roi_status', 'historical_monthly_avg', 'recent_monthly_avg', 'usage_drop_percent']]
        
        st.markdown("### Projects Requiring Immediate Attention")
        for _, row in alert_df.iterrows():
            with st.expander(f"{row['CLIENT']} - {row['PROJECT']}", expanded=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Status", row['roi_status'])
                with col2:
                    st.metric("Was Averaging", f"{row['historical_monthly_avg']:.1f}/mo")
                with col3:
                    st.metric("Now Averaging", f"{row['recent_monthly_avg']:.1f}/mo", 
                             delta=f"-{row['usage_drop_percent']:.0f}%" if row['usage_drop_percent'] > 0 else f"{row['usage_drop_percent']:.0f}%")
                
                if row['usage_drop_percent'] > 50:
                    st.error(f"Usage has dropped by {row['usage_drop_percent']:.0f}% from historical average")
        
        st.markdown("---")
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Portfolio Overview", "Analytics", "Solution Details", "Settings"])
    
    with tab1:
        st.subheader("Portfolio Overview")
        
        # Sort options
        sort_col1, sort_col2 = st.columns([2, 1])
        with sort_col1:
            sort_by = st.selectbox(
                "Sort by",
                ['usage_last_30_days', 'cost_saved_30d', 'roi_progress_percent', 'mom_usage_percent'],
                format_func=lambda x: {
                    'usage_last_30_days': 'Usage (Last 30d)',
                    'cost_saved_30d': 'Savings (Last 30d)',
                    'roi_progress_percent': 'ROI Progress %',
                    'mom_usage_percent': 'MoM Change %'
                }[x]
            )
        with sort_col2:
            sort_order = st.radio("Order", ['Descending', 'Ascending'], horizontal=True)
        
        # Sort dataframe - first by COMPANY, then by selected column
        ascending = sort_order == 'Ascending'
        display_df = filtered_df.sort_values(by=['COMPANY', sort_by], ascending=[True, ascending])
        
        # Display table with better formatting
        # Get custom column config
        custom_config = load_custom_columns_config()
        columns_to_display = custom_config.get('visible_columns', [
            'CLIENT', 'PROJECT', 'Month Activated', 'Investment',
            'Usage Type',
            'usage_last_30_days', 'usage_last_3_months', 'usage_last_12_months',
            'time_saved_hours_30d',
            'Monthly ROI Goal', 'cost_saved_30d', 'roi_goal_achieved',
            'cumulative_cost_saved', 'roi_reached',
            'roi_status'
        ])
        
        # Add a column to check if monthly ROI goal was achieved
        display_df['roi_goal_achieved'] = display_df.apply(
            lambda row: 'Yes' if (pd.notna(row.get('Monthly ROI Goal')) and 
                                  pd.notna(row['cost_saved_30d']) and 
                                  row['cost_saved_30d'] >= row.get('Monthly ROI Goal', 0)) 
            else 'N/A' if pd.isna(row.get('Monthly ROI Goal')) else 'No', axis=1
        )
        
        # Add a column to show if overall ROI is reached
        display_df['roi_reached_display'] = display_df['roi_reached'].apply(
            lambda x: 'Yes' if x else 'No'
        )
        
        # Filter only existing columns
        columns_to_display = [col for col in columns_to_display if col in display_df.columns]
        
        display_table = display_df[columns_to_display].copy()
        
        # Add the display column
        if 'roi_reached' in display_table.columns:
            display_table['roi_reached'] = display_df['roi_reached_display']
        
        # Rename for display
        rename_dict = {
            'CLIENT': 'Client', 
            'PROJECT': 'Project',
            'Month Activated': 'Activated',
            'Investment': 'Investment',
            'Usage Type': 'What We Count',
            'usage_last_30_days': 'Usage (30d)',
            'usage_last_3_months': 'Usage (3mo)',
            'usage_last_12_months': 'Usage (12mo)',
            'time_saved_hours_30d': 'Hours Saved (30d)',
            'time_saved_hours_3mo': 'Hours Saved (3mo)',
            'time_saved_hours_12mo': 'Hours Saved (12mo)',
            'Monthly ROI Goal': 'Monthly Target',
            'cost_saved_30d': 'Saved This Month',
            'cost_saved_3mo': 'Saved (3mo)',
            'cost_saved_12mo': 'Saved (12mo)',
            'roi_goal_achieved': 'Target Met?',
            'cumulative_cost_saved': 'Total Saved',
            'roi_reached': 'ROI Reached?',
            'roi_status': 'Overall Status'
        }
        display_table = display_table.rename(columns=rename_dict)
        
        # Format numbers
        if 'Activated' in display_table.columns:
            display_table['Activated'] = pd.to_datetime(display_table['Activated'], errors='coerce').dt.strftime('%Y-%m')
        if 'Investment' in display_table.columns:
            display_table['Investment'] = display_table['Investment'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x > 0 else "Not set")
        if 'Usage (30d)' in display_table.columns:
            display_table['Usage (30d)'] = display_table['Usage (30d)'].round(0).astype(int)
        if 'Usage (3mo)' in display_table.columns:
            display_table['Usage (3mo)'] = display_table['Usage (3mo)'].round(0).astype(int)
        if 'Usage (12mo)' in display_table.columns:
            display_table['Usage (12mo)'] = display_table['Usage (12mo)'].round(0).astype(int)
        if 'Hours Saved (30d)' in display_table.columns:
            display_table['Hours Saved (30d)'] = display_table['Hours Saved (30d)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "0.00h")
        if 'Hours Saved (3mo)' in display_table.columns:
            display_table['Hours Saved (3mo)'] = display_table['Hours Saved (3mo)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "0.00h")
        if 'Hours Saved (12mo)' in display_table.columns:
            display_table['Hours Saved (12mo)'] = display_table['Hours Saved (12mo)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "0.00h")
        if 'Monthly Target' in display_table.columns:
            display_table['Monthly Target'] = display_table['Monthly Target'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x > 0 else "Not set")
        if 'Saved This Month' in display_table.columns:
            display_table['Saved This Month'] = display_table['Saved This Month'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        if 'Saved (3mo)' in display_table.columns:
            display_table['Saved (3mo)'] = display_table['Saved (3mo)'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        if 'Saved (12mo)' in display_table.columns:
            display_table['Saved (12mo)'] = display_table['Saved (12mo)'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        if 'Total Saved' in display_table.columns:
            display_table['Total Saved'] = display_table['Total Saved'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        
        st.dataframe(
            display_table,
            use_container_width=True,
            height=400,
            hide_index=True
        )
        
        # Add legends and explanations
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Column Explanations:**
            - **Client**: The company/client name
            - **Project**: The solution/project name
            - **Activated**: When the project went live
            - **Investment**: Total project cost
            - **Usage (30d/3mo/12mo)**: Usage count for different time periods
            - **Hours Saved**: Total hours saved for each time period
            - **Monthly Target**: Dollar savings goal for this month
            - **Saved This Month/3mo/12mo**: Actual dollar value saved
            - **Target Met?**: Did we achieve the monthly ROI goal? (Yes / No)
            - **Total Saved**: Cumulative savings since project launch
            - **ROI Reached?**: Has total saved exceeded investment? (Yes / No)
            - **Overall Status**: Project health indicator with alerts
            """)
        
        with col2:
            st.markdown("""
            **Status Legend:**
            - **ROI Reached / Above Target**: ROI reached or above monthly target
            - **On Track**: 70-100% of monthly target
            - **Below Target**: Less than 70% of target
            - **No Recent Usage**: No usage this month (but was active)
            - **Usage Dropped**: Usage dropped >50% from historical average
            - **Inactive**: No usage in last 3 months
            
            **Formula:**
            Savings = Usage × (Minutes/Use ÷ 60) × Hourly Rate
            """)
    
    with tab2:
        st.subheader("Analytics & Trends")
        
        # Monthly usage trends - Enhanced
        st.markdown("### Usage Per Month (All Projects)")
        
        # Prepare monthly data for plotting with proper year tracking
        monthly_data = []
        available_months = [m for m in MONTHS_FR if m in filtered_df.columns]
        
        # Determine year for each month based on chronological order
        # Assuming data spans from early 2025 to early 2026
        # You can adjust start_year and start_month based on your actual data
        start_year = 2025
        start_month = 4  # April (index 3, but month number is 4)
        
        for _, row in filtered_df.iterrows():
            for month in available_months:
                month_idx = MONTHS_FR.index(month)
                month_num = month_idx + 1  # Convert 0-indexed to 1-indexed month
                
                # Determine year: if month_num < start_month, it's likely next year
                if month_num < start_month:
                    year = start_year + 1
                else:
                    year = start_year
                
                monthly_data.append({
                    'Client': row['CLIENT'],
                    'Project': row['PROJECT'],
                    'Full_Label': f"{row['CLIENT']} - {row['PROJECT']}",
                    'Month': MONTHS_EN[month_idx],
                    'Year': year,
                    'Date_Sort': f"{year}-{month_num:02d}",  # YYYY-MM for sorting
                    'Month_Year_Label': f"{MONTHS_EN[month_idx]} {year}",
                    'Usage': row[month]
                })
        
        if monthly_data:
            monthly_df = pd.DataFrame(monthly_data)
            
            # Sort chronologically
            monthly_df = monthly_df.sort_values('Date_Sort')
            
            # Overall usage trend by month
            st.markdown("#### Total Usage Across All Projects")
            monthly_total = monthly_df.groupby(['Month_Year_Label', 'Date_Sort'])['Usage'].sum().reset_index()
            monthly_total = monthly_total.sort_values('Date_Sort')
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly_total['Month_Year_Label'],
                y=monthly_total['Usage'],
                mode='lines+markers',
                name='Total Usage',
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=10),
                fill='tozeroy',
                fillcolor='rgba(31, 119, 180, 0.2)'
            ))
            fig.update_layout(
                xaxis_title="Month",
                yaxis_title="Total Usage Count",
                height=400,
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Individual project trends
            st.markdown("#### Usage by Project")
            
            # Get chronological order for x-axis
            month_order = monthly_df.sort_values('Date_Sort')['Month_Year_Label'].unique().tolist()
            
            fig = px.line(
                monthly_df,
                x='Month_Year_Label',
                y='Usage',
                color='Full_Label',
                markers=True,
                labels={'Usage': 'Usage Count', 'Month_Year_Label': 'Month', 'Full_Label': 'Project'},
                height=500
            )
            fig.update_layout(
                xaxis={'categoryorder': 'array', 'categoryarray': month_order},
                hovermode='x unified',
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02
                )
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
        
        # Top performers and distribution
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Top 5 by Savings (This Month)")
            top_savings = filtered_df.nlargest(5, 'cost_saved_30d')[['CLIENT', 'PROJECT', 'cost_saved_30d']]
            top_savings['label'] = top_savings['CLIENT'] + ' - ' + top_savings['PROJECT']
            fig = px.bar(
                top_savings, 
                x='cost_saved_30d', 
                y='label',
                orientation='h',
                color='CLIENT',
                labels={'cost_saved_30d': 'Savings ($)', 'label': ''},
                height=300
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("#### Project Status Distribution")
            status_counts = filtered_df['roi_status'].value_counts()
            fig = px.pie(
                values=status_counts.values,
                names=status_counts.index,
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Savings by company
        st.markdown("#### Total Savings by Company")
        company_savings = filtered_df.groupby('COMPANY').agg({
            'cumulative_cost_saved': 'sum',
            'project_cost': 'sum'
        }).reset_index()
        company_savings['ROI %'] = (company_savings['cumulative_cost_saved'] / company_savings['project_cost'] * 100).round(1)
        company_savings = company_savings.sort_values('cumulative_cost_saved', ascending=False)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=company_savings['COMPANY'],
            y=company_savings['cumulative_cost_saved'],
            name='Total Saved',
            marker_color='lightgreen',
            text=company_savings['cumulative_cost_saved'].apply(lambda x: f'${x:,.0f}'),
            textposition='outside'
        ))
        fig.add_trace(go.Bar(
            x=company_savings['COMPANY'],
            y=company_savings['project_cost'],
            name='Investment',
            marker_color='lightcoral',
            text=company_savings['project_cost'].apply(lambda x: f'${x:,.0f}'),
            textposition='outside'
        ))
        fig.update_layout(
            barmode='group',
            xaxis_title="Company",
            yaxis_title="Amount ($)",
            height=400,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Solution Details")
        
        # Select a solution to drill down
        solution_options = [f"{row['CLIENT']} - {row['PROJECT']}" 
                           for _, row in filtered_df.iterrows()]
        
        if solution_options:
            selected_solution = st.selectbox("Select a solution", solution_options)
            
            # Get the selected row
            client_name, project_name = selected_solution.split(' - ', 1)
            solution_data = filtered_df[
                (filtered_df['CLIENT'] == client_name) & 
                (filtered_df['PROJECT'] == project_name)
            ].iloc[0]
            
            # Display configuration
            st.markdown("### 📋 Project Configuration")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("#### Project Info")
                activated = solution_data.get('Month Activated', 'N/A')
                if pd.notna(activated):
                    activated_date = pd.to_datetime(activated, errors='coerce')
                    if pd.notna(activated_date):
                        st.info(f"**Activated:** {activated_date.strftime('%B %Y')}")
                        # Calculate months active
                        months_active = (datetime.now() - activated_date).days / 30
                        st.caption(f"Active for {months_active:.1f} months")
                else:
                    st.info(f"**Activated:** {activated}")
            
            with col2:
                st.markdown("#### Time Savings")
                mins = solution_data.get('Minutes Saved per usage', 0)
                if mins and mins > 0:
                    st.metric("Minutes Saved per Usage", f"{mins:.0f} min")
                    st.caption(f"Each usage saves {mins:.0f} minutes of manual work")
                else:
                    st.info("Time savings not configured")
            
            with col3:
                st.markdown("#### Financial Details")
                investment = solution_data.get('project_cost')
                if investment and investment > 0:
                    st.metric("Total Investment", f"${investment:,.0f}")
                else:
                    st.info("Investment not configured")
                
                hourly_rate = solution_data.get('Client Hourly Rate')
                if hourly_rate and hourly_rate > 0:
                    st.metric("Client Hourly Rate", f"${hourly_rate:.0f}/hr")
                else:
                    st.info("Hourly rate not configured")
                
                monthly_goal = solution_data.get('Monthly ROI Goal')
                if monthly_goal and monthly_goal > 0:
                    st.metric("Monthly Target Savings", f"${monthly_goal:,.0f}")
                    st.caption("Monthly savings goal to stay on track")
                
            st.markdown("---")
            
            # Show the calculation clearly (only if all values are configured)
            investment = solution_data.get('project_cost')
            hourly_rate = solution_data.get('Client Hourly Rate')
            mins = solution_data.get('Minutes Saved per usage')
            
            if investment and hourly_rate and mins and all([investment > 0, hourly_rate > 0, mins > 0]):
                st.markdown("### How Savings Are Calculated")
                st.code(f"""
Example for last 30 days:
• Usage Count: {solution_data['usage_last_30_days']:.0f} times
• Time Saved: {solution_data['usage_last_30_days']:.0f} × {mins:.0f} min = {solution_data['usage_last_30_days'] * mins:.0f} minutes
• Convert to Hours: {solution_data['usage_last_30_days'] * mins:.0f} min ÷ 60 = {solution_data['time_saved_hours_30d']:.1f} hours
• Dollar Value: {solution_data['time_saved_hours_30d']:.1f} hrs × ${hourly_rate:.0f}/hr = ${solution_data['cost_saved_30d']:,.2f}

Total Investment: ${investment:,.0f}
Total Saved (all time): ${solution_data['cumulative_cost_saved']:,.2f}
ROI Net: ${solution_data['roi_net']:,.2f} ({solution_data['roi_progress_percent']:.1f}% of investment)
                """, language=None)
            else:
                st.info("Complete project configuration (Investment, Hourly Rate, Minutes Saved) to see ROI calculations")
            
            st.markdown("---")
            
            st.markdown("---")
            
            # Display metrics
            st.markdown("### Key Metrics")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Usage (30d)", f"{solution_data['usage_last_30_days']:.0f}")
            with col2:
                delta_value = solution_data['mom_usage_percent']
                st.metric("MoM Change", f"{delta_value:.1f}%", delta=f"{delta_value:.1f}%")
            with col3:
                st.metric("Hours Saved (30d)", f"{solution_data['time_saved_hours_30d']:.1f}h")
            with col4:
                st.metric("Savings (30d)", f"${solution_data['cost_saved_30d']:,.0f}")
            with col5:
                st.metric("ROI Progress", f"{solution_data['roi_progress_percent']:.1f}%")
            
            # Historical comparison
            if solution_data['historical_monthly_avg'] > 0:
                st.markdown("### Usage Trend Analysis")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Historical Avg/Month",
                        f"{solution_data['historical_monthly_avg']:.1f}",
                        help="Average usage during first 6 active months"
                    )
                with col2:
                    st.metric(
                        "Recent Avg/Month",
                        f"{solution_data['recent_monthly_avg']:.1f}",
                        delta=f"-{solution_data['usage_drop_percent']:.0f}%" if solution_data['usage_drop_percent'] > 0 else f"+{abs(solution_data['usage_drop_percent']):.0f}%",
                        help="Average usage in last 3 months"
                    )
                with col3:
                    if solution_data['usage_drop_percent'] > 50:
                        st.error(f"Usage dropped {solution_data['usage_drop_percent']:.0f}%")
                    elif solution_data['usage_drop_percent'] > 20:
                        st.warning(f"Usage dropped {solution_data['usage_drop_percent']:.0f}%")
                    elif solution_data['usage_drop_percent'] < -20:
                        st.success(f"Usage increased {abs(solution_data['usage_drop_percent']):.0f}%")
                    else:
                        st.info(f"Usage stable")
            
            # Status with colored box
            status = solution_data['roi_status']
            status_color = solution_data.get('status_color', 'gray')
            
            if 'ROI Reached' in status or 'Above Target' in status:
                st.success(f"**Status:** {status}")
            elif 'On Track' in status:
                st.warning(f"**Status:** {status}")
            elif 'Below Target' in status or 'Dropped' in status:
                st.error(f"**Status:** {status}")
            else:
                st.info(f"**Status:** {status}")
            
            st.markdown(f"**Break-even Estimate:** {solution_data['breakeven_estimate']}")
            
            # ROI Progress bar
            st.markdown("### ROI Progress")
            progress_value = min(solution_data['roi_progress_percent'] / 100, 1.0)
            st.progress(progress_value)
            st.caption(f"${solution_data['cumulative_cost_saved']:,.0f} / ${solution_data['project_cost']:,.0f}")
            
            # Monthly trend for this solution
            st.markdown("### Monthly Usage Trend")
            available_months = [m for m in MONTHS_FR if m in solution_data.index]
            monthly_values = [solution_data[month] for month in available_months]
            monthly_labels = [MONTHS_EN[MONTHS_FR.index(month)] for month in available_months]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly_labels,
                y=monthly_values,
                mode='lines+markers',
                name='Usage',
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=8)
            ))
            fig.update_layout(
                xaxis_title="Month",
                yaxis_title="Usage Count",
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Savings calculation breakdown
            st.markdown("### Savings Calculation")
            st.write(f"- **Usage (12 months):** {solution_data['usage_last_12_months']:.0f}")
            st.write(f"- **Time saved per usage:** {solution_data.get('Minutes Saved per usage', 5)} minutes")
            st.write(f"- **Total time saved:** {solution_data['time_saved_hours_12mo']:.1f} hours")
            st.write(f"- **Hourly rate:** ${solution_data.get('Client Hourly Rate', 45)}")
            st.write(f"- **Total savings:** ${solution_data['cost_saved_12mo']:,.2f}")
        else:
            st.info("No solutions available with current filters.")
    
    with tab4:
        st.subheader("Custom Columns & Settings")
        
        # Load config
        custom_config = load_custom_columns_config()
        
        st.markdown("---")
        
        # Section 1: Custom Data Columns
        st.markdown("### Custom Data Columns")
        st.caption("Add custom fields to store metadata (e.g., Project Owner, Priority, Status)")
        
        with st.expander("Add New Data Column", expanded=False):
            new_col_name = st.text_input("Column Name", key="new_data_col")
            new_col_type = st.selectbox("Data Type", ["Text", "Number", "Date"], key="new_data_type")
            new_col_default = st.text_input("Default Value", key="new_data_default")
            
            if st.button("Add Data Column"):
                if new_col_name and new_col_name not in custom_config['data_columns']:
                    custom_config['data_columns'][new_col_name] = {
                        'type': new_col_type,
                        'default_value': new_col_default,
                        'values': {}
                    }
                    save_custom_columns_config(custom_config)
                    st.success(f"Added column '{new_col_name}'")
                    st.rerun()
                elif not new_col_name:
                    st.error("Please enter a column name")
                else:
                    st.error("Column already exists")
        
        # Show existing data columns
        if custom_config['data_columns']:
            st.markdown("#### Existing Data Columns")
            for col_name, col_config in custom_config['data_columns'].items():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.text(f"{col_name} ({col_config['type']})")
                with col2:
                    if st.button("Edit", key=f"edit_data_{col_name}"):
                        st.session_state[f'editing_data_{col_name}'] = True
                with col3:
                    if st.button("Delete", key=f"del_data_{col_name}"):
                        del custom_config['data_columns'][col_name]
                        save_custom_columns_config(custom_config)
                        st.success(f"Deleted column '{col_name}'")
                        st.rerun()
                
                # Edit values
                if st.session_state.get(f'editing_data_{col_name}', False):
                    with st.expander(f"Edit values for '{col_name}'", expanded=True):
                        for _, row in filtered_df.iterrows():
                            project_key = f"{row['COMPANY']}_{row['PROJECT']}"
                            current_value = col_config.get('values', {}).get(project_key, col_config.get('default_value', ''))
                            
                            new_value = st.text_input(
                                f"{row['COMPANY']} - {row['PROJECT']}", 
                                value=current_value,
                                key=f"edit_{col_name}_{project_key}"
                            )
                            
                            if new_value != current_value:
                                if 'values' not in custom_config['data_columns'][col_name]:
                                    custom_config['data_columns'][col_name]['values'] = {}
                                custom_config['data_columns'][col_name]['values'][project_key] = new_value
                        
                        if st.button("Save Changes", key=f"save_data_{col_name}"):
                            save_custom_columns_config(custom_config)
                            st.session_state[f'editing_data_{col_name}'] = False
                            st.success("Saved!")
                            st.rerun()
        
        st.markdown("---")
        
        # Section 2: Custom Calculated Columns
        st.markdown("### Custom Calculated Columns")
        st.caption("Add columns with formulas (e.g., usage_last_30_days / Investment)")
        
        with st.expander("Add New Calculated Column", expanded=False):
            calc_col_name = st.text_input("Column Name", key="new_calc_col")
            calc_formula = st.text_area(
                "Formula (pandas eval syntax)", 
                help="Example: usage_last_30_days / (Investment + 1)\nAvailable columns: usage_last_30_days, cost_saved_30d, Investment, etc.",
                key="new_calc_formula"
            )
            
            if st.button("Add Calculated Column"):
                if calc_col_name and calc_formula:
                    custom_config['calculated_columns'][calc_col_name] = calc_formula
                    save_custom_columns_config(custom_config)
                    st.success(f"Added calculated column '{calc_col_name}'")
                    st.rerun()
                else:
                    st.error("Please enter both name and formula")
        
        # Show existing calculated columns
        if custom_config['calculated_columns']:
            st.markdown("#### Existing Calculated Columns")
            for col_name, formula in custom_config['calculated_columns'].items():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.code(f"{col_name} = {formula}", language=None)
                with col2:
                    if st.button("Delete", key=f"del_calc_{col_name}"):
                        del custom_config['calculated_columns'][col_name]
                        save_custom_columns_config(custom_config)
                        st.success(f"Deleted column '{col_name}'")
                        st.rerun()
        
        st.markdown("---")
        
        # Section 3: Column Visibility
        st.markdown("### Column Visibility")
        st.caption("Choose which columns to display in the Portfolio Overview table")
        
        # Get all available columns
        all_possible_columns = [
            'CLIENT', 'PROJECT', 'Month Activated', 'Investment',
            'Usage Type', 'Months Active',
            'usage_last_30_days', 'usage_last_3_months', 'usage_last_12_months',
            'time_saved_hours_30d', 'time_saved_hours_3mo', 'time_saved_hours_12mo',
            'Monthly ROI Goal', 'cost_saved_30d', 'cost_saved_3mo', 'cost_saved_12mo',
            'roi_goal_achieved', 'cumulative_cost_saved', 'roi_reached', 'roi_status',
            'Minutes Saved per usage', 'Client Hourly Rate',
            'mom_usage_percent', 'roi_progress_percent', 'breakeven_estimate'
        ] + list(custom_config.get('data_columns', {}).keys()) + list(custom_config.get('calculated_columns', {}).keys())
        
        selected_columns = st.multiselect(
            "Visible Columns",
            options=all_possible_columns,
            default=custom_config.get('visible_columns', all_possible_columns[:12]),
            key="visible_cols"
        )
        
        if st.button("Save Column Visibility"):
            custom_config['visible_columns'] = selected_columns
            save_custom_columns_config(custom_config)
            st.success("Column visibility saved!")
            st.rerun()
        
        st.markdown("---")
        
        # Section 4: Custom Projects/Rows
        st.markdown("### Custom Projects")
        st.caption("Add manual project entries that don't have Supabase data")
        
        # Load custom projects
        projects_config = load_custom_projects()
        
        with st.expander("Add New Project", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                new_company = st.text_input("Company", key="new_proj_company")
                new_project = st.text_input("Project Name", key="new_proj_name")
                new_investment = st.number_input("Investment ($)", min_value=0, key="new_proj_inv")
                new_roi_goal = st.number_input("Monthly ROI Goal ($)", min_value=0, key="new_proj_roi")
            
            with col2:
                new_hourly_rate = st.number_input("Hourly Rate ($)", min_value=0, key="new_proj_rate")
                new_minutes = st.number_input("Minutes Saved per Usage", min_value=0, key="new_proj_mins")
                new_usage_type = st.text_input("Usage Type", key="new_proj_type")
                new_activated = st.date_input("Month Activated", key="new_proj_date")
            
            if st.button("Add Project"):
                if new_company and new_project:
                    new_proj = {
                        'company': new_company,
                        'client': new_company,
                        'project_name': new_project,
                        'investment': new_investment if new_investment > 0 else None,
                        'monthly_roi_goal': new_roi_goal if new_roi_goal > 0 else None,
                        'hourly_rate': new_hourly_rate if new_hourly_rate > 0 else None,
                        'minutes_saved': new_minutes if new_minutes > 0 else None,
                        'usage_type': new_usage_type if new_usage_type else None,
                        'month_activated': str(new_activated) if new_activated else None,
                        'monthly_usage': {}
                    }
                    projects_config['custom_projects'].append(new_proj)
                    save_custom_projects(projects_config)
                    st.success(f"Added project '{new_project}'!")
                    st.rerun()
                else:
                    st.error("Please enter at least Company and Project Name")
        
        # Show existing custom projects
        if projects_config['custom_projects']:
            st.markdown("#### Existing Custom Projects")
            for idx, project in enumerate(projects_config['custom_projects']):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.text(f"{project['company']} - {project['project_name']}")
                with col2:
                    if st.button("Edit Usage", key=f"edit_proj_{idx}"):
                        st.session_state[f'editing_project_{idx}'] = True
                with col3:
                    if st.button("Delete", key=f"del_proj_{idx}"):
                        projects_config['custom_projects'].pop(idx)
                        save_custom_projects(projects_config)
                        st.success("Deleted project!")
                        st.rerun()
                
                # Edit monthly usage
                if st.session_state.get(f'editing_project_{idx}', False):
                    with st.expander(f"Edit monthly usage for {project['project_name']}", expanded=True):
                        st.caption("Enter usage counts for each month")
                        cols = st.columns(4)
                        
                        for i, month in enumerate(MONTHS_EN):
                            with cols[i % 4]:
                                month_fr = MONTHS_FR[i]
                                current_val = project.get('monthly_usage', {}).get(month_fr, 0)
                                new_val = st.number_input(
                                    month,
                                    min_value=0,
                                    value=int(current_val),
                                    key=f"usage_{idx}_{month}"
                                )
                                if 'monthly_usage' not in projects_config['custom_projects'][idx]:
                                    projects_config['custom_projects'][idx]['monthly_usage'] = {}
                                projects_config['custom_projects'][idx]['monthly_usage'][month_fr] = new_val
                        
                        if st.button("Save Usage Data", key=f"save_proj_{idx}"):
                            save_custom_projects(projects_config)
                            st.session_state[f'editing_project_{idx}'] = False
                            st.success("Saved!")
                            st.rerun()

if __name__ == "__main__":
    main()
