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
from modules.email_alerts import check_and_send_alerts, send_email_alert
from modules.data_loader import calculate_metrics as _calculate_metrics

# Page config
st.set_page_config(
    page_title="Genia Client Dashboard",
    page_icon=None,
    layout="wide"
)

# Constants
MONTHS_FR = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 
             'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']
MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June',
             'July', 'August', 'September', 'October', 'November', 'December']

# Chart styling - clean, legible, light theme
CHART_LAYOUT = dict(
    paper_bgcolor='rgba(255,255,255,1)',
    plot_bgcolor='rgba(248,249,250,1)',
    font=dict(family='Inter, system-ui, sans-serif', size=13, color='#1a1a2e'),
    margin=dict(l=60, r=40, t=50, b=60),
    xaxis=dict(
        showgrid=True,
        gridcolor='rgba(0,0,0,0.08)',
        zeroline=False,
        tickfont=dict(size=12),
        title_font=dict(size=14),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor='rgba(0,0,0,0.08)',
        zeroline=False,
        tickfont=dict(size=12),
        title_font=dict(size=14),
    ),
    legend=dict(
        font=dict(size=12),
        bgcolor='rgba(255,255,255,0.9)',
        bordercolor='rgba(0,0,0,0.1)',
        borderwidth=1,
    ),
    hoverlabel=dict(
        bgcolor='white',
        font_size=13,
        font_family='sans-serif',
    ),
)
CHART_COLORS = [
    '#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed',
    '#0891b2', '#ea580c', '#db2777', '#4f46e5', '#0d9488',
]
CUSTOM_COLUMNS_FILE = 'custom_columns_config.json'
CELL_OVERRIDES_FILE = 'cell_overrides.json'
HIDDEN_PROJECTS_FILE = 'hidden_projects.json'

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

def load_cell_overrides():
    """Load cell-level overrides (user edits from the table)"""
    if os.path.exists(CELL_OVERRIDES_FILE):
        with open(CELL_OVERRIDES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cell_overrides(overrides):
    """Save cell-level overrides"""
    with open(CELL_OVERRIDES_FILE, 'w') as f:
        json.dump(overrides, f, indent=2)

def load_hidden_projects():
    """Load list of hidden project keys (COMPANY_PROJECT)"""
    if os.path.exists(HIDDEN_PROJECTS_FILE):
        with open(HIDDEN_PROJECTS_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('hidden', []))
    return set()

def save_hidden_projects(hidden_set):
    """Save hidden project keys"""
    with open(HIDDEN_PROJECTS_FILE, 'w') as f:
        json.dump({'hidden': list(hidden_set)}, f, indent=2)

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

def load_data():
    """Load data from Supabase - aggregate usage by month for each project"""
    supabase = get_supabase_client()
    if not supabase:
        return pd.DataFrame()
    
    from modules.data_loader import load_data as _load_data
    return _load_data(supabase, COMPANY_CONFIGS)

def calculate_metrics(df):
    return _calculate_metrics(df)


def main():
    st.title("Genia Client Dashboard")
    
    # Manual refresh button in sidebar
    with st.sidebar:
        st.image("https://genia.co/wp-content/uploads/2022/10/logo_genia.svg", width=160)
        st.markdown("---")
        
        # Manual refresh button
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        # Show last refresh time
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = time.time()
        
        import pytz
        montreal_tz = pytz.timezone('America/Montreal')
        last_refresh_time = datetime.fromtimestamp(st.session_state.last_refresh, tz=pytz.utc).astimezone(montreal_tz)
        st.caption(f"Last updated: {last_refresh_time.strftime('%H:%M:%S')}")
    
    st.markdown("---")
    
    # Load data
    with st.spinner("Loading data from Supabase..."):
        df = load_data()
    
    if df.empty:
        st.error("No data found in Supabase. Please check your configuration and database.")
        return
    
    # Calculate metrics
    df_metrics = calculate_metrics(df)

    # Add custom columns
    custom_config = load_custom_columns_config()
    df_metrics = add_custom_data_columns(df_metrics, custom_config)
    df_metrics = add_custom_calculated_columns(df_metrics, custom_config)
    
    # Filter out hidden projects
    hidden_projects = load_hidden_projects()
    df_metrics['_project_key'] = df_metrics.apply(lambda r: f"{r['COMPANY']}_{r['PROJECT']}", axis=1)
    visible_df = df_metrics[~df_metrics['_project_key'].isin(hidden_projects)].drop(columns=['_project_key'])
    
    # Sidebar - Filters (built from visible projects only)
    st.sidebar.header("Filters")
    
    clients = ['All'] + sorted(visible_df['CLIENT'].dropna().unique().tolist())
    selected_client = st.sidebar.selectbox("Filter by Client", clients)
    
    projects = ['All'] + sorted(visible_df['PROJECT'].dropna().unique().tolist())
    selected_project = st.sidebar.selectbox("Filter by Project", projects)
    
    status_options = ['All'] + sorted(visible_df['roi_status'].unique().tolist())
    selected_status = st.sidebar.selectbox("Filter by ROI Status", status_options)
    
    # Apply filters (from visible projects)
    filtered_df = visible_df.copy()
    if selected_client != 'All':
        filtered_df = filtered_df[filtered_df['CLIENT'] == selected_client]
    if selected_project != 'All':
        filtered_df = filtered_df[filtered_df['PROJECT'] == selected_project]
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
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["Portfolio Overview", "Solution Details", "Settings"])
    
    with tab1:
        st.subheader("Portfolio Overview")
        
        # Sort options
        sort_col1, sort_col2 = st.columns([2, 1])
        with sort_col1:
            sort_by = st.selectbox(
                "Sort by",
                ['usage_last_30_days', 'cost_saved_30d', 'roi_progress_percent', 'mom_usage_percent'],
                format_func=lambda x: {
                    'usage_last_30_days': 'Usage (This Month)',
                    'cost_saved_30d': 'Saved (This Month)',
                    'roi_progress_percent': 'ROI Progress %',
                    'mom_usage_percent': 'MoM Change %'
                }[x]
            )
        with sort_col2:
            sort_order = st.radio("Order", ['Descending', 'Ascending'], horizontal=True)
        
        # Sort dataframe - first by COMPANY, then by selected column
        ascending = sort_order == 'Ascending'
        display_df = filtered_df.sort_values(
            by=['COMPANY', '_project_group', '_sort_order', sort_by],
            ascending=[True, True, True, ascending]
        )
        
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
            'usage_yesterday': 'Yesterday',
            'usage_last_30_days': 'Usage (This Month)',
            'usage_last_3_months': 'Usage (Last 3 Months)',
            'usage_last_12_months': 'Usage (Last 12 Months)',
            'time_saved_hours_30d': 'Hours Saved (This Month)',
            'time_saved_hours_3mo': 'Hours Saved (Last 3 Months)',
            'time_saved_hours_12mo': 'Hours Saved (Last 12 Months)',
            'Monthly ROI Goal': 'Monthly Target',
            'cost_saved_30d': 'Saved (This Month)',
            'cost_saved_3mo': 'Saved (Last 3 Months)',
            'cost_saved_12mo': 'Saved (Last 12 Months)',
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
        if 'Yesterday' in display_table.columns:
            display_table['Yesterday'] = display_table['Yesterday'].fillna(0).round(0).astype(int)
        if 'Usage (This Month)' in display_table.columns:
            display_table['Usage (This Month)'] = display_table['Usage (This Month)'].round(0).astype(int)
        if 'Usage (Last 3 Months)' in display_table.columns:
            display_table['Usage (Last 3 Months)'] = display_table['Usage (Last 3 Months)'].round(0).astype(int)
        if 'Usage (Last 12 Months)' in display_table.columns:
            display_table['Usage (Last 12 Months)'] = display_table['Usage (Last 12 Months)'].round(0).astype(int)
        if 'Hours Saved (This Month)' in display_table.columns:
            display_table['Hours Saved (This Month)'] = display_table['Hours Saved (This Month)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "")
        if 'Hours Saved (Last 3 Months)' in display_table.columns:
            display_table['Hours Saved (Last 3 Months)'] = display_table['Hours Saved (Last 3 Months)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "")
        if 'Hours Saved (Last 12 Months)' in display_table.columns:
            display_table['Hours Saved (Last 12 Months)'] = display_table['Hours Saved (Last 12 Months)'].apply(lambda x: f"{x:.2f}h" if pd.notna(x) else "")
        if 'Monthly Target' in display_table.columns:
            display_table['Monthly Target'] = display_table['Monthly Target'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x > 0 else "Not set")
        if 'Saved (This Month)' in display_table.columns:
            display_table['Saved (This Month)'] = display_table['Saved (This Month)'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")
        if 'Saved (Last 3 Months)' in display_table.columns:
            display_table['Saved (Last 3 Months)'] = display_table['Saved (Last 3 Months)'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")
        if 'Saved (Last 12 Months)' in display_table.columns:
            display_table['Saved (Last 12 Months)'] = display_table['Saved (Last 12 Months)'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")
        if 'Total Saved' in display_table.columns:
            display_table['Total Saved'] = display_table['Total Saved'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "")
        
        # For split sub-rows (e.g. email_agent, phone_agent), show "Same as Hemy" for shared financial columns
        if '_hide_roi' in display_df.columns:
            hide_mask = display_df['_hide_roi'].reindex(display_table.index).fillna(False).astype(bool)
            hide_cols = ['Investment', 'Activated', 'Monthly Target', 'ROI Reached?', 'Target Met?', 'Overall Status']
            for col in hide_cols:
                if col in display_table.columns:
                    display_table.loc[hide_mask, col] = 'Same as ALL_HEMY'

        # Add colored dot prefix to Overall Status for visual indicator
        status_dots = {
            'ROI Reached':            '🟢 ROI Reached',
            'Above Target':           '🟢 Above Target',
            'On Track':               '🟡 On Track',
            'Below Target':           '🔴 Below Target',
            'Usage Dropped':          '🔴 Usage Dropped',
            'No Recent Usage':        '🟠 No Recent Usage',
            'Inactive':               '🟠 Inactive',
            'Active (Config Needed)': '⚪ Active (Config Needed)',
            'Same as ALL_HEMY':       'Same as ALL_HEMY',
        }
        if 'Overall Status' in display_table.columns:
            display_table['Overall Status'] = display_table['Overall Status'].map(
                lambda v: status_dots.get(v, v)
            )

        # Apply cell overrides (user edits from previous sessions)
        cell_overrides = load_cell_overrides()
        for idx, row in display_table.iterrows():
            row_key = f"{display_df.loc[idx, 'COMPANY']}_{display_df.loc[idx, 'PROJECT']}"
            if row_key in cell_overrides:
                for col, val in cell_overrides[row_key].items():
                    if col in display_table.columns and val is not None:
                        display_table.at[idx, col] = val

        st.caption("Click any cell to edit. Changes are saved automatically.")
        edited_table = st.data_editor(
            display_table,
            use_container_width=True,
            height=400,
            hide_index=True,
            key="portfolio_table_editor"
        )

        # Persist edits when user changes cells
        if edited_table is not None:
            has_changes = False
            for idx in display_table.index:
                row_key = f"{display_df.loc[idx, 'COMPANY']}_{display_df.loc[idx, 'PROJECT']}"
                if row_key not in cell_overrides:
                    cell_overrides[row_key] = {}
                for col in display_table.columns:
                    orig = display_table.at[idx, col]
                    new_val = edited_table.at[idx, col]
                    orig_str = "" if pd.isna(orig) else str(orig)
                    new_str = "" if pd.isna(new_val) else str(new_val)
                    if orig_str != new_str:
                        has_changes = True
                        stored = None if pd.isna(new_val) else (new_val if isinstance(new_val, (str, int, float, bool)) else str(new_val))
                        cell_overrides[row_key][col] = stored
            if has_changes:
                cell_overrides = {k: {c: v for c, v in vals.items() if v is not None} for k, vals in cell_overrides.items()}
                cell_overrides = {k: v for k, v in cell_overrides.items() if v}
                save_cell_overrides(cell_overrides)
                st.rerun()
        
        # Add legends and explanations
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Column Explanations:**
            - **Client**: The company/client name
            - **Project**: The solution/project name
            - **Activated**: When the project went live
            - **Investment**: Total project cost
            - **Yesterday**: Usage count from yesterday (complete day)
            - **Usage (This Month/Last 3 Months/Last 12 Months)**: Usage count for different time periods
            - **Hours Saved**: Total hours saved for each time period
            - **Monthly Target**: Dollar savings goal per month
            - **Saved (This Month/Last 3 Months/Last 12 Months)**: Actual dollar value saved
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
            - **Inactive**: No usage this month or last 3 months
            
            **Formula:**
            Savings = Usage × (Minutes/Use ÷ 60) × Hourly Rate
            """)
    
    with tab2:
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
            st.markdown("### Project Configuration")
            
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
Example for this month:
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
                st.metric("Usage (This Month)", f"{solution_data['usage_last_30_days']:.0f}")
            with col2:
                delta_value = solution_data['mom_usage_percent']
                st.metric("MoM Change", f"{delta_value:.1f}%", delta=f"{delta_value:.1f}%")
            with col3:
                st.metric("Hours Saved (This Month)", f"{solution_data['time_saved_hours_30d']:.1f}h")
            with col4:
                st.metric("Saved (This Month)", f"${solution_data['cost_saved_30d']:,.0f}")
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
            
            # Monthly trend for this solution - with year for correct chronological order
            st.markdown("### Monthly Usage Trend")
            _cy = datetime.now().year
            _cm = datetime.now().month
            month_data = []
            for i, month_fr in enumerate(MONTHS_FR):
                if month_fr not in solution_data.index:
                    continue
                month_num = i + 1
                year = _cy if month_num <= _cm else _cy - 1
                month_data.append({
                    'label': f"{MONTHS_EN[i][:3]} {year}",
                    'value': solution_data[month_fr],
                    'sort_key': f"{year}-{month_num:02d}",
                })
            month_data.sort(key=lambda x: x['sort_key'])
            monthly_labels = [d['label'] for d in month_data]
            monthly_values = [d['value'] for d in month_data]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly_labels,
                y=monthly_values,
                mode='lines+markers',
                name='Usage',
                line=dict(color=CHART_COLORS[0], width=3),
                marker=dict(size=10, line=dict(width=2, color='white')),
                fill='tozeroy',
                fillcolor='rgba(37, 99, 235, 0.12)',
                hovertemplate='%{x}<br><b>%{y:,.0f}</b> usages<extra></extra>',
            ))
            fig.update_layout(
                **CHART_LAYOUT,
                xaxis_title="Month",
                yaxis_title="Usage Count",
                height=340,
                showlegend=False,
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
    
    with tab3:
        st.subheader("Custom Columns & Settings")
        
        # Load config
        custom_config = load_custom_columns_config()
        
        st.markdown("---")
        
        # Section 0: Hidden Projects
        st.markdown("### Hidden Projects")
        st.caption("Hide projects from the entire dashboard. They won't appear in the table, metrics, or filters.")
        
        # Show hidden projects with Unhide button
        if hidden_projects:
            st.markdown("#### Currently Hidden")
            if st.button("Unhide All", key="unhide_all"):
                save_hidden_projects(set())
                st.success("All projects unhidden!")
                st.rerun()
            for key in sorted(hidden_projects):
                display_name = key.replace('_', ' - ', 1)  # Fallback if project no longer in data
                if '_project_key' in df_metrics.columns:
                    row_match = df_metrics[df_metrics['_project_key'] == key]
                    if not row_match.empty:
                        display_name = f"{row_match.iloc[0]['CLIENT']} - {row_match.iloc[0]['PROJECT']}"
                if st.button(f"Unhide: {display_name}", key=f"unhide_{key}"):
                    hidden_projects.remove(key)
                    save_hidden_projects(hidden_projects)
                    st.rerun()
        else:
            st.caption("No projects hidden.")
        
        # Hide a project dropdown
        st.markdown("#### Hide a Project")
        visible_options = [f"{row['CLIENT']} - {row['PROJECT']}" for _, row in visible_df.iterrows()]
        if visible_options:
            project_to_hide = st.selectbox(
                "Select project to hide",
                options=[""] + visible_options,
                key="hide_project_select",
                format_func=lambda x: "Choose..." if x == "" else x,
            )
            if project_to_hide and st.button("Hide Project"):
                # Find the key for selected project
                for _, row in visible_df.iterrows():
                    if f"{row['CLIENT']} - {row['PROJECT']}" == project_to_hide:
                        key = f"{row['COMPANY']}_{row['PROJECT']}"
                        hidden_projects.add(key)
                        save_hidden_projects(hidden_projects)
                        st.success(f"Hidden '{project_to_hide}'")
                        st.rerun()
                        break
        else:
            st.caption("All projects are already hidden or no projects available.")
        
        st.markdown("---")
        
        # Section 1: Table cell overrides
        st.markdown("### Table Cell Overrides")
        st.caption("Edits you make in the Portfolio Overview table are saved here. Clear to reset all custom cell values.")
        if os.path.exists(CELL_OVERRIDES_FILE):
            overrides = load_cell_overrides()
            override_count = sum(len(v) for v in overrides.values())
            st.caption(f"Currently {override_count} cell override(s) across {len(overrides)} project(s).")
            if st.button("Clear All Table Edits", key="clear_overrides"):
                save_cell_overrides({})
                st.success("All table edits cleared!")
                st.rerun()
        else:
            st.caption("No cell overrides yet.")
        
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
            'usage_yesterday', 'usage_last_30_days', 'usage_last_3_months', 'usage_last_12_months',
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
        
        # Section 4: Email Alerts  
        st.markdown("### Email Alerts")
        
        # Get recipients from .env
        recipients_str = os.getenv('ALERT_TO_EMAILS', '')
        recipients = [email.strip() for email in recipients_str.split(',') if email.strip()]
        
        dashboard_url = os.getenv('DASHBOARD_URL', 'http://localhost:8501')
        
        if st.button("Test with Current Numbers", type="primary", use_container_width=True):
            smtp_config = {
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', 587)),
                'smtp_user': os.getenv('SMTP_USER', ''),
                'smtp_password': os.getenv('SMTP_PASSWORD', ''),
                'from_email': os.getenv('ALERT_FROM_EMAIL', '')
            }
            
            alert_config = {
                'dashboard_url': dashboard_url,
                'to_emails': recipients
            }
            
            with st.spinner("Checking usage..."):
                alerts_sent, alerts_skipped = check_and_send_alerts(df_metrics, smtp_config, alert_config)
                
                if alerts_sent:
                    st.success(f"Sent {len(alerts_sent)} alert(s)")
                    for alert in alerts_sent:
                        st.caption(f"• {alert['project']}: Yesterday={alert['yesterday']:.0f}, Avg={alert['avg']:.1f}")
                else:
                    st.info("No alerts needed")
        
if __name__ == "__main__":
    main()
