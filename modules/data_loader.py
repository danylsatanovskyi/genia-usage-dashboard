"""
Shared data loading - used by both app and run_daily_alerts for consistent metrics
"""
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

MONTHS_FR = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 
             'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']


def load_excel_metadata():
    """Load project metadata from Excel (no streamlit)"""
    try:
        excel_file = 'data.xlsx'
        metadata_dict = {}
        company_sheets = ['HEMA-QUEBEC', 'CELLCOM', 'SERIE CONSEIL', 'TECHO BLOC', 'DIGITAD', 'RETROMTL', 'CHEMTECH']
        
        for sheet_name in company_sheets:
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet_name, header=2)
                df.columns = df.columns.str.strip()
                df['CLIENT'] = df['CLIENT'].ffill()
                df = df[df['PROJECT'].notna() & (df['PROJECT'] != '')]
                exclude_projects = ['TYPE D\'ECONOMIE', 'PROJET', 'TOTAL', 'SCREENSHOT FOR EMAIL']
                df = df[~df['PROJECT'].isin(exclude_projects)]
                df = df[~df['PROJECT'].str.contains('🔍|⚙️|💰', na=False)]
                
                for _, row in df.iterrows():
                    project_key = f"{sheet_name}_{row['PROJECT']}"
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
            except Exception:
                continue
        
        return metadata_dict
    except Exception:
        return {}


def _fetch_all_rows(supabase, table_name):
    """Fetch all rows from a Supabase table, paginating past the 1000-row default limit."""
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        response = supabase.table(table_name).select("*").range(offset, offset + page_size - 1).execute()
        if not response.data:
            break
        all_rows.extend(response.data)
        if len(response.data) < page_size:
            break
        offset += page_size
    return all_rows


def _count_usage(series, value_type):
    """Count usage from a series regardless of dtype (bool, int, object/string)."""
    if value_type != "boolean":
        return pd.to_numeric(series, errors='coerce').sum()
    # Handle bool, int (0/1), and object ("True"/"False" strings)
    if series.dtype == bool:
        return series.sum()
    return (series == True).sum()


def load_data(supabase, company_configs):
    """Load data from Supabase - same logic as app"""
    excel_metadata = load_excel_metadata()
    all_data = []

    for company_name, company_config in company_configs.items():
        for project_name, project_config in company_config['projects'].items():
            try:
                table_name = project_config['supabase_table']
                usage_field = project_config['usage_field']
                value_type = project_config.get('value_type', 'boolean')

                rows = _fetch_all_rows(supabase, table_name)

                if not rows:
                    continue

                records_df = pd.DataFrame(rows)

                # Use 'date' or 'processed_date' if present (actual usage time), else fall back to 'created_at'
                if 'date' in records_df.columns:
                    date_col = 'date'
                elif 'processed_date' in records_df.columns:
                    date_col = 'processed_date'
                else:
                    date_col = 'created_at'
                records_df[date_col] = pd.to_datetime(records_df[date_col], errors='coerce')
                records_df = records_df[records_df[date_col].notna()]

                records_df['_month'] = records_df[date_col].dt.month
                records_df['_year'] = records_df[date_col].dt.year
                records_df['_date'] = records_df[date_col].dt.date

                yesterday = date.today() - timedelta(days=1)
                yesterday_records = records_df[records_df['_date'] == yesterday]

                if usage_field in yesterday_records.columns:
                    usage_yesterday = _count_usage(yesterday_records[usage_field], value_type)
                else:
                    usage_yesterday = 0

                current_year = date.today().year
                current_month = date.today().month
                monthly_usage = {}
                for month_idx in range(12):
                    month_num = month_idx + 1
                    year = current_year if month_num <= current_month else current_year - 1
                    month_name = MONTHS_FR[month_idx]
                    month_records = records_df[
                        (records_df['_month'] == month_num) & (records_df['_year'] == year)
                    ]
                    usage_count = _count_usage(month_records[usage_field], value_type) if usage_field in month_records.columns else 0
                    monthly_usage[month_name] = usage_count
                
                project_key = f"{company_config.get('worksheet_name', company_name)}_{project_name}"
                metadata = excel_metadata.get(project_key, {})
                usage_type_override = "Matched Companies" if (company_name == "TECHO BLOC" and project_name == "MATCHING") else None
                
                project_row = {
                    'COMPANY': company_name,
                    'CLIENT': company_config.get('client_name', company_name),
                    'PROJECT': project_name,
                    'Investment': metadata.get('Investment'),
                    'Monthly ROI Goal': metadata.get('Monthly ROI Goal'),
                    'Client Hourly Rate': metadata.get('Client Hourly Rate'),
                    'Minutes Saved per usage': metadata.get('Minutes Saved per usage'),
                    'Month Activated': metadata.get('Month Activated'),
                    'Usage Type': usage_type_override or metadata.get('Usage Type'),
                    'Months Active': metadata.get('Months Active'),
                    'usage_yesterday': usage_yesterday,
                }
                project_row.update(monthly_usage)
                all_data.append(project_row)
                
            except Exception as e:
                print(f"Error: {company_name} - {project_name}: {e}")
                continue
    
    if all_data:
        return pd.DataFrame(all_data)
    return pd.DataFrame()


def calculate_metrics(df):
    """Same metrics as app - usage_last_3_months, recent_monthly_avg, etc."""
    if df.empty:
        return df
    
    current_month_idx = datetime.now().month - 1

    df['usage_last_30_days'] = df[MONTHS_FR[current_month_idx]] if MONTHS_FR[current_month_idx] in df.columns else 0

    month_cols_3mo = []
    for i in range(1, 4):
        month_idx = (current_month_idx - i) % 12
        if MONTHS_FR[month_idx] in df.columns:
            month_cols_3mo.append(MONTHS_FR[month_idx])
    df['usage_last_3_months'] = df[month_cols_3mo].sum(axis=1) if month_cols_3mo else 0

    available_months = [m for m in MONTHS_FR if m in df.columns]
    df['usage_last_12_months'] = df[available_months].sum(axis=1) if available_months else 0

    def get_historical_avg(row):
        usage_values = [row[m] for m in available_months if pd.notna(row.get(m)) and row.get(m, 0) > 0]
        if len(usage_values) >= 6:
            return np.mean(usage_values[:6])
        elif len(usage_values) > 0:
            return np.mean(usage_values)
        return 0
    
    df['historical_monthly_avg'] = df.apply(get_historical_avg, axis=1)
    df['recent_monthly_avg'] = df['usage_last_3_months'] / 3
    
    df['usage_drop_percent'] = ((df['historical_monthly_avg'] - df['recent_monthly_avg']) / 
                                 (df['historical_monthly_avg'] + 0.01) * 100)
    
    minutes_saved = df['Minutes Saved per usage'].fillna(0)
    hourly_rate = df['Client Hourly Rate'].fillna(0)
    df['time_saved_hours_30d'] = df['usage_last_30_days'] * minutes_saved / 60
    df['time_saved_hours_3mo'] = df['usage_last_3_months'] * minutes_saved / 60
    df['time_saved_hours_12mo'] = df['usage_last_12_months'] * minutes_saved / 60
    df['cost_saved_30d'] = df['time_saved_hours_30d'] * hourly_rate
    df['cost_saved_3mo'] = df['time_saved_hours_3mo'] * hourly_rate
    df['cost_saved_12mo'] = df['time_saved_hours_12mo'] * hourly_rate
    df['cumulative_cost_saved'] = df['cost_saved_12mo']
    project_cost = df['Investment'].fillna(0)
    df['project_cost'] = project_cost
    df['roi_net'] = df['cumulative_cost_saved'] - df['project_cost']
    df['roi_reached'] = (df['project_cost'] > 0) & (df['roi_net'] >= 0)
    
    monthly_target = df['Monthly ROI Goal'].fillna(0)
    
    def get_status(row):
        if row['project_cost'] == 0 or monthly_target[row.name] == 0:
            if row['usage_last_30_days'] == 0 and row['usage_last_3_months'] == 0:
                return 'Inactive'
            elif row['usage_last_30_days'] == 0:
                return 'No Recent Usage'
            elif row['usage_drop_percent'] > 50 and row['historical_monthly_avg'] > 5:
                return 'Usage Dropped'
            return 'Active (Config Needed)'
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
        return 'Below Target'
    
    df['roi_status'] = df.apply(get_status, axis=1)
    
    return df
