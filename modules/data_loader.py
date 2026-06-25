"""
Shared data loading - used by both app and run_daily_alerts for consistent metrics
"""
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

MONTHS_FR = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
             'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']


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


def _count_usage(series, value_type, match_value=None):
    """Count usage from a series regardless of dtype (bool, int, object/string)."""
    if value_type == "match":
        return (series == match_value).sum()
    if value_type != "boolean":
        return pd.to_numeric(series, errors='coerce').sum()
    # Handle bool, int (0/1), and object ("True"/"False" strings)
    if series.dtype == bool:
        return series.sum()
    return (series == True).sum()


def load_data(supabase, company_configs, project_metadata=None):
    """Load data from Supabase - same logic as app"""
    if project_metadata is None:
        project_metadata = {}
    all_data = []

    for company_name, company_config in company_configs.items():
        for project_name, project_config in company_config['projects'].items():
            try:
                table_name = project_config['supabase_table']
                usage_field = project_config['usage_field']
                value_type = project_config.get('value_type', 'boolean')
                match_value = project_config.get('match_value')

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

                # Use last weekday so Monday compares Friday, not Sunday
                yesterday = date.today() - timedelta(days=1)
                while yesterday.weekday() >= 5:
                    yesterday -= timedelta(days=1)
                yesterday_records = records_df[records_df['_date'] == yesterday]

                if usage_field in yesterday_records.columns:
                    usage_yesterday = _count_usage(yesterday_records[usage_field], value_type, match_value)
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
                    usage_count = _count_usage(month_records[usage_field], value_type, match_value) if usage_field in month_records.columns else 0
                    monthly_usage[month_name] = usage_count

                project_key = f"{company_config.get('worksheet_name', company_name)}_{project_name}"
                metadata_entry = project_metadata.get(project_key, {})
                usage_type_override = "Matched Companies" if (company_name == "TECHO BLOC" and project_name == "MATCHING") else None

                split_by_field = project_config.get('split_by_field')
                split_financial_row = project_config.get('split_financial_row', '').lower()

                split_values = project_config.get('split_values')

                if split_by_field and split_by_field in records_df.columns:
                    all_sub_values = records_df[split_by_field].dropna().unique()
                    sub_values = [v for v in all_sub_values if split_values is None or v in split_values]
                    if split_values:
                        sub_values = sorted(sub_values, key=lambda v: split_values.index(v) if v in split_values else 999)

                    # Build per-sub-value monthly usage first so we can sum for the total row
                    sub_rows_data = []
                    total_monthly = {MONTHS_FR[i]: 0 for i in range(12)}
                    total_yesterday = 0

                    for sub_val in sub_values:
                        sub_df = records_df[records_df[split_by_field] == sub_val]

                        sub_yesterday = _count_usage(
                            sub_df[sub_df['_date'] == yesterday][usage_field],
                            value_type, match_value
                        ) if usage_field in sub_df.columns else 0
                        total_yesterday += sub_yesterday

                        sub_monthly = {}
                        for month_idx in range(12):
                            month_num = month_idx + 1
                            year = current_year if month_num <= current_month else current_year - 1
                            month_name = MONTHS_FR[month_idx]
                            month_sub = sub_df[
                                (sub_df['_month'] == month_num) & (sub_df['_year'] == year)
                            ]
                            count = _count_usage(month_sub[usage_field], value_type, match_value) if usage_field in month_sub.columns else 0
                            sub_monthly[month_name] = count
                            total_monthly[month_name] += count

                        sub_rows_data.append((sub_val, sub_yesterday, sub_monthly))

                    # Sub-rows only — no aggregated total row.
                    # All shared project-level fields are copied to every sub-row for display.
                    # _split_primary=True only on the first sub-row so investment/ROI are
                    # counted once in dashboard totals, not once per sub-row.
                    for order, (sub_val, sub_yesterday, sub_monthly) in enumerate(sub_rows_data):
                        sub_row = {
                            'COMPANY': company_name,
                            'CLIENT': company_config.get('client_name', company_name),
                            'PROJECT': str(sub_val),
                            'Investment': metadata_entry.get('investment'),
                            'Monthly ROI Goal': metadata_entry.get('monthly_roi_goal'),
                            'Client Hourly Rate': metadata_entry.get('client_hourly_rate'),
                            'Minutes Saved per usage': metadata_entry.get('minutes_saved_per_usage'),
                            'Month Activated': metadata_entry.get('month_activated'),
                            'Usage Type': usage_type_override,
                            'Months Active': None,
                            'usage_yesterday': sub_yesterday,
                            '_hide_roi': True,
                            '_project_group': project_name,
                            '_sort_order': order,
                            '_split_primary': order == 0,
                        }
                        sub_row.update(sub_monthly)
                        all_data.append(sub_row)
                else:
                    project_row = {
                        'COMPANY': company_name,
                        'CLIENT': company_config.get('client_name', company_name),
                        'PROJECT': project_name,
                        'Investment': metadata_entry.get('investment'),
                        'Monthly ROI Goal': metadata_entry.get('monthly_roi_goal'),
                        'Client Hourly Rate': metadata_entry.get('client_hourly_rate'),
                        'Minutes Saved per usage': metadata_entry.get('minutes_saved_per_usage'),
                        'Month Activated': metadata_entry.get('month_activated'),
                        'Usage Type': usage_type_override,
                        'Months Active': None,
                        '_hide_roi': False,
                        '_project_group': project_name,
                        '_sort_order': 0,
                        '_split_primary': True,
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
    """Single source of truth for all metrics — used by both app and email alerts."""
    if df.empty:
        return df

    current_month_idx = datetime.now().month - 1
    available_months = [m for m in MONTHS_FR if m in df.columns]

    df['usage_last_30_days'] = df[MONTHS_FR[current_month_idx]] if MONTHS_FR[current_month_idx] in df.columns else 0

    month_cols_3mo = []
    for i in range(0, 3):
        month_idx = (current_month_idx - i) % 12
        if MONTHS_FR[month_idx] in df.columns:
            month_cols_3mo.append(MONTHS_FR[month_idx])
    df['usage_last_3_months'] = df[month_cols_3mo].sum(axis=1) if month_cols_3mo else 0
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

    prev_month_idx = (current_month_idx - 1) % 12
    if MONTHS_FR[prev_month_idx] in df.columns and MONTHS_FR[current_month_idx] in df.columns:
        df['usage_prev_month'] = df[MONTHS_FR[prev_month_idx]]
        df['mom_usage_percent'] = ((df['usage_last_30_days'] - df['usage_prev_month']) /
                                    (df['usage_prev_month'] + 0.01) * 100)
    else:
        df['usage_prev_month'] = 0
        df['mom_usage_percent'] = 0

    df['trailing_3mo_monthly_avg_usage'] = df['usage_last_3_months'] / 3

    minutes_saved = df['Minutes Saved per usage']
    hourly_rate = df['Client Hourly Rate']
    df['time_saved_hours_30d'] = df['usage_last_30_days'] * minutes_saved / 60
    df['time_saved_hours_3mo'] = df['usage_last_3_months'] * minutes_saved / 60
    df['time_saved_hours_12mo'] = df['usage_last_12_months'] * minutes_saved / 60
    df['cost_saved_30d'] = df['time_saved_hours_30d'] * hourly_rate
    df['cost_saved_3mo'] = df['time_saved_hours_3mo'] * hourly_rate
    df['cost_saved_12mo'] = df['time_saved_hours_12mo'] * hourly_rate
    df['cumulative_cost_saved'] = df['cost_saved_12mo']

    project_cost = df['Investment'].fillna(0)
    df['project_cost'] = project_cost
    df['roi_net'] = df['cumulative_cost_saved'] - project_cost
    df['roi_reached'] = (project_cost > 0) & (df['roi_net'] >= 0)
    df['roi_progress_percent'] = (df['roi_net'] / project_cost * 100).where(project_cost > 0)

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

    def estimate_breakeven(row):
        if row['roi_reached']:
            return "ROI Reached"
        if pd.isna(row['cost_saved_3mo']) or row['cost_saved_3mo'] <= 0:
            if row['usage_last_12_months'] > 0:
                return "Was active, now inactive"
            else:
                return "Never used"
        monthly_avg = row['cost_saved_3mo'] / 3
        if monthly_avg < 10 and row['historical_monthly_avg'] > monthly_avg * 10:
            return f"~{((row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg):.0f} months (project appears abandoned)"
        elif monthly_avg < 50:
            return f"{((row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg):.0f} months (very low usage)"
        months_to_break_even = (row['project_cost'] - row['cumulative_cost_saved']) / monthly_avg
        if months_to_break_even > 100:
            return f"{months_to_break_even:.0f} months (needs attention)"
        elif months_to_break_even > 24:
            return f"{months_to_break_even:.1f} months"
        return f"{months_to_break_even:.1f} months"

    df['breakeven_estimate'] = df.apply(estimate_breakeven, axis=1)

    return df
