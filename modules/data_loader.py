"""
Shared data loading - used by both app and run_daily_alerts for consistent metrics
"""
import re
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


def _load_manual_data(supabase, project_metadata):
    """Load data for manually-tracked projects (manual_projects + manual_daily_usage tables)."""
    try:
        manual_projects = supabase.table("manual_projects").select("*").execute().data or []
        if not manual_projects:
            return []

        all_usage = supabase.table("manual_daily_usage").select("*").execute().data or []

        usage_by_key = {}
        for entry in all_usage:
            key = entry["project_key"]
            if key not in usage_by_key:
                usage_by_key[key] = []
            usage_by_key[key].append(entry)

        current_year = date.today().year
        current_month = date.today().month
        yesterday = date.today() - timedelta(days=1)
        while yesterday.weekday() >= 5:
            yesterday -= timedelta(days=1)

        rows = []
        for mp in manual_projects:
            company_name = mp["company_name"]
            client_name = mp.get("client_name", company_name)
            project_name = mp["project_name"]
            worksheet_name = mp.get("worksheet_name", company_name)
            project_key = f"{worksheet_name}_{project_name}"

            entries = usage_by_key.get(project_key, [])
            metadata_entry = project_metadata.get(project_key, {})

            usage_by_date = {}
            for entry in entries:
                try:
                    d = pd.to_datetime(entry["date"]).date()
                    usage_by_date[d] = int(entry.get("usage_count", 0))
                except Exception:
                    continue

            usage_yesterday = usage_by_date.get(yesterday, 0)

            # Determine display start month
            month_activated_str = metadata_entry.get('month_activated')
            forced_start = None
            if month_activated_str:
                try:
                    fmt = '%Y-%m-%d' if len(month_activated_str) > 7 else '%Y-%m'
                    act = datetime.strptime(month_activated_str, fmt)
                    forced_start = (act.year, act.month)
                except Exception:
                    pass

            if forced_start:
                m_yr, m_mo = forced_start
            elif usage_by_date:
                min_d = min(usage_by_date.keys())
                m_yr, m_mo = min_d.year, min_d.month
            else:
                m_yr, m_mo = current_year, current_month

            monthly_usage = {}
            while (m_yr, m_mo) <= (current_year, current_month):
                col_name = f"{MONTHS_FR[m_mo - 1]} {m_yr}"
                count = sum(
                    v for d, v in usage_by_date.items()
                    if d.month == m_mo and d.year == m_yr
                )
                monthly_usage[col_name] = count
                m_mo += 1
                if m_mo > 12:
                    m_mo = 1
                    m_yr += 1

            # If no forced start, trim leading zero-usage months
            if not forced_start:
                _sorted_cols = sorted(
                    monthly_usage.keys(),
                    key=lambda c: next(
                        (int(c[len(mn) + 1:]) * 12 + i
                         for i, mn in enumerate(MONTHS_FR) if c.startswith(mn + ' ')),
                        999999
                    )
                )
                first_nz = next((i for i, c in enumerate(_sorted_cols) if monthly_usage[c] > 0), None)
                if first_nz is not None and first_nz > 0:
                    for c in _sorted_cols[:first_nz]:
                        del monthly_usage[c]

            project_row = {
                'COMPANY': company_name,
                'CLIENT': client_name,
                'PROJECT': project_name,
                'Investment': metadata_entry.get('investment'),
                'Monthly ROI Goal': metadata_entry.get('monthly_roi_goal'),
                'Client Hourly Rate': metadata_entry.get('client_hourly_rate'),
                'Minutes Saved per usage': metadata_entry.get('minutes_saved_per_usage'),
                'Month Activated': metadata_entry.get('month_activated'),
                'Usage Type': None,
                'Months Active': None,
                '_hide_roi': False,
                '_project_group': project_name,
                '_sort_order': 0,
                '_split_primary': True,
                'usage_yesterday': usage_yesterday,
                'usage_all_time': sum(usage_by_date.values()),
            }
            project_row.update(monthly_usage)
            rows.append(project_row)

        return rows
    except Exception as e:
        print(f"_load_manual_data error: {e}")
        return []


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

                project_key = f"{company_config.get('worksheet_name', company_name)}_{project_name}"
                metadata_entry = project_metadata.get(project_key, {})

                # Determine display start month
                month_activated_str = metadata_entry.get('month_activated')
                forced_start = None
                if month_activated_str:
                    try:
                        fmt = '%Y-%m-%d' if len(month_activated_str) > 7 else '%Y-%m'
                        act = datetime.strptime(month_activated_str, fmt)
                        forced_start = (act.year, act.month)
                    except Exception:
                        pass

                if forced_start:
                    start_year, start_month = forced_start
                elif not records_df.empty:
                    min_date = records_df[date_col].min()
                    start_year, start_month = min_date.year, min_date.month
                else:
                    start_year, start_month = current_year, current_month

                # Build monthly usage for ALL months from start to now
                monthly_usage = {}
                yr, mo = start_year, start_month
                while (yr, mo) <= (current_year, current_month):
                    col_name = f"{MONTHS_FR[mo - 1]} {yr}"
                    month_records = records_df[
                        (records_df['_month'] == mo) & (records_df['_year'] == yr)
                    ]
                    usage_count = _count_usage(month_records[usage_field], value_type, match_value) if usage_field in month_records.columns else 0
                    monthly_usage[col_name] = usage_count
                    mo += 1
                    if mo > 12:
                        mo = 1
                        yr += 1

                # Apply manual monthly overrides (infer year using rolling logic for backward compat)
                manual_overrides = project_config.get('manual_monthly_overrides', {})
                for month_name, extra_count in manual_overrides.items():
                    if month_name in MONTHS_FR:
                        mo_num = MONTHS_FR.index(month_name) + 1
                        override_year = current_year if mo_num <= current_month else current_year - 1
                        col_name = f"{month_name} {override_year}"
                        monthly_usage[col_name] = monthly_usage.get(col_name, 0) + extra_count

                # If no forced start, trim leading zero-usage months
                if not forced_start:
                    _sorted_cols = sorted(
                        monthly_usage.keys(),
                        key=lambda c: next(
                            (int(c[len(mn) + 1:]) * 12 + i
                             for i, mn in enumerate(MONTHS_FR) if c.startswith(mn + ' ')),
                            999999
                        )
                    )
                    first_nz = next((i for i, c in enumerate(_sorted_cols) if monthly_usage[c] > 0), None)
                    if first_nz is not None and first_nz > 0:
                        for c in _sorted_cols[:first_nz]:
                            del monthly_usage[c]
                usage_type_override = "Matched Companies" if (company_name == "TECHO BLOC" and project_name == "MATCHING") else None

                split_by_field = project_config.get('split_by_field')
                split_financial_row = project_config.get('split_financial_row', '').lower()

                split_values = project_config.get('split_values')
                split_display_names = project_config.get('split_display_names', {})

                if split_by_field and split_by_field in records_df.columns:
                    all_sub_values = records_df[split_by_field].dropna().unique()
                    sub_values = [v for v in all_sub_values if split_values is None or v in split_values]
                    if split_values:
                        sub_values = sorted(sub_values, key=lambda v: split_values.index(v) if v in split_values else 999)

                    # Sub-rows only — no aggregated total row.
                    # Each sub-row has its own metadata entry keyed by worksheet_name + sub_val,
                    # so individual investments/rates can be configured per sub-project.
                    # Falls back to the parent project entry if no sub-specific entry exists.
                    worksheet_name = company_config.get('worksheet_name', company_name)
                    split_manual_monthly  = project_config.get('split_manual_monthly_overrides', {})
                    split_manual_historical = project_config.get('split_manual_historical_extra', {})
                    total_monthly = {}
                    total_yesterday = 0

                    for order, sub_val in enumerate(sub_values):
                        sub_df = records_df[records_df[split_by_field] == sub_val]
                        display_name = split_display_names.get(str(sub_val), str(sub_val))
                        sub_key = f"{worksheet_name}_{sub_val}"
                        sub_meta = project_metadata.get(sub_key, metadata_entry)

                        sub_yesterday = _count_usage(
                            sub_df[sub_df['_date'] == yesterday][usage_field],
                            value_type, match_value
                        ) if usage_field in sub_df.columns else 0
                        total_yesterday += sub_yesterday

                        # Determine start month for this sub-project
                        sub_month_activated_str = sub_meta.get('month_activated')
                        sub_forced_start = None
                        if sub_month_activated_str:
                            try:
                                fmt = '%Y-%m-%d' if len(sub_month_activated_str) > 7 else '%Y-%m'
                                act = datetime.strptime(sub_month_activated_str, fmt)
                                sub_forced_start = (act.year, act.month)
                            except Exception:
                                pass

                        if sub_forced_start:
                            sub_start_yr, sub_start_mo = sub_forced_start
                        elif not sub_df.empty:
                            sub_min = sub_df[date_col].min()
                            sub_start_yr, sub_start_mo = sub_min.year, sub_min.month
                        else:
                            sub_start_yr, sub_start_mo = current_year, current_month

                        sub_monthly = {}
                        s_yr, s_mo = sub_start_yr, sub_start_mo
                        while (s_yr, s_mo) <= (current_year, current_month):
                            col_name = f"{MONTHS_FR[s_mo - 1]} {s_yr}"
                            month_sub = sub_df[
                                (sub_df['_month'] == s_mo) & (sub_df['_year'] == s_yr)
                            ]
                            count = _count_usage(month_sub[usage_field], value_type, match_value) if usage_field in month_sub.columns else 0
                            sub_monthly[col_name] = count
                            total_monthly[col_name] = total_monthly.get(col_name, 0) + count
                            s_mo += 1
                            if s_mo > 12:
                                s_mo = 1
                                s_yr += 1

                        # Apply per-sub monthly overrides to display columns (infer year)
                        sub_overrides = split_manual_monthly.get(str(sub_val), {})
                        for month_name, extra_count in sub_overrides.items():
                            if month_name in MONTHS_FR:
                                mo_num = MONTHS_FR.index(month_name) + 1
                                override_year = current_year if mo_num <= current_month else current_year - 1
                                col_name = f"{month_name} {override_year}"
                                sub_monthly[col_name] = sub_monthly.get(col_name, 0) + extra_count

                        # If no forced start, trim leading zero-usage months
                        if not sub_forced_start:
                            _sorted_sub_cols = sorted(
                                sub_monthly.keys(),
                                key=lambda c: next(
                                    (int(c[len(mn) + 1:]) * 12 + i
                                     for i, mn in enumerate(MONTHS_FR) if c.startswith(mn + ' ')),
                                    999999
                                )
                            )
                            first_nz = next((i for i, c in enumerate(_sorted_sub_cols) if sub_monthly[c] > 0), None)
                            if first_nz is not None and first_nz > 0:
                                for c in _sorted_sub_cols[:first_nz]:
                                    del sub_monthly[c]

                        # All-time for this sub-project
                        sub_all_time = _count_usage(sub_df[usage_field], value_type, match_value) if usage_field in sub_df.columns else 0
                        sub_all_time += sum(sub_overrides.values())
                        sub_all_time += split_manual_historical.get(str(sub_val), 0)

                        sub_row = {
                            'COMPANY': company_name,
                            'CLIENT': company_config.get('client_name', company_name),
                            'PROJECT': display_name,
                            '_split_db_value': str(sub_val),
                            'Investment': sub_meta.get('investment'),
                            'Monthly ROI Goal': sub_meta.get('monthly_roi_goal'),
                            'Client Hourly Rate': sub_meta.get('client_hourly_rate'),
                            'Minutes Saved per usage': sub_meta.get('minutes_saved_per_usage'),
                            'Month Activated': sub_meta.get('month_activated'),
                            'Usage Type': usage_type_override,
                            'Months Active': None,
                            'usage_yesterday': sub_yesterday,
                            '_hide_roi': True,
                            '_project_group': project_name,
                            '_sort_order': order,
                            '_split_primary': True,
                            'usage_all_time': int(sub_all_time),
                        }
                        sub_row.update(sub_monthly)
                        all_data.append(sub_row)
                else:
                    # All-time usage: all DB rows + overrides (no date filter)
                    all_time_usage = _count_usage(records_df[usage_field], value_type, match_value) if usage_field in records_df.columns else 0
                    all_time_usage += sum(project_config.get('manual_monthly_overrides', {}).values())
                    all_time_usage += project_config.get('manual_historical_extra', 0)

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
                        'usage_all_time': int(all_time_usage),
                    }
                    project_row.update(monthly_usage)
                    all_data.append(project_row)
                
            except Exception as e:
                print(f"Error: {company_name} - {project_name}: {e}")
                continue

    # Load manually-tracked project data
    all_data.extend(_load_manual_data(supabase, project_metadata))

    if all_data:
        return pd.DataFrame(all_data)
    return pd.DataFrame()


def calculate_metrics(df):
    """Single source of truth for all metrics — used by both app and email alerts."""
    if df.empty:
        return df

    import re
    now = datetime.now()
    current_year  = now.year
    current_month = now.month

    # Detect all year-qualified month columns and sort chronologically
    _month_re = re.compile(r'^(' + '|'.join(MONTHS_FR) + r') (\d{4})$')
    def _parse_col(col):
        m = _month_re.match(col)
        if m:
            mo_num = MONTHS_FR.index(m.group(1)) + 1
            yr     = int(m.group(2))
            return (yr, mo_num, col)
        return None

    all_month_cols_info = sorted(
        filter(None, (_parse_col(c) for c in df.columns)),
        key=lambda x: (x[0], x[1]),
    )
    all_month_cols = [col for (_, _, col) in all_month_cols_info]

    # Helpers to get column name for a given (year, month_num)
    def _col(yr, mo):
        return f"{MONTHS_FR[mo - 1]} {yr}"

    current_col  = _col(current_year, current_month)
    prev_mo      = current_month - 1 if current_month > 1 else 12
    prev_yr      = current_year if current_month > 1 else current_year - 1
    prev_col     = _col(prev_yr, prev_mo)

    # last-3-months columns (current + prev 2)
    last_3_info  = [(yr, mo, col) for (yr, mo, col) in all_month_cols_info
                    if (yr * 12 + mo) >= (current_year * 12 + current_month - 2)
                    and (yr * 12 + mo) <= (current_year * 12 + current_month)]
    last_3_cols  = [col for (_, _, col) in last_3_info]

    # last-12-months columns
    last_12_info = [(yr, mo, col) for (yr, mo, col) in all_month_cols_info
                    if (yr * 12 + mo) >= (current_year * 12 + current_month - 11)
                    and (yr * 12 + mo) <= (current_year * 12 + current_month)]
    last_12_cols = [col for (_, _, col) in last_12_info]

    df['usage_this_month']    = df[current_col] if current_col in df.columns else 0
    df['usage_last_3_months'] = df[last_3_cols].sum(axis=1)  if last_3_cols  else 0
    df['usage_last_12_months']= df[last_12_cols].sum(axis=1) if last_12_cols else 0

    def get_historical_avg(row):
        usage_values = [row[c] for c in all_month_cols if pd.notna(row.get(c)) and row.get(c, 0) > 0]
        if len(usage_values) >= 6:
            return np.mean(usage_values[:6])
        elif len(usage_values) > 0:
            return np.mean(usage_values)
        return 0

    df['historical_monthly_avg'] = df.apply(get_historical_avg, axis=1)
    df['recent_monthly_avg']     = df['usage_last_3_months'] / 3
    df['usage_drop_percent']     = (
        (df['historical_monthly_avg'] - df['recent_monthly_avg']) /
        (df['historical_monthly_avg'] + 0.01) * 100
    )

    # Treat missing prev_col as 0 so MoM color still works when leading zeros were trimmed
    df['usage_prev_month'] = df[prev_col].fillna(0) if prev_col in df.columns else 0
    df['mom_usage_percent'] = (
        (df['usage_this_month'] - df['usage_prev_month']) /
        (df['usage_prev_month'] + 0.01) * 100
    )

    df['trailing_3mo_monthly_avg_usage'] = df['usage_last_3_months'] / 3

    minutes_saved = df['Minutes Saved per usage']
    hourly_rate   = df['Client Hourly Rate']
    df['time_saved_hours_this_month'] = df['usage_this_month']     * minutes_saved / 60
    df['time_saved_hours_3mo']        = df['usage_last_3_months']  * minutes_saved / 60
    df['time_saved_hours_12mo']       = df['usage_last_12_months'] * minutes_saved / 60
    df['cost_saved_this_month']       = df['time_saved_hours_this_month'] * hourly_rate
    df['cost_saved_3mo']              = df['time_saved_hours_3mo']        * hourly_rate
    df['cost_saved_12mo']             = df['time_saved_hours_12mo']       * hourly_rate
    # Use all-time usage for cumulative ROI (true since-launch total)
    all_time_usage = df['usage_all_time'] if 'usage_all_time' in df.columns else df['usage_last_12_months']
    df['cumulative_cost_saved']       = all_time_usage * minutes_saved / 60 * hourly_rate

    project_cost = df['Investment'].fillna(0)
    df['project_cost']         = project_cost
    df['roi_net']              = df['cumulative_cost_saved'] - project_cost
    df['roi_reached']          = (project_cost > 0) & (df['roi_net'] >= 0)
    df['roi_progress_percent'] = df['cumulative_cost_saved'] / project_cost.replace(0, np.nan) * 100

    monthly_target = df['Monthly ROI Goal'].fillna(0)
    df['mo_roi_pct'] = df['cost_saved_this_month'] / monthly_target.replace(0, np.nan) * 100

    df['tag_active']        = df['usage_this_month'] > 0
    df['tag_no_recent']     = (df['usage_this_month'] == 0) & (df['usage_last_3_months'] > 0)
    df['tag_inactive']      = (df['usage_this_month'] == 0) & (df['usage_last_3_months'] == 0)

    has_investment = project_cost > 0
    has_target     = monthly_target > 0
    df['tag_no_config']     = ~has_investment
    df['tag_roi_reached']   = df['roi_reached']
    df['tag_usage_dropped'] = (df['usage_drop_percent'] > 50) & (df['historical_monthly_avg'] > 5)
    df['tag_above_target']  = has_investment & has_target & (df['cost_saved_this_month'] >= monthly_target)
    df['tag_below_target']  = has_investment & has_target & (df['cost_saved_this_month'] < monthly_target)
    df['tag_no_target']     = has_investment & ~has_target & ~df['roi_reached']

    def _activity_status(row):
        if row['tag_active']:    return 'Active'
        if row['tag_no_recent']: return 'No Recent Usage'
        return 'Inactive'

    def _roi_status(row):
        if row['tag_no_config']:   return 'No Config'
        if row['tag_roi_reached']: return 'ROI Reached'
        if row['tag_usage_dropped'] and row['tag_below_target']: return 'Usage Dropped + Below Mo. Target'
        if row['tag_usage_dropped']: return 'Usage Dropped'
        if row['tag_above_target']:  return 'Above Mo. Target'
        if row['tag_below_target']:  return 'Below Mo. Target'
        if row['tag_no_target']:     return 'No Target'
        return '—'

    df['activity_status'] = df.apply(_activity_status, axis=1)
    df['roi_status']      = df.apply(_roi_status, axis=1)

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
