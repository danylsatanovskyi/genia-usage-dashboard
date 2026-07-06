"""
Genia Usage Dashboard — Dash rewrite
Replaces the Streamlit app.py without touching it.
"""

import os
import json
import math
import secrets
import numpy as np
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from flask import session, redirect, request, render_template_string

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, COMPANY_CONFIGS
from modules.data_loader import load_data, calculate_metrics, MONTHS_FR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BRAND = "#00c4ce"
DARK = "#13100d"
BG = "#f8f9fa"
# Metadata and hidden projects are stored in Supabase (see project_metadata / hidden_projects tables)

# ---------------------------------------------------------------------------
# Helpers — metadata / hidden projects
# ---------------------------------------------------------------------------

def _sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def load_project_metadata():
    try:
        rows = _sb().table("project_metadata").select("*").execute().data
        return {r["key"]: {k: v for k, v in r.items() if k != "key"} for r in rows}
    except Exception as e:
        print(f"load_project_metadata error: {e}")
        return {}


def save_project_metadata(metadata):
    try:
        rows = [{"key": k, **{fk: fv for fk, fv in v.items()}} for k, v in metadata.items()]
        _sb().table("project_metadata").upsert(rows).execute()
    except Exception as e:
        print(f"save_project_metadata error: {e}")


def load_hidden_projects():
    try:
        rows = _sb().table("hidden_projects").select("project_name").execute().data
        return [r["project_name"] for r in rows]
    except Exception as e:
        print(f"load_hidden_projects error: {e}")
        return []


def hide_project(project_name):
    try:
        _sb().table("hidden_projects").upsert({"project_name": project_name}).execute()
    except Exception as e:
        print(f"hide_project error: {e}")


def unhide_project(project_name):
    try:
        _sb().table("hidden_projects").delete().eq("project_name", project_name).execute()
    except Exception as e:
        print(f"unhide_project error: {e}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_dataframe():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    metadata = load_project_metadata()
    df = load_data(supabase, COMPANY_CONFIGS, metadata)
    if not df.empty:
        df = calculate_metrics(df)
    return df


def df_to_store(df):
    if df is None or df.empty:
        return None
    return df.to_json(orient="split", date_format="iso")


def df_from_store(store_data):
    if not store_data:
        return pd.DataFrame()
    import io
    return pd.read_json(io.StringIO(store_data), orient="split")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _isna(val):
    """True if val is None or any flavour of NaN/inf that pandas may produce."""
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    return False


def _safe_num(val, default=0):
    """Return a plain float, coercing None/NaN/non-numeric to *default*.

    Pandas cells can arrive as float NaN (which is truthy!), numpy scalars,
    or plain Python numbers.  Always use this instead of ``val or default``
    when the value comes from a DataFrame row.
    """
    if _isna(val):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def fmt_currency(val):
    if _isna(val):
        return ""
    return f"${val:,.0f}"


def fmt_hours(val):
    if _isna(val):
        return ""
    return f"{val:.1f}h"


def fmt_mom(curr, prev, month_activated=None):
    if curr == 0 and prev == 0:
        return "–"
    if prev == 0 and curr > 0:
        # Only label "New" if the project was activated within the last 2 months
        if isinstance(month_activated, str) and month_activated:
            try:
                from datetime import datetime as dt, date
                activated = dt.strptime(month_activated, "%Y-%m").date().replace(day=1)
                today = date.today()
                months_since = (today.year - activated.year) * 12 + (today.month - activated.month)
                if months_since <= 2:
                    return "New"
            except ValueError:
                pass
        return "↑ from 0"
    pct = (curr - prev) / (prev + 0.01) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}%"


def fmt_roi(val):
    if _isna(val):
        return "N/A"
    return f"{val:.0f}%"


def fmt_activated(val):
    # NaN is truthy in Python, so guard with isinstance rather than truthiness
    if not isinstance(val, str) or not val:
        return ""
    return val[:7]


# ---------------------------------------------------------------------------
# Row color by roi_status
# ---------------------------------------------------------------------------

ACTIVITY_CHIP = {
    "Active":          ("#d4edda", "#155724"),
    "No Recent Usage": ("#fff3cd", "#856404"),
    "Inactive":        ("#e2e3e5", "#383d41"),
}

ROI_CHIP = {
    "ROI Reached":  ("#d4edda", "#155724"),
    "Above Mo. Target": ("#c3e6cb", "#155724"),
    "Below Mo. Target": ("#f8d7da", "#721c24"),
    "Usage Dropped":("#f8d7da", "#721c24"),
    "No Target":    ("#e8f4f8", "#0c5460"),
    "No Config":    ("#e2e3e5", "#383d41"),
}

# Keep for modal title badge
STATUS_BG = {**{k: v[0] for k, v in ACTIVITY_CHIP.items()}, **{k: v[0] for k, v in ROI_CHIP.items()}}


# ---------------------------------------------------------------------------
# Build AgGrid column defs and row data from a DataFrame
# ---------------------------------------------------------------------------

def build_grid_data(df):
    if df.empty:
        return [], []

    rows = []
    for _, row in df.iterrows():
        curr  = _safe_num(row.get("usage_this_month"))
        prev  = _safe_num(row.get("usage_prev_month"))
        # Month Activated must be a str for strptime; NaN is truthy so don't use `or`
        month_activated = row.get("Month Activated")
        if not isinstance(month_activated, str):
            month_activated = None
        status   = row.get("roi_status", "") or ""
        hide_roi = bool(row.get("_hide_roi", False))

        mo_target  = row.get("Monthly ROI Goal")
        mo_roi_raw = row.get("mo_roi_pct")

        u3   = int(_safe_num(row.get("usage_last_3_months")))
        u12  = int(_safe_num(row.get("usage_last_12_months")))
        prev_hrs = _safe_num(row.get("usage_prev_month")) * _safe_num(row.get("Minutes Saved per usage")) / 60
        proj_cost = _safe_num(row.get("project_cost"))

        # YTD: Jan 1 → current month inclusive
        import datetime as _dt
        _now = _dt.date.today()
        _ytd_months = MONTHS_FR[:_now.month]
        _mins_saved  = _safe_num(row.get("Minutes Saved per usage"))
        _hourly_rate = _safe_num(row.get("Client Hourly Rate"))
        _ytd_usage_raw  = sum(_safe_num(row.get(m, 0)) for m in _ytd_months)
        _ytd_hrs_raw    = _ytd_usage_raw * _mins_saved / 60
        _ytd_saved_raw  = _ytd_hrs_raw * _hourly_rate

        rows.append({
            "_id":              str(_),
            "_roi_status":      status,
            "_activity_status": row.get("activity_status", "") or "",
            "_hide_roi":        hide_roi,
            "Client":           row.get("CLIENT", "") or "",
            "Project":          row.get("PROJECT", "") or "",
            "Activated":        fmt_activated(row.get("Month Activated")),
            "Mo Target":        fmt_currency(mo_target) if not _isna(mo_target) and mo_target else "",
            "1 mo":             int(curr),
            "MoM %":            fmt_mom(curr, prev, month_activated),
            "Mo ROI %":         fmt_roi(mo_roi_raw),
            "_mo_roi_pct_raw":  None if _isna(mo_roi_raw) else mo_roi_raw,
            "3 mo":             u3,
            "12 mo":            u12,
            "Hrs This Mo":      fmt_hours(row.get("time_saved_hours_this_month")),
            "Hrs 12mo":         fmt_hours(row.get("time_saved_hours_12mo")),
            "Investment":       fmt_currency(proj_cost) if proj_cost else "",
            "Total Saved":      fmt_currency(row.get("cumulative_cost_saved")),
            "ROI %":            fmt_roi(row.get("roi_progress_percent")),
            # Raw values for the detail panel
            "_usage_1mo":       f"{int(curr)} usages",
            "_usage_3mo":       f"{u3} usages",
            "_usage_12mo":      f"{u12} usages",
            "_mom_pct":         fmt_mom(curr, prev, month_activated),
            "_hrs_this_mo":     fmt_hours(row.get("time_saved_hours_this_month")),
            "_hrs_prev_mo":     fmt_hours(prev_hrs),
            "_hrs_12mo":        fmt_hours(row.get("time_saved_hours_12mo")),
            "_investment":      fmt_currency(proj_cost) if proj_cost else "—",
            "_saved_this_mo":   fmt_currency(row.get("cost_saved_this_month")) or "—",
            "_total_saved":     fmt_currency(row.get("cumulative_cost_saved")),
            "_mo_target":       fmt_currency(mo_target) if not _isna(mo_target) and mo_target else "—",
            "_roi_pct":         fmt_roi(row.get("roi_progress_percent")),
            "_roi_pct_raw":     None if _isna(row.get("roi_progress_percent")) else row.get("roi_progress_percent"),
            "_mom_pct_raw":     None if _isna(row.get("mom_usage_percent")) else row.get("mom_usage_percent"),
            "_breakeven":           row.get("breakeven_estimate", "") or "",
            "_project_group":       row.get("_project_group", "") or "",
            "_client":              row.get("CLIENT", "") or "",
            # YTD (Jan 1 → current month)
            "_ytd_usage":           int(_ytd_usage_raw),
            "_ytd_hrs":             fmt_hours(_ytd_hrs_raw),
            "_ytd_saved":           fmt_currency(_ytd_saved_raw) if _ytd_saved_raw else "—",
            # Raw numerics for sort presets
            "_usage_1mo_raw":       curr,
            "_total_saved_raw":     _safe_num(row.get("cumulative_cost_saved")),
            "_usage_drop_pct_raw":  _safe_num(row.get("usage_drop_percent")),
            # Boolean ROI tags for multi-chip column
            "_tag_roi_reached":  bool(row.get("tag_roi_reached", False)),
            "_tag_usage_dropped":bool(row.get("tag_usage_dropped", False)),
            "_tag_above_target": bool(row.get("tag_above_target", False)),
            "_tag_below_target": bool(row.get("tag_below_target", False)),
            "_tag_no_target":    bool(row.get("tag_no_target", False)),
            "_tag_no_config":    bool(row.get("tag_no_config", False)),
        })

    col_defs = [
        {"field": "Client",      "sortable": True, "flex": 2, "minWidth": 120},
        {"field": "Project",     "sortable": True, "flex": 2, "minWidth": 130,
         "cellStyle": {"function": "return params.data._hide_roi ? {paddingLeft: '28px'} : {}"}},
        {"field": "Activated",   "sortable": True, "flex": 1, "minWidth": 100},
        {"field": "Active?",     "sortable": True, "flex": 1, "minWidth": 75,
         "cellStyle": {"function": "params.data['Active?'] === 'Yes' ? {color: '#2e7d32', fontWeight: '600'} : {color: '#c62828', fontWeight: '600'}"}},
        {"field": "Mo Target",   "sortable": True, "flex": 1, "minWidth": 100},
        {"field": "1 mo",        "sortable": True, "flex": 1, "minWidth": 65,  "type": "numericColumn"},
        {"field": "MoM %",       "sortable": True, "flex": 1, "minWidth": 75,
         "cellStyle": {"function": "params.data._mom_pct_raw == null ? {} : params.data._mom_pct_raw > 0 ? {background: '#d4edda', fontWeight: '600'} : params.data._mom_pct_raw < 0 ? {background: '#f8d7da', fontWeight: '600'} : {}"}},
        {"field": "Mo ROI %",    "sortable": True, "flex": 1, "minWidth": 85,
         "cellStyle": {"function": "params.data._mo_roi_pct_raw == null || isNaN(params.data._mo_roi_pct_raw) ? {} : params.data._mo_roi_pct_raw >= 100 ? {background: '#d4edda', fontWeight: '600'} : params.data._mo_roi_pct_raw >= 70 ? {background: '#fff3cd', fontWeight: '600'} : {background: '#f8d7da', fontWeight: '600'}"}},
        {"field": "3 mo",        "sortable": True, "flex": 1, "minWidth": 65,  "type": "numericColumn"},
        {"field": "12 mo",       "sortable": True, "flex": 1, "minWidth": 65,  "type": "numericColumn"},
        {"field": "Hrs This Mo", "sortable": True, "flex": 1, "minWidth": 100},
        {"field": "Hrs 12mo",    "sortable": True, "flex": 1, "minWidth": 90},
        {"field": "Investment",  "sortable": True, "flex": 1, "minWidth": 100},
        {"field": "Total Saved", "sortable": True, "flex": 1, "minWidth": 105},
        {"field": "ROI %",       "sortable": True, "flex": 1, "minWidth": 75,
         "cellStyle": {"function": "params.data._roi_pct_raw == null ? {} : params.data._roi_pct_raw >= 100 ? {background: '#d4edda', fontWeight: '600'} : params.data._roi_pct_raw >= 70 ? {background: '#fff3cd', fontWeight: '600'} : {background: '#f8d7da', fontWeight: '600'}"}},
    ]

    return col_defs, rows


def build_client_table(client_rows):
    """Render a client's projects as a styled HTML table with a details button per row."""
    import math as _math

    th_style = {
        "fontSize": "11px", "fontWeight": "700", "color": "#888",
        "padding": "8px 12px", "borderBottom": "2px solid #eee",
        "background": "#f8f9fa", "textTransform": "uppercase", "letterSpacing": "0.4px",
    }
    td_base = {"padding": "10px 12px", "fontSize": "13px", "verticalAlign": "middle", "borderBottom": "1px solid #f3f3f3"}

    headers = html.Thead(html.Tr([
        html.Th("Project",          style=th_style),
        html.Th("Activated",        style={**th_style, "textAlign": "center"}),
        html.Th("Activity",         style={**th_style, "textAlign": "center"}),
        html.Th("ROI & Performance",style={**th_style, "textAlign": "left"}),
        html.Th("1 mo",             style={**th_style, "textAlign": "right"}),
        html.Th("MoM %",            style={**th_style, "textAlign": "center"}),
        html.Th("Mo ROI %",         style={**th_style, "textAlign": "center"}),
        html.Th("ROI %",            style={**th_style, "textAlign": "center"}),
        html.Th("",                 style=th_style),
    ]))

    def _nan(v):
        return v is None or (isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)))

    def _chip(label, color_map):
        bg, fg = color_map.get(label, ("#e2e3e5", "#383d41"))
        return html.Span(label, style={
            "background": bg, "color": fg,
            "fontSize": "10px", "fontWeight": "700",
            "padding": "2px 8px", "borderRadius": "4px",
            "whiteSpace": "nowrap", "display": "inline-block",
        })

    ROI_TAG_MAP = [
        ("_tag_roi_reached",  "ROI Reached"),
        ("_tag_above_target", "Above Mo. Target"),
        ("_tag_below_target", "Below Mo. Target"),
        ("_tag_usage_dropped","Usage Dropped"),
        ("_tag_no_target",    "No Target"),
        ("_tag_no_config",    "No Config"),
    ]

    data_rows = []
    for row in client_rows:
        roi_status      = row.get("_roi_status", "")
        activity_status = row.get("_activity_status", "")
        hide_roi        = row.get("_hide_roi", False)

        border_color = ACTIVITY_CHIP.get(activity_status, ("#e2e3e5", "#383d41"))[0]

        # Build ROI performance chips — include every tag that is True
        roi_chips = html.Div(
            [_chip(label, ROI_CHIP) for key, label in ROI_TAG_MAP if row.get(key)],
            style={"display": "flex", "flexDirection": "column", "gap": "3px", "alignItems": "flex-start"},
        )

        mom_raw = row.get("_mom_pct_raw")
        mom_bg  = "transparent" if _nan(mom_raw) else ("#d4edda" if mom_raw > 0 else "#f8d7da" if mom_raw < 0 else "transparent")

        mr_raw  = row.get("_mo_roi_pct_raw")
        mr_bg   = "transparent" if _nan(mr_raw) else ("#d4edda" if mr_raw >= 100 else "#f8d7da")

        roi_bg  = "#d4edda" if row.get("_tag_roi_reached") else (
                  "#f8d7da" if not _nan(row.get("_roi_pct_raw")) else "transparent"
        )

        project_key = f"{row.get('_client', '')}___{row.get('Project', '')}"

        ytd_usage  = row.get("_ytd_usage", "—")
        ytd_hrs    = row.get("_ytd_hrs",   "—") or "—"
        ytd_saved  = row.get("_ytd_saved", "—") or "—"

        quick_view_row = html.Tr(
            html.Td(
                html.Div([
                    html.Div([
                        html.Div("YTD Usage",  style={"fontSize": "10px", "color": "#888", "marginBottom": "3px", "textTransform": "uppercase", "letterSpacing": "0.4px"}),
                        html.Div(str(ytd_usage),  style={"fontSize": "16px", "fontWeight": "700", "color": "#222"}),
                    ], style={"textAlign": "center", "padding": "0 24px", "borderRight": "1px solid #e0f5f5"}),
                    html.Div([
                        html.Div("YTD Hours Saved",  style={"fontSize": "10px", "color": "#888", "marginBottom": "3px", "textTransform": "uppercase", "letterSpacing": "0.4px"}),
                        html.Div(str(ytd_hrs),    style={"fontSize": "16px", "fontWeight": "700", "color": "#00838f"}),
                    ], style={"textAlign": "center", "padding": "0 24px", "borderRight": "1px solid #e0f5f5"}),
                    html.Div([
                        html.Div("YTD Money Saved",  style={"fontSize": "10px", "color": "#888", "marginBottom": "3px", "textTransform": "uppercase", "letterSpacing": "0.4px"}),
                        html.Div(str(ytd_saved),  style={"fontSize": "16px", "fontWeight": "700", "color": "#2e7d32"}),
                    ], style={"textAlign": "center", "padding": "0 24px"}),
                ], style={"display": "flex", "alignItems": "center", "padding": "12px 8px", "background": "#f5fffe"}),
                colSpan=9,
                style={"padding": "0", "borderBottom": "1px solid #e0f5f5"},
            ),
            id={"type": "quick-view-row", "index": project_key},
            style={"display": "none"},
        )

        data_rows.append(html.Tr([
            html.Td(
                html.Div([
                    html.Button(
                        "YTD",
                        id={"type": "quick-view-btn", "index": project_key},
                        n_clicks=0,
                        style={
                            "background": "none", "border": f"1px solid {BRAND}",
                            "borderRadius": "4px", "cursor": "pointer",
                            "color": BRAND, "fontSize": "9px", "fontWeight": "700",
                            "padding": "1px 5px", "marginRight": "8px",
                            "letterSpacing": "0.3px", "flexShrink": "0",
                        },
                    ),
                    row.get("Project", ""),
                ], style={"display": "flex", "alignItems": "center"}),
                style={**td_base, "fontWeight": "500",
                       "paddingLeft": "32px" if hide_roi else "8px",
                       "borderLeft": f"4px solid {border_color}"},
            ),
            html.Td(row.get("Activated", "") or "—",
                    style={**td_base, "textAlign": "center", "fontSize": "12px", "color": "#888"}),
            html.Td(_chip(activity_status, ACTIVITY_CHIP), style={**td_base, "textAlign": "center"}),
            html.Td(roi_chips, style={**td_base, "minWidth": "140px"}),
            html.Td(row.get("1 mo", ""),     style={**td_base, "textAlign": "right",  "fontWeight": "600"}),
            html.Td(row.get("MoM %", ""),    style={**td_base, "textAlign": "center", "fontWeight": "600", "background": mom_bg}),
            html.Td(row.get("Mo ROI %", ""), style={**td_base, "textAlign": "center", "fontWeight": "600", "background": mr_bg}),
            html.Td(row.get("ROI %", ""),    style={**td_base, "textAlign": "center", "fontWeight": "600", "background": roi_bg}),
            html.Td(
                html.Button(
                    [html.I(className="bi bi-arrow-right", style={"fontSize": "11px"}), " Details"],
                    id={"type": "row-details-btn", "index": project_key},
                    n_clicks=0,
                    style={
                        "background": BRAND, "color": "white", "border": "none",
                        "borderRadius": "12px", "padding": "4px 11px",
                        "fontSize": "11px", "fontWeight": "600", "cursor": "pointer",
                        "whiteSpace": "nowrap", "letterSpacing": "0.2px",
                    },
                ),
                style={**td_base, "textAlign": "right", "width": "80px"},
            ),
        ]))
        data_rows.append(quick_view_row)

    return html.Table(
        [headers, html.Tbody(data_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "marginBottom": 0},
    )


def _build_client_summary(client_df):
    """Aggregate metrics bar shown at the top of each client accordion section."""
    n_total  = len(client_df)
    n_active = int(client_df["tag_active"].fillna(False).sum()) if "tag_active" in client_df.columns else 0

    total_investment = client_df["project_cost"].apply(_safe_num).sum() if "project_cost" in client_df.columns else 0
    total_saved      = client_df["cumulative_cost_saved"].apply(_safe_num).sum() if "cumulative_cost_saved" in client_df.columns else 0
    roi_net          = total_saved - total_investment

    def _stat(label, value, color=None):
        return html.Div([
            html.Span(label, style={
                "fontSize": "10px", "color": "#999", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.4px",
                "display": "block", "marginBottom": "2px",
            }),
            html.Span(value, style={"fontSize": "13px", "fontWeight": "700", "color": color or DARK}),
        ], style={"padding": "8px 16px", "borderRight": "1px solid #e8f5f5"})

    roi_color  = "#2e7d32" if roi_net >= 0 else "#c62828"
    roi_prefix = "+" if roi_net > 0 else ""
    roi_str    = f"{roi_prefix}{fmt_currency(roi_net)}" if total_investment > 0 else "—"

    return html.Div([
        _stat("Projects",   f"{n_active} / {n_total} active"),
        _stat("Total Saved",  fmt_currency(total_saved)      or "—"),
        _stat("Investment",   fmt_currency(total_investment)  or "—"),
        _stat("Net ROI",      roi_str,                          color=roi_color),
    ], style={
        "display": "flex", "flexWrap": "wrap",
        "background": "#f5fffe", "borderRadius": "8px",
        "border": "1px solid #d8f0f0", "marginBottom": "12px", "overflow": "hidden",
    })


def _build_client_charts(client_df, client_id):
    """Build monthly usage + savings trend charts for a client. Returns (toggle_btn, collapse)."""
    now = pd.Timestamp.now()
    current_month_idx = now.month - 1

    months_ordered = []
    for i in range(11, -1, -1):
        idx  = (current_month_idx - i) % 12
        year = now.year if idx <= current_month_idx else now.year - 1
        months_ordered.append((MONTHS_FR[idx], f"{MONTHS_FR[idx][:4]} '{str(year)[2:]}"))

    labels         = [lbl for _, lbl in months_ordered]
    usage_totals   = []
    savings_totals = []
    hours_totals   = []

    for month_name, _ in months_ordered:
        u_total = 0.0
        s_total = 0.0
        h_total = 0.0
        if month_name in client_df.columns:
            for _, row in client_df.iterrows():
                u     = _safe_num(row.get(month_name))
                mins  = _safe_num(row.get("Minutes Saved per usage"))
                rate  = _safe_num(row.get("Client Hourly Rate"))
                h     = u * mins / 60
                u_total += u
                h_total += h
                s_total += h * rate
        usage_totals.append(u_total)
        savings_totals.append(s_total)
        hours_totals.append(h_total)

    max_u = max(usage_totals,   default=0)
    max_s = max(savings_totals, default=0)
    max_h = max(hours_totals,   default=0)

    usage_fig = go.Figure(go.Bar(
        x=labels, y=usage_totals,
        marker_color=[BRAND if v == max_u else "#80e0e6" for v in usage_totals],
    ))
    usage_fig.update_layout(
        title={"text": "Monthly Usage (all projects)", "font": {"size": 11, "color": "#888"}, "x": 0.01},
        margin={"l": 10, "r": 10, "t": 30, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False, "rangemode": "tozero"},
        xaxis={"showgrid": False, "tickfont": {"size": 9}},
        height=180, showlegend=False,
    )

    savings_fig = go.Figure(go.Bar(
        x=labels, y=savings_totals,
        marker_color=[BRAND if v == max_s else "#80e0e6" for v in savings_totals],
        text=[fmt_currency(v) if v > 0 else "" for v in savings_totals],
        textposition="outside", cliponaxis=False,
        textfont={"size": 9, "color": DARK},
    ))
    savings_fig.update_layout(
        title={"text": "Monthly Savings (all projects)", "font": {"size": 11, "color": "#888"}, "x": 0.01},
        margin={"l": 10, "r": 10, "t": 30, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False, "rangemode": "tozero",
               "tickprefix": "$", "range": [0, max_s * 1.35] if max_s > 0 else None},
        xaxis={"showgrid": False, "tickfont": {"size": 9}},
        height=180, showlegend=False,
    )

    toggle = html.Button(
        [html.I(className="bi bi-bar-chart-line", style={"fontSize": "11px", "marginRight": "5px"}),
         "Show Charts"],
        id={"type": "client-charts-toggle", "client": client_id},
        n_clicks=0,
        style={
            "background": "transparent", "border": f"1px solid {BRAND}",
            "color": BRAND, "borderRadius": "12px", "padding": "3px 12px",
            "fontSize": "11px", "fontWeight": "600", "cursor": "pointer",
            "marginTop": "10px",
        },
    )

    hours_fig = go.Figure(go.Bar(
        x=labels, y=hours_totals,
        marker_color=[BRAND if v == max_h else "#80e0e6" for v in hours_totals],
        text=[fmt_hours(v) if v > 0 else "" for v in hours_totals],
        textposition="outside", cliponaxis=False,
        textfont={"size": 9, "color": DARK},
    ))
    hours_fig.update_layout(
        title={"text": "Hours Saved (all projects)", "font": {"size": 11, "color": "#888"}, "x": 0.01},
        margin={"l": 10, "r": 10, "t": 30, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False, "rangemode": "tozero",
               "range": [0, max_h * 1.35] if max_h > 0 else None},
        xaxis={"showgrid": False, "tickfont": {"size": 9}},
        height=180, showlegend=False,
    )

    collapse = dbc.Collapse(
        dbc.Row([
            dbc.Col(dcc.Graph(figure=usage_fig,   config={"displayModeBar": False}), xs=12, md=4),
            dbc.Col(dcc.Graph(figure=savings_fig, config={"displayModeBar": False}), xs=12, md=4),
            dbc.Col(dcc.Graph(figure=hours_fig,   config={"displayModeBar": False}), xs=12, md=4),
        ], style={"marginTop": "6px", "marginBottom": "4px"}),
        id={"type": "client-charts-collapse", "client": client_id},
        is_open=False,
    )

    return toggle, collapse


# ---------------------------------------------------------------------------
# Column list (defined here so make_portfolio_tab can reference it)
# ---------------------------------------------------------------------------
TABLE_COLS = ["Project", "Active?", "1 mo", "MoM %", "Mo ROI %", "ROI %"]


# ---------------------------------------------------------------------------
# App layout helpers
# ---------------------------------------------------------------------------

SIDEBAR_BG = BRAND

def make_sidebar():
    label_style = {
        "color": "rgba(255,255,255,0.7)", "fontWeight": "700", "fontSize": "10px",
        "textTransform": "uppercase", "letterSpacing": "0.8px", "marginBottom": "6px",
        "display": "flex", "alignItems": "center", "gap": "6px",
    }

    def _filter_block(icon, label, child):
        return html.Div([
            html.Div([
                html.I(className=f"bi {icon}", style={"fontSize": "10px", "color": "rgba(255,255,255,0.8)"}),
                html.Span(label),
            ], style=label_style),
            child,
        ], style={"marginBottom": "4px"})

    section_divider = html.Div([
        html.Div(style={"flex": 1, "height": "1px", "background": "rgba(255,255,255,0.3)"}),
        html.Span("Filters", style={
            "fontSize": "9px", "fontWeight": "700", "color": "rgba(255,255,255,0.6)",
            "textTransform": "uppercase", "letterSpacing": "1.2px", "padding": "0 10px",
        }),
        html.Div(style={"flex": 1, "height": "1px", "background": "rgba(255,255,255,0.3)"}),
    ], style={"display": "flex", "alignItems": "center", "margin": "4px 0"})

    dd_style = {"fontSize": "13px"}

    return html.Div(
        style={
            "width": "272px",
            "minHeight": "100vh",
            "background": SIDEBAR_BG,
            "padding": "24px 18px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "16px",
            "position": "fixed",
            "top": 0,
            "left": 0,
            "bottom": 0,
            "overflowY": "auto",
            "zIndex": 100,
            "boxShadow": "4px 0 24px rgba(0,0,0,0.18)",
        },
        children=[
            # Logo
            html.Div(
                html.Img(
                    src="https://genia.co/wp-content/uploads/2022/10/logo_genia.svg",
                    style={"maxWidth": "100%", "maxHeight": "52px"},
                ),
                style={
                    "background": "white",
                    "borderRadius": "12px",
                    "padding": "14px 18px",
                    "textAlign": "center",
                    "boxShadow": "0 4px 16px rgba(0,0,0,0.12)",
                },
            ),

            # App title + subtitle
            html.Div([
                html.P("Usage Dashboard", style={
                    "color": "white", "fontWeight": "800", "fontSize": "15px",
                    "marginBottom": "2px", "letterSpacing": "-0.2px",
                }),
                html.P("AI Solution Performance & ROI", style={
                    "color": "rgba(255,255,255,0.6)", "fontSize": "11px", "marginBottom": 0,
                }),
            ]),

            # Refresh button
            html.Button(
                [html.I(className="bi bi-arrow-clockwise", style={"marginRight": "7px"}),
                 "Refresh Data"],
                id="btn-refresh",
                n_clicks=0,
                style={
                    "width": "100%", "padding": "9px 0",
                    "background": "rgba(255,255,255,0.15)",
                    "border": "1px solid rgba(255,255,255,0.35)",
                    "borderRadius": "10px",
                    "color": "white", "fontWeight": "700", "fontSize": "13px",
                    "cursor": "pointer", "letterSpacing": "0.2px",
                    "transition": "background 0.15s, border-color 0.15s",
                },
            ),

            section_divider,

            # Filters
            _filter_block("bi-building",      "Client",   dcc.Dropdown(id="filter-client",     options=[], value="All", clearable=False, style=dd_style)),
            _filter_block("bi-folder2",       "Project",  dcc.Dropdown(id="filter-project",    options=[], value="All", clearable=False, style=dd_style)),
            _filter_block("bi-activity",      "Activity", dcc.Dropdown(id="filter-activity",   options=[], value=None, multi=True, placeholder="Any activity…",  style=dd_style)),
            _filter_block("bi-bar-chart",      "Status",   dcc.Dropdown(id="filter-roi-status", options=[], value=None, multi=True, placeholder="Any status…",    style=dd_style)),

            # Footer
            html.Div(style={"flex": 1}),
            html.A(
                [html.I(className="bi bi-box-arrow-right", style={"marginRight": "6px"}), "Sign out"],
                href="/logout",
                style={
                    "display": "block", "textAlign": "center",
                    "color": "rgba(255,255,255,0.5)", "fontSize": "12px",
                    "fontWeight": "600", "textDecoration": "none",
                    "padding": "6px", "borderRadius": "8px",
                    "border": "1px solid rgba(255,255,255,0.2)",
                }
            ),
            html.Div("Genia © 2026", style={
                "fontSize": "10px", "color": "rgba(255,255,255,0.4)",
                "textAlign": "center", "letterSpacing": "0.4px",
            }),
        ],
    )


def make_granularity_toggle(selected="monthly"):
    options = [("Daily", "daily"), ("Weekly", "weekly"), ("Monthly", "monthly")]
    buttons = []
    for label, value in options:
        active = value == selected
        buttons.append(html.Button(
            label,
            id={"type": "gran-btn", "index": value},
            n_clicks=0,
            style={
                "padding": "5px 16px", "borderRadius": "16px", "border": "none",
                "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
                "background": BRAND if active else "transparent",
                "color": "white" if active else "#888",
                "boxShadow": "0 1px 4px rgba(0,196,206,0.3)" if active else "none",
                "transition": "background 0.15s, color 0.15s",
            }
        ))
    return html.Div(buttons, style={
        "background": "#f0f0f0", "borderRadius": "20px",
        "padding": "3px", "display": "inline-flex", "gap": "2px",
    })


def make_metric_card(title, value_id, icon, subtitle):
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div(
                    html.I(className=f"bi {icon}"),
                    style={
                        "width": "38px", "height": "38px", "flexShrink": 0,
                        "background": f"rgba(0,196,206,0.12)",
                        "borderRadius": "10px",
                        "display": "flex", "alignItems": "center",
                        "justifyContent": "center",
                        "fontSize": "17px", "color": BRAND,
                    },
                ),
                html.P(title, style={
                    "fontSize": "11px", "color": "#999", "marginBottom": 0,
                    "fontWeight": "700", "textTransform": "uppercase",
                    "letterSpacing": "0.6px", "marginLeft": "10px", "lineHeight": "1.3",
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "14px"}),
            html.Div(id=value_id, children="—", style={
                "fontSize": "26px", "fontWeight": "800", "color": DARK,
                "letterSpacing": "-0.5px", "marginBottom": "4px",
            }),
            html.P(subtitle, style={"fontSize": "11px", "color": "#bbb", "marginBottom": 0}),
        ], style={"padding": "18px 20px"}),
        style={
            "borderRadius": "14px",
            "border": "none",
            "boxShadow": "0 2px 12px rgba(0,0,0,0.06)",
            "background": "white",
            "height": "100%",
        },
    )


def make_portfolio_tab():
    return dbc.Tab(
        label="Portfolio",
        tab_id="tab-portfolio",
        children=[
            # Summary cards
            dbc.Row([
                dbc.Col(make_metric_card("Solutions",   "metric-total-solutions",  "bi-grid",           "monitored projects"),    xs=12, sm=4, md=True, className="mb-3"),
                dbc.Col(make_metric_card("Active",      "metric-active-projects",  "bi-lightning-fill", "with usage this month"), xs=12, sm=4, md=True, className="mb-3"),
                dbc.Col(make_metric_card("ROI Reached", "metric-roi-reached",      "bi-trophy",         "projects fully paid off"),xs=12, sm=4, md=True, className="mb-3"),
            ], className="mb-4"),

            dcc.Store(id="client-sort-store", data={}),
            dcc.Store(id="accordion-active-store", data=None),

            # Portfolio table (grouped by client)
            dcc.Loading(
                id="loading-table",
                type="circle",
                color=BRAND,
                overlay_style={"visibility": "visible", "opacity": 0.15},
                custom_spinner=html.Div(style={"display": "none"}),
                children=html.Div(id="client-accordion-container"),
            ),

            html.Div(style={"marginTop": "8px"}, children=[
                html.P("Click any row to view full project details.", style={"color": "#aaa", "fontSize": "13px", "fontStyle": "italic"}),
            ]),
        ],
    )


STATUS_LEGEND = {
    "Activity": [
        ("Active",           ACTIVITY_CHIP["Active"],           "Has usage this month."),
        ("No Recent Usage",  ACTIVITY_CHIP["No Recent Usage"],  "No usage this month, but had usage in the last 3 months."),
        ("Inactive",         ACTIVITY_CHIP["Inactive"],         "No usage in the last 3 months."),
    ],
    "ROI & Performance": [
        ("ROI Reached",   ROI_CHIP["ROI Reached"],   "Cumulative savings have fully recovered the investment."),
        ("Above Mo. Target",  ROI_CHIP["Above Mo. Target"],  "This month's savings met or exceeded the monthly ROI goal."),
        ("Below Mo. Target",  ROI_CHIP["Below Mo. Target"],  "This month's savings fell short of the monthly ROI goal."),
        ("Usage Dropped", ROI_CHIP["Usage Dropped"], "Recent 3-month average is >50% lower than the historical baseline (only flagged if historical avg > 5 uses/mo)."),
        ("No Target",     ROI_CHIP["No Target"],     "Investment is set but no monthly ROI goal has been configured."),
        ("No Config",     ROI_CHIP["No Config"],     "No investment amount has been entered yet."),
    ],
}


def make_status_legend():
    sections = []
    for section_title, entries in STATUS_LEGEND.items():
        rows = []
        for label, (bg, fg), description in entries:
            rows.append(
                html.Div([
                    html.Div(
                        html.Span(label, style={
                            "background": bg, "color": fg,
                            "fontSize": "11px", "fontWeight": "700",
                            "padding": "3px 10px", "borderRadius": "4px",
                            "whiteSpace": "nowrap",
                        }),
                        style={"minWidth": "130px", "flexShrink": 0},
                    ),
                    html.P(description, style={
                        "fontSize": "12px", "color": "#555", "marginBottom": 0, "lineHeight": "1.4",
                    }),
                ], style={
                    "display": "flex", "alignItems": "center", "gap": "14px",
                    "padding": "10px 14px",
                    "borderBottom": "1px solid #f3f3f3",
                })
            )
        sections.append(html.Div([
            html.P(section_title, style={
                "fontSize": "11px", "fontWeight": "700", "color": "#888",
                "textTransform": "uppercase", "letterSpacing": "0.5px",
                "margin": "0", "padding": "10px 14px 6px",
                "background": "#f8f9fa", "borderBottom": "1px solid #eee",
            }),
            *rows,
        ], style={
            "border": "1px solid #eee", "borderRadius": "10px",
            "overflow": "hidden", "marginBottom": "12px",
        }))

    return html.Div(sections)


def make_settings_tab():
    return dbc.Tab(
        label="Configuration",
        tab_id="tab-settings",
        children=[
            dbc.Row([
                dbc.Col([
                    html.H5("Project Configuration", style={"color": BRAND, "fontWeight": "700", "marginBottom": "16px"}),
                    dcc.Loading(
                        id="loading-settings",
                        type="circle",
                        color=BRAND,
                        children=html.Div(id="settings-accordion"),
                    ),
                    dcc.Loading(html.Div([
                        dbc.Button(
                            "Save Configuration",
                            id="btn-save-config",
                            color="primary",
                            style={"background": BRAND, "border": "none", "marginTop": "20px", "fontWeight": "600"},
                        ),
                        html.Div(id="save-config-status", style={"marginTop": "10px"}),
                    ]), type="circle", color=BRAND,
                    overlay_style={"visibility": "visible", "opacity": 0.5}),
                ], md=8),
                dbc.Col([
                    html.H5("Status Reference", style={"color": BRAND, "fontWeight": "700", "marginBottom": "16px"}),
                    make_status_legend(),
                    html.Hr(style={"margin": "20px 0"}),
                    html.H5("Hidden Projects", style={"color": BRAND, "fontWeight": "700", "marginBottom": "16px"}),
                    html.Div(id="hidden-projects-list"),
                    dcc.Loading(html.Div([
                        html.Label("Hide a Project:", style={"fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                        dcc.Dropdown(id="hide-project-dropdown", options=[], placeholder="Select project…", style={"marginBottom": "8px"}),
                        dbc.Button("Hide Project", id="btn-hide-project", color="warning", size="sm"),
                        html.Div(id="hide-project-status", style={"marginTop": "10px"}),
                    ], style={"marginTop": "20px"}), type="circle", color=BRAND,
                    overlay_style={"visibility": "visible", "opacity": 0.5}),
                ], md=4),
            ]),
        ],
    )


# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ],
    suppress_callback_exceptions=True,
    title="Genia Usage Dashboard",
)
server = app.server   # for WSGI / Gunicorn

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
server.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME', 'admin')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', '')

_LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Genia Dashboard — Sign In</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', 'Segoe UI', sans-serif;
      background: #f0fafb;
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
    }
    .card {
      background: white; border-radius: 20px;
      padding: 44px 40px; width: 100%; max-width: 400px;
      box-shadow: 0 8px 40px rgba(0,196,206,0.12), 0 2px 8px rgba(0,0,0,0.06);
    }
    .logo-wrap {
      background: white; border-radius: 12px;
      padding: 14px 18px; text-align: center; margin-bottom: 28px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    }
    .logo-wrap img { max-height: 52px; max-width: 160px; }
    h1 { font-size: 21px; font-weight: 800; color: #13100d; margin-bottom: 4px; }
    .sub { font-size: 13px; color: #aaa; margin-bottom: 28px; }
    label {
      display: block; font-size: 11px; font-weight: 700; color: #888;
      text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px;
    }
    input[type=password] {
      width: 100%; padding: 10px 14px; margin-bottom: 18px;
      border: 1.5px solid #e8e8e8; border-radius: 10px;
      font-size: 14px; outline: none; transition: border-color 0.15s;
      font-family: inherit;
    }
    input:focus { border-color: #00c4ce; }
    button {
      width: 100%; padding: 13px; margin-top: 4px;
      background: #00c4ce; color: white; border: none;
      border-radius: 12px; font-size: 14px; font-weight: 700;
      cursor: pointer; letter-spacing: 0.2px; font-family: inherit;
      transition: opacity 0.15s;
    }
    button:hover { opacity: 0.88; }
    .error {
      background: #fff0f0; color: #c62828; border: 1px solid #fdd;
      border-radius: 8px; padding: 10px 14px;
      font-size: 13px; margin-bottom: 16px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo-wrap">
      <img src="https://genia.co/wp-content/uploads/2022/10/logo_genia.svg" alt="Genia">
    </div>
    <h1>Sign in</h1>
    <p class="sub">Genia Usage Dashboard</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST" action="/login">
      <label>Password</label>
      <input type="password" name="password" autocomplete="off" autofocus>
      <button type="submit">Continue</button>
    </form>
  </div>
</body>
</html>"""


@server.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            return redirect(request.args.get('next', '/'))
        error = 'Incorrect password.'
    return render_template_string(_LOGIN_HTML, error=error)


@server.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@server.before_request
def require_login():
    if request.path.startswith('/login') or request.path.startswith('/static'):
        return
    if not session.get('authenticated'):
        if request.path.startswith('/_dash'):
            return 'Unauthorized', 401
        return redirect(f'/login?next={request.path}')


app.layout = html.Div(
    style={"fontFamily": "'Inter', 'Segoe UI', sans-serif", "background": BG, "minHeight": "100vh"},
    children=[
        # Stores
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="data-store"),
        dcc.Store(id="settings-inputs-store"),   # holds current settings field values
        dcc.Store(id="hidden-store", data=load_hidden_projects()),  # holds hidden projects list
        dcc.Store(id="modal-raw-store"),         # raw timeseries for open project
        dcc.Store(id="modal-project-key"),       # triggers slow modal body load
        dcc.Store(id="usage-granularity", data="monthly"),  # granularity toggle state

        # Layout: sidebar + main
        html.Div(
            style={"display": "flex"},
            children=[
                # Sidebar
                make_sidebar(),

                # Main content (offset by sidebar width)
                html.Div(
                    style={"marginLeft": "272px", "flex": 1, "padding": "32px 32px 32px 32px", "minHeight": "100vh"},
                    children=[
                        # Header
                        html.Div([
                            html.H3("Genia Usage Dashboard", style={"color": DARK, "fontWeight": "800", "marginBottom": "4px"}),
                            html.P("AI Solution Performance & ROI Tracking", style={"color": "#666", "marginBottom": "24px"}),
                        ]),

                        # Tabs
                        dbc.Tabs(
                            id="main-tabs",
                            active_tab="tab-portfolio",
                            style={
                                "borderBottom": f"2px solid {BRAND}",
                                "marginBottom": "24px",
                            },
                            children=[
                                make_portfolio_tab(),
                                make_settings_tab(),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        # Solution detail modal
        dbc.Modal(
            id="solution-modal",
            size="xl",
            is_open=False,
            scrollable=True,
            children=[
                dbc.ModalHeader(
                    html.Div(id="solution-modal-title"),
                    close_button=True,
                    style={"background": "#f0fafb"},
                ),
                dcc.Loading(
                    dbc.ModalBody(id="solution-modal-body",
                                  style={"padding": "24px", "overflowY": "auto", "maxHeight": "72vh"}),
                    color=BRAND, type="circle",
                    style={"minHeight": "200px"},
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# CSS injection for AgGrid row colours (getRowStyle) and tab active style
# ---------------------------------------------------------------------------
app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
/* Active tab highlight */
.nav-tabs .nav-link.active {
    border-bottom: 3px solid """ + BRAND + """ !important;
    color: """ + BRAND + """ !important;
    font-weight: 700;
}
.nav-tabs .nav-link {
    color: #555;
    font-weight: 500;
}
/* Turquoise button */
.btn-primary {
    background-color: """ + BRAND + """ !important;
    border-color: """ + BRAND + """ !important;
}
/* AgGrid inner text */
.ag-theme-alpine {
    --ag-font-size: 13px;
    --ag-header-background-color: #f0fafb;
    --ag-header-foreground-color: """ + DARK + """;
    --ag-odd-row-background-color: transparent;
}
</style>
</head>
<body>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>
"""


def _apply_tag_filter(df, selected_tags, logic="or"):
    """Filter df by tag columns. logic='or' matches any tag; logic='and' requires all tags."""
    if not selected_tags:
        return df
    if isinstance(selected_tags, str):
        selected_tags = [selected_tags]
    if logic == "and":
        mask = pd.Series(True, index=df.index)
        for tag in selected_tags:
            col = STATUS_TAGS.get(tag)
            if col and col in df.columns:
                mask &= df[col].fillna(False).astype(bool)
    else:
        mask = pd.Series(False, index=df.index)
        for tag in selected_tags:
            col = STATUS_TAGS.get(tag)
            if col and col in df.columns:
                mask |= df[col].fillna(False).astype(bool)
    return df[mask]


# ===========================================================================
# CALLBACKS
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Load data on startup & on Refresh click
# ---------------------------------------------------------------------------
@app.callback(
    Output("data-store", "data"),
    Input("btn-refresh", "n_clicks"),
    prevent_initial_call=False,
)
def load_or_refresh_data(_n):
    df = fetch_dataframe()
    return df_to_store(df)


# ---------------------------------------------------------------------------
# 2. Populate sidebar filter dropdowns from loaded data
# ---------------------------------------------------------------------------
# Maps tag label → boolean column name in df
STATUS_TAGS = {
    # Activity
    "Active":           "tag_active",
    "No Recent Usage":  "tag_no_recent",
    "Inactive":         "tag_inactive",
    # ROI / financial
    "ROI Reached":      "tag_roi_reached",
    "Usage Dropped":    "tag_usage_dropped",
    "Above Mo. Target":     "tag_above_target",
    "Below Mo. Target":     "tag_below_target",
    "No Target":        "tag_no_target",
    "No Config":        "tag_no_config",
}

ACTIVITY_TAG_ORDER = ["Active", "No Recent Usage", "Inactive"]
ROI_TAG_ORDER      = ["ROI Reached", "Above Mo. Target", "Below Mo. Target", "Usage Dropped", "No Target", "No Config"]


@app.callback(
    Output("filter-client", "options"),
    Output("filter-project", "options"),
    Output("filter-activity", "options"),
    Output("filter-roi-status", "options"),
    Input("data-store", "data"),
)
def update_filter_options(store_data):
    df = df_from_store(store_data)
    if df.empty:
        empty = [{"label": "All", "value": "All"}]
        return empty, empty, empty, empty

    clients = ["All"] + sorted(df["CLIENT"].dropna().unique().tolist())
    projects = ["All"] + sorted(df["PROJECT"].dropna().unique().tolist())

    # Only show tags that are present in the data
    activity_opts = [{"label": t, "value": t} for t in ACTIVITY_TAG_ORDER
                     if STATUS_TAGS[t] in df.columns and df[STATUS_TAGS[t]].any()]
    roi_opts      = [{"label": t, "value": t} for t in ROI_TAG_ORDER
                     if STATUS_TAGS[t] in df.columns and df[STATUS_TAGS[t]].any()]

    return (
        [{"label": c, "value": c} for c in clients],
        [{"label": p, "value": p} for p in projects],
        activity_opts,
        roi_opts,
    )




# ---------------------------------------------------------------------------
# 3a. Per-client sort — clientside, instant
# ---------------------------------------------------------------------------
app.clientside_callback(
    """
    function(n_clicks_list, current_sorts) {
        var triggered = window.dash_clientside.callback_context.triggered;
        if (!triggered || triggered.length === 0) return current_sorts || {};
        var id = JSON.parse(triggered[0].prop_id.split('.')[0]);
        var parts = id.index.split('||');
        var client = parts[0];
        var key    = parts[1];
        var updated = Object.assign({}, current_sorts);
        updated[client] = key;
        return updated;
    }
    """,
    Output("client-sort-store", "data"),
    Input({"type": "client-sort-btn", "index": dash.ALL}, "n_clicks"),
    State("client-sort-store", "data"),
    prevent_initial_call=True,
)

# Save accordion open/close state so rebuild can restore it
app.clientside_callback(
    "function(active) { return active == null ? window.dash_clientside.no_update : active; }",
    Output("accordion-active-store", "data"),
    Input("client-accordion", "active_item"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# 3. Update portfolio table based on filters
# ---------------------------------------------------------------------------
_SORT_KEYS = {
    # Negated = descending (worst/best first). min() in client aggregation picks the worst project per client.
    "drop":         lambda r: -_safe_num(r.get("_usage_drop_pct_raw")),   # highest drop first
    "low_usage":    lambda r:  _safe_num(r.get("_usage_1mo_raw", 0)),      # lowest usage first
    "high_savings": lambda r: -_safe_num(r.get("_total_saved_raw")),       # highest savings first
    "roi_closest":  lambda r: -_safe_num(r.get("_roi_pct_raw")),           # highest ROI% first
}


@app.callback(
    Output("client-accordion-container", "children"),
    Input("data-store", "data"),
    Input("hidden-store", "data"),
    Input("filter-client", "value"),
    Input("filter-project", "value"),
    Input("filter-activity", "value"),
    Input("filter-roi-status", "value"),
    Input("client-sort-store", "data"),
    State("accordion-active-store", "data"),
)
def update_table(store_data, hidden_store, client_filter, project_filter, activity_filter, roi_filter, client_sorts, accordion_active):
    df = df_from_store(store_data)
    if df.empty:
        return []

    hidden = hidden_store or load_hidden_projects()
    if hidden:
        df = df[~df["PROJECT"].isin(hidden)]

    if client_filter and client_filter != "All":
        df = df[df["CLIENT"] == client_filter]
    if project_filter and project_filter != "All":
        df = df[df["PROJECT"] == project_filter]
    df = _apply_tag_filter(df, activity_filter, logic="and")
    df = _apply_tag_filter(df, roi_filter, logic="and")

    _, all_rows = build_grid_data(df)
    client_sorts = client_sorts or {}

    rows_by_client = {}
    for r in all_rows:
        rows_by_client.setdefault(r.get("Client"), []).append(r)

    clients = list(dict.fromkeys(r.get("Client") for r in all_rows))

    _SORT_LABELS = [
        ("default",      "Default"),
        ("drop",         "Biggest Drop"),
        ("low_usage",    "Lowest Usage"),
        ("high_savings", "Highest Savings"),
        ("roi_closest",  "Closest to ROI"),
    ]

    accordion_items = []
    for client in clients:
        client_rows   = rows_by_client.get(client, [])
        active_sort   = client_sorts.get(client, "default")
        sort_fn       = _SORT_KEYS.get(active_sort)
        if sort_fn:
            client_rows = sorted(client_rows, key=sort_fn)

        client_df_sub = df[df["CLIENT"] == client]
        summary       = _build_client_summary(client_df_sub)
        table         = build_client_table(client_rows)
        toggle, collapse = _build_client_charts(client_df_sub, client)

        sort_btns = html.Div([
            html.Span("Sort:", style={"fontSize": "11px", "color": "#aaa",
                                      "fontWeight": "600", "marginRight": "8px", "lineHeight": "26px"}),
            *[
                dbc.Button(
                    label,
                    id={"type": "client-sort-btn", "index": f"{client}||{key}"},
                    size="sm",
                    outline=(active_sort != key),
                    color="info",
                    className="me-1",
                    style={
                        "borderRadius": "20px", "fontSize": "11px", "padding": "2px 10px",
                        "--bs-btn-color": BRAND, "--bs-btn-border-color": BRAND,
                        "--bs-btn-hover-bg": BRAND, "--bs-btn-active-bg": BRAND,
                        "--bs-btn-bg": BRAND if active_sort == key else "transparent",
                        "color": "white" if active_sort == key else BRAND,
                    },
                )
                for key, label in _SORT_LABELS
            ],
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
                  "marginBottom": "10px", "marginTop": "4px"})

        accordion_items.append(
            dbc.AccordionItem(
                html.Div([
                    summary,
                    sort_btns,
                    html.Div(table, style={"overflowX": "auto"}),
                    toggle,
                    collapse,
                ]),
                title=client,
                item_id=f"client-{client}",
            )
        )

    all_item_ids = [f"client-{c}" for c in clients]
    if accordion_active is not None:
        # Restore saved state; ensure any newly visible clients are open
        active_items = list(accordion_active) + [i for i in all_item_ids if i not in accordion_active]
    else:
        active_items = all_item_ids

    return dbc.Accordion(
        accordion_items,
        id="client-accordion",
        active_item=active_items,
        always_open=True,
        flush=True,
        style={"marginBottom": "16px"},
    )


# ---------------------------------------------------------------------------
# 3a. Toggle client charts collapse (clientside — no server round-trip)
# ---------------------------------------------------------------------------
app.clientside_callback(
    "function(n, isOpen) { return n ? !isOpen : isOpen; }",
    Output({"type": "client-charts-collapse", "client": dash.MATCH}, "is_open"),
    Input({"type": "client-charts-toggle",    "client": dash.MATCH}, "n_clicks"),
    State({"type": "client-charts-collapse",  "client": dash.MATCH}, "is_open"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(n_clicks_list, current_styles) {
        var ctx = dash_clientside.callback_context;
        if (!ctx.triggered || !ctx.triggered.length) return current_styles;
        var triggered_id = JSON.parse(ctx.triggered[0].prop_id.split('.')[0]);
        var target_idx = triggered_id.index;
        return current_styles.map(function(style, i) {
            if (ctx.outputs_list[i].id.index === target_idx) {
                var isHidden = !style || style.display === 'none';
                var newStyle = Object.assign({}, style || {});
                newStyle.display = isHidden ? 'table-row' : 'none';
                return newStyle;
            }
            return style;
        });
    }
    """,
    Output({"type": "quick-view-row", "index": dash.ALL}, "style"),
    Input({"type": "quick-view-btn",  "index": dash.ALL}, "n_clicks"),
    State({"type": "quick-view-row",  "index": dash.ALL}, "style"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# 4. Update summary metrics
# ---------------------------------------------------------------------------
@app.callback(
    Output("metric-total-solutions", "children"),
    Output("metric-active-projects", "children"),
    Output("metric-roi-reached", "children"),
    Input("data-store", "data"),
    Input("hidden-store", "data"),
    Input("filter-client", "value"),
    Input("filter-project", "value"),
    Input("filter-activity", "value"),
    Input("filter-roi-status", "value"),
)
def update_metrics(store_data, hidden_store, client_filter, project_filter, activity_filter, roi_filter):
    df = df_from_store(store_data)
    if df.empty:
        return "—", "—", "—"

    hidden = hidden_store or load_hidden_projects()
    if hidden:
        df = df[~df["PROJECT"].isin(hidden)]

    # Client/project filters scope the portfolio; activity + ROI filters are drill-downs.
    # Metric cards reflect the full client/project scope regardless of drill-down filters.
    if client_filter and client_filter != "All":
        df = df[df["CLIENT"] == client_filter]
    if project_filter and project_filter != "All":
        df = df[df["PROJECT"] == project_filter]
    _ = activity_filter  # intentionally not applied to metrics
    _ = roi_filter

    total_solutions = len(df)
    active_projects = int(df["tag_active"].fillna(False).sum()) if "tag_active" in df.columns else 0

    primary_df = df[df["_split_primary"] == True] if "_split_primary" in df.columns else df
    roi_reached = int(primary_df["tag_roi_reached"].fillna(False).sum()) if "tag_roi_reached" in primary_df.columns else 0

    return (
        str(total_solutions),
        f"{active_projects} / {total_solutions}",
        str(roi_reached),
    )


# ---------------------------------------------------------------------------
# 5. Solution detail modal on row selection
# ---------------------------------------------------------------------------

def _fetch_project_timeseries(client, project, project_group):
    """Fetch raw daily records for the project from Supabase. Returns store dict or None."""
    from modules.data_loader import _fetch_all_rows
    proj_cfg = None
    for company_name, company_config in COMPANY_CONFIGS.items():
        if company_config.get('client_name', company_name) == client:
            proj_cfg = company_config['projects'].get(project_group)
            if proj_cfg:
                break
    if not proj_cfg:
        return None
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        rows = _fetch_all_rows(supabase, proj_cfg['supabase_table'])
        if not rows:
            return None
        raw = pd.DataFrame(rows)

        # Date column
        date_col = next((c for c in ['date', 'processed_date', 'created_at'] if c in raw.columns), None)
        if not date_col:
            return None
        raw[date_col] = pd.to_datetime(raw[date_col], errors='coerce')
        raw = raw[raw[date_col].notna()]

        # Filter split projects to the specific sub-value
        split_field = proj_cfg.get('split_by_field')
        if split_field and split_field in raw.columns:
            raw = raw[raw[split_field] == project]

        # Compute a numeric "usage" column per row
        usage_field  = proj_cfg['usage_field']
        value_type   = proj_cfg.get('value_type', 'boolean')
        match_value  = proj_cfg.get('match_value')
        if usage_field not in raw.columns:
            return None
        if value_type == 'match':
            raw['_u'] = (raw[usage_field] == match_value).astype(int)
        elif value_type == 'boolean':
            raw['_u'] = ((raw[usage_field] == True) | (raw[usage_field] == 'True') | (raw[usage_field] == 1)).astype(int)
        else:
            raw['_u'] = pd.to_numeric(raw[usage_field], errors='coerce').fillna(0)

        raw['_date'] = raw[date_col].dt.date.astype(str)
        daily = raw.groupby('_date')['_u'].sum().reset_index()
        daily.columns = ['date', 'count']
        daily = daily.sort_values('date')

        return {'daily': daily.to_dict('records')}
    except Exception as e:
        print(f"Timeseries fetch error: {e}")
        return None


def _modal_chip(label, color_map):
    bg, fg = color_map.get(label, ("#e2e3e5", "#383d41"))
    return html.Span(label, style={
        "marginLeft": "8px", "fontSize": "11px", "fontWeight": "700",
        "background": bg, "color": fg,
        "padding": "3px 10px", "borderRadius": "12px", "verticalAlign": "middle",
    })


def _build_modal_title(client, project, df):
    mask = (df["CLIENT"] == client) & (df["PROJECT"] == project)
    matching_df = df[mask]
    if matching_df.empty:
        return None
    row_data = matching_df.iloc[0]
    return html.Div([
        html.Span(f"{client}  —  {project}", style={"fontWeight": "700", "fontSize": "17px", "color": DARK}),
        _modal_chip(row_data.get("activity_status", "") or "", ACTIVITY_CHIP),
        _modal_chip(row_data.get("roi_status",      "") or "", ROI_CHIP),
    ])


def _load_alert_state(project_key):
    """Return (last_alert_status, last_alert_sent) from Supabase, or (None, None)."""
    try:
        rows = _sb().table("project_metadata") \
                    .select("last_alert_status,last_alert_sent") \
                    .eq("key", project_key).execute().data
        if rows:
            r = rows[0]
            return r.get("last_alert_status"), r.get("last_alert_sent")
    except Exception:
        pass
    return None, None


def _alert_banner(project_key):
    """Small info strip shown at top of modal with last-alert info."""
    status, sent_at = _load_alert_state(project_key)
    if not status or not sent_at:
        return None
    try:
        dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        date_str = dt.strftime("%b %d, %Y")
    except Exception:
        date_str = sent_at[:10]
    color = "#c62828" if status == "Usage Dropped" else "#d32f2f"
    return html.Div(
        [
            html.Span(f"Alert sent on {date_str}  ·  ", style={"fontWeight": "600"}),
            html.Span(status, style={"color": color, "fontWeight": "700"}),
        ],
        style={
            "background": "#fdf2f2", "border": f"1px solid {color}",
            "borderRadius": "8px", "padding": "8px 14px",
            "fontSize": "12px", "color": "#555",
            "marginBottom": "16px",
        },
    )


def _build_modal_body(client, project, df):
    """Build the full modal body. Hits Supabase for timeseries. Returns (body, raw_store)."""
    mask = (df["CLIENT"] == client) & (df["PROJECT"] == project)
    matching_df = df[mask]
    if matching_df.empty:
        return "Project not found.", None

    _, all_rows = build_grid_data(matching_df)
    if not all_rows:
        return "No data.", None

    row = all_rows[0]
    project_group = row.get("_project_group", project)

    raw_store     = _fetch_project_timeseries(client, project, project_group) or {}
    minutes_saved = _safe_num(matching_df.iloc[0].get("Minutes Saved per usage"))
    hourly_rate   = _safe_num(matching_df.iloc[0].get("Client Hourly Rate"))
    raw_store['minutes_saved'] = minutes_saved
    raw_store['hourly_rate']   = hourly_rate

    now = pd.Timestamp.now()
    current_month_idx = now.month - 1
    monthly_savings = {}
    for i in range(11, -1, -1):
        idx   = (current_month_idx - i) % 12
        year  = now.year if idx <= current_month_idx else now.year - 1
        mname = MONTHS_FR[idx]
        usage = _safe_num(matching_df.iloc[0].get(mname, 0))
        monthly_savings[f"{mname} {year}"] = round(usage * minutes_saved / 60 * hourly_rate, 2)
    raw_store['monthly_savings'] = monthly_savings

    def _pill(label, value, accent=False):
        return html.Div([
            html.P(label, style={"fontSize": "11px", "color": "#888", "marginBottom": "4px",
                                  "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
            html.P(str(value), style={"fontWeight": "700", "color": BRAND if accent else DARK,
                                       "fontSize": "22px", "marginBottom": 0}),
        ], style={"background": "white", "borderRadius": "10px", "padding": "14px 16px",
                  "boxShadow": "0 1px 4px rgba(0,0,0,0.07)", "height": "100%"})

    def _chart_card(graph_id, height=240):
        return dbc.Card(
            dbc.CardBody(dcc.Loading(
                dcc.Graph(id=graph_id, config={"displayModeBar": False},
                          style={"height": f"{height}px"}),
                color=BRAND, type="circle",
                overlay_style={"visibility": "visible", "opacity": 0.4},
            )),
            style={"border": "none", "boxShadow": "0 1px 4px rgba(0,0,0,0.07)",
                   "borderRadius": "10px", "marginTop": "8px"},
        )

    granularity_toggle = html.Div(
        html.Div(id="granularity-toggle-container", children=make_granularity_toggle("monthly")),
        style={"textAlign": "right", "marginBottom": "8px"},
    )

    roi_bar   = _build_roi_bar(row)
    breakeven = row.get("_breakeven", "")

    ytd_months = MONTHS_FR[:current_month_idx + 1]
    row_data   = matching_df.iloc[0]
    ytd_usage  = int(sum(_safe_num(row_data.get(m, 0)) for m in ytd_months))
    ytd_savings = ytd_usage * minutes_saved / 60 * hourly_rate

    # Tab 1: Usage
    tab_usage = dbc.Tab(label="Usage", tab_id="tab-usage", children=html.Div([
        dbc.Row([
            dbc.Col(_pill("This Month", row.get("_usage_1mo",  "—"), accent=True), xs=6, md=True, className="mb-3"),
            dbc.Col(_pill("MoM %",      row.get("_mom_pct",    "—"), accent=True), xs=6, md=True, className="mb-3"),
            dbc.Col(_pill("3 Months",   row.get("_usage_3mo",  "—")), xs=6, md=True, className="mb-3"),
            dbc.Col(_pill("YTD",        f"{ytd_usage} usages"), xs=6, md=True, className="mb-3"),
            dbc.Col(_pill("12 Months",  row.get("_usage_12mo", "—")), xs=6, md=True, className="mb-3"),
        ], className="mb-3"),
        granularity_toggle,
        _chart_card("usage-trend-graph", height=260),
    ], style={"padding": "20px 4px 4px 4px"}))

    # Tab 2: ROI & Financials
    tab_roi = dbc.Tab(label="ROI & Financials", tab_id="tab-roi", children=html.Div([
        dbc.Row([
            dbc.Col(_pill("Investment",   row.get("_investment",    "—")),                             xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("Total Saved",  row.get("_total_saved",   "—")),                             xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("YTD Savings",  fmt_currency(ytd_savings) if ytd_savings else "—"),          xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("ROI %",        row.get("_roi_pct",       "—"), accent=True),                xs=6, md=3, className="mb-3"),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col(_pill("Mo Target",    row.get("_mo_target",     "—")),              xs=6, md=4, className="mb-3"),
            dbc.Col(_pill("Saved This Mo",row.get("_saved_this_mo", "—")),              xs=6, md=4, className="mb-3"),
            dbc.Col(_pill("Mo ROI %",     row.get("Mo ROI %",       "—"), accent=True), xs=6, md=4, className="mb-3"),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(roi_bar),
                             style={"border": "none", "boxShadow": "0 1px 4px rgba(0,0,0,0.07)", "borderRadius": "10px"}), md=8),
            dbc.Col(html.Div([
                html.P("Break-even", style={"fontSize": "11px", "color": "#888", "marginBottom": "4px",
                                            "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.P(breakeven or "—", style={"fontWeight": "600", "color": DARK, "fontSize": "14px", "marginBottom": 0}),
            ], style={"background": "white", "borderRadius": "10px", "padding": "14px 16px",
                      "boxShadow": "0 1px 4px rgba(0,0,0,0.07)", "height": "100%"}), md=4),
        ], className="mb-1"),
        _chart_card("savings-trend-graph", height=220),
    ], style={"padding": "20px 4px 4px 4px"}))

    # Tab 3: Hours Saved — 12-month bar chart
    hrs_this_mo_raw = row.get("_hrs_this_mo", "—")
    hrs_prev_mo_raw = row.get("_hrs_prev_mo", "—")
    hrs_12mo_raw    = row.get("_hrs_12mo",    "—")

    _mo_labels = []
    _mo_hrs    = []
    for i in range(11, -1, -1):
        idx        = (current_month_idx - i) % 12
        year       = now.year if idx <= current_month_idx else now.year - 1
        month_name = MONTHS_FR[idx]
        _mo_labels.append(f"{month_name[:4]} '{str(year)[2:]}")
        _mo_hrs.append(_safe_num(row_data.get(month_name, 0)) * minutes_saved / 60)

    max_h = max(_mo_hrs, default=0.1)
    bar_fig = go.Figure(go.Bar(
        x=_mo_labels, y=_mo_hrs,
        marker_color=[BRAND if v == max_h else "#80e0e6" for v in _mo_hrs],
        text=[fmt_hours(v) if v > 0 else "" for v in _mo_hrs],
        textposition="outside", cliponaxis=False,
        textfont={"size": 11, "color": DARK},
    ))
    bar_fig.update_layout(
        margin={"l": 20, "r": 20, "t": 10, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False, "range": [0, max_h * 1.35]},
        xaxis={"showgrid": False, "tickfont": {"size": 11}},
        height=220, showlegend=False,
    )
    tab_hours = dbc.Tab(label="Hours Saved", tab_id="tab-hours", children=html.Div([
        dbc.Row([
            dbc.Col(_pill("This Month", hrs_this_mo_raw, accent=True), xs=6, md=4, className="mb-3"),
            dbc.Col(_pill("Last Month", hrs_prev_mo_raw),               xs=6, md=4, className="mb-3"),
            dbc.Col(_pill("12 Months",  hrs_12mo_raw),                  xs=6, md=4, className="mb-3"),
        ], className="mb-2"),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=bar_fig, config={"displayModeBar": False})),
                 style={"border": "none", "boxShadow": "0 1px 4px rgba(0,0,0,0.07)", "borderRadius": "10px"}),
    ], style={"padding": "20px 4px 4px 4px"}))

    tabs = dbc.Tabs(
        [tab_usage, tab_roi, tab_hours],
        active_tab="tab-usage",
        style={"borderBottom": f"2px solid {BRAND}"},
    )
    project_key = f"{client}_{project}"
    banner = _alert_banner(project_key)
    body = html.Div([banner, tabs] if banner else [tabs])
    return body, raw_store


# ---------------------------------------------------------------------------
# 5. Solution detail modal — Phase 1: open instantly (no Supabase)
# ---------------------------------------------------------------------------
@app.callback(
    Output("solution-modal", "is_open"),
    Output("solution-modal-title", "children"),
    Output("modal-project-key", "data"),
    Input({"type": "row-details-btn", "index": dash.ALL}, "n_clicks"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def open_modal(all_n_clicks, store_data):
    triggered = ctx.triggered_id
    if not triggered or not any(n for n in (all_n_clicks or []) if n):
        return False, no_update, no_update

    project_key = triggered["index"]
    client, project = project_key.split("___", 1)

    df = df_from_store(store_data)
    title = _build_modal_title(client, project, df)
    if title is None:
        return False, "", no_update

    # Include a timestamp so re-opening the same project always triggers the body callback
    return True, title, {"key": project_key, "t": pd.Timestamp.now().isoformat()}


# ---------------------------------------------------------------------------
# 5. Solution detail modal — Phase 2: load body + charts (hits Supabase)
# ---------------------------------------------------------------------------
@app.callback(
    Output("solution-modal-body", "children"),
    Output("modal-raw-store", "data"),
    Input("modal-project-key", "data"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def load_modal_body(modal_key_data, store_data):
    import traceback
    if not modal_key_data:
        return no_update, no_update
    try:
        client, project = modal_key_data["key"].split("___", 1)
        df = df_from_store(store_data)
        if df.empty:
            return "No data available.", None
        body, raw_store = _build_modal_body(client, project, df)
        return body, raw_store
    except Exception:
        traceback.print_exc()
        return "Error loading project details.", None


# ---------------------------------------------------------------------------
# 5a-i. Granularity button clicks → update store + re-render toggle
# ---------------------------------------------------------------------------
@app.callback(
    Output("usage-granularity", "data"),
    Input({"type": "gran-btn", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_granularity(n_clicks):
    triggered = ctx.triggered_id
    if triggered and any(n for n in (n_clicks or []) if n):
        return triggered["index"]
    return no_update


@app.callback(
    Output("granularity-toggle-container", "children"),
    Input("usage-granularity", "data"),
    prevent_initial_call=False,
)
def render_granularity_toggle(selected):
    return make_granularity_toggle(selected or "monthly")


# ---------------------------------------------------------------------------
# 5a. Usage trend chart — reacts to granularity toggle
# ---------------------------------------------------------------------------
@app.callback(
    Output("usage-trend-graph", "figure"),
    Input("modal-raw-store", "data"),
    Input("usage-granularity", "data"),
    prevent_initial_call=True,
)
def render_usage_trend(raw_data, granularity="monthly"):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis={"visible": False}, yaxis={"visible": False}, height=260)
    if not raw_data:
        return empty

    daily_records = raw_data.get("daily", [])
    if not daily_records:
        # Fallback: empty chart with message
        return empty

    df = pd.DataFrame(daily_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    if granularity == "daily":
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
        df = df[df["date"] >= cutoff]
        x = df["date"].dt.strftime("%b %d, %Y")
        y = df["count"]
        mode = "lines+markers"
    elif granularity == "weekly":
        df["period"] = df["date"].dt.to_period("W").dt.start_time
        df = df.groupby("period")["count"].sum().reset_index()
        # Label = "Week of Jun 23, 2025" (Monday start)
        x = df["period"].dt.strftime("w/o %b %d, %Y")
        y = df["count"]
        mode = "lines+markers"
    else:  # monthly
        df["period"] = df["date"].dt.to_period("M").dt.start_time
        df = df.groupby("period")["count"].sum().reset_index()
        cutoff = pd.Timestamp.now() - pd.DateOffset(months=13)
        df = df[df["period"] >= cutoff]
        x = df["period"].dt.strftime("%b %Y")
        y = df["count"]
        mode = "lines+markers"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode=mode,
        line={"color": BRAND, "width": 2.5},
        marker={"color": BRAND, "size": 6},
        fill="tozeroy", fillcolor="rgba(0,196,206,0.12)",
    ))
    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 10, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False, "rangemode": "tozero"},
        xaxis={"showgrid": False, "tickfont": {"size": 10}},
        height=260, showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# 5b. Monthly savings trend chart
# ---------------------------------------------------------------------------
@app.callback(
    Output("savings-trend-graph", "figure"),
    Input("modal-raw-store", "data"),
    prevent_initial_call=True,
)
def render_savings_trend(raw_data):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis={"visible": False}, yaxis={"visible": False}, height=220)
    if not raw_data:
        return empty

    monthly_savings = raw_data.get("monthly_savings", {})
    if not monthly_savings or all(v == 0 for v in monthly_savings.values()):
        return empty

    labels = list(monthly_savings.keys())
    values = [monthly_savings[k] for k in labels]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=[BRAND if v == max(values) else "#80e0e6" for v in values],
        text=[fmt_currency(v) if v else "" for v in values],
        textposition="outside", cliponaxis=False,
        textfont={"size": 10, "color": DARK},
    ))
    fig.update_layout(
        title={"text": "Monthly Savings (12 mo)", "font": {"size": 12, "color": "#888"}, "x": 0.01},
        margin={"l": 20, "r": 20, "t": 36, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False,
               "tickprefix": "$", "rangemode": "tozero",
               "range": [0, max(values, default=1) * 1.35]},
        xaxis={"showgrid": False, "tickfont": {"size": 10}},
        height=220, showlegend=False,
    )
    return fig


def _build_roi_bar(row):
    """Build a custom HTML ROI progress bar."""
    roi_pct_raw = row.get("_roi_pct_raw")
    if roi_pct_raw is None or (isinstance(roi_pct_raw, float) and math.isnan(roi_pct_raw)):
        return html.Div("ROI data not available", style={"color": "#999", "fontSize": "13px"})

    clamped = max(0, min(100, roi_pct_raw))
    pct_display = f"{roi_pct_raw:.0f}%"

    bar = html.Div([
        html.P("ROI Progress", style={"fontSize": "12px", "fontWeight": "600", "color": "#555", "marginBottom": "4px"}),
        html.Div(
            html.Div(
                style={
                    "width": f"{clamped}%",
                    "height": "100%",
                    "background": BRAND,
                    "borderRadius": "6px",
                    "transition": "width 0.5s",
                }
            ),
            style={
                "background": "#e0f7f8",
                "borderRadius": "6px",
                "height": "18px",
                "width": "100%",
                "overflow": "hidden",
                "marginBottom": "4px",
            },
        ),
        html.P(
            f"{pct_display} of investment recovered",
            style={"fontSize": "12px", "color": "#555", "marginBottom": 0},
        ),
    ])
    return bar


# ---------------------------------------------------------------------------
# 6. Render settings accordion
# ---------------------------------------------------------------------------
@app.callback(
    Output("settings-accordion", "children"),
    Input("data-store", "data"),
)
def render_settings_accordion(store_data):
    metadata = load_project_metadata()
    accordion_items = []

    for company_name, company_config in COMPANY_CONFIGS.items():
        client_name = company_config.get("client_name", company_name)
        worksheet = company_config.get("worksheet_name", company_name)
        project_fields = []

        for project_name, proj_cfg in company_config["projects"].items():
            # For split projects, show one row per sub-value (each has its own metadata).
            # For regular projects, show one row for the project itself.
            split_values = proj_cfg.get("split_values")
            entries = (
                [(sv, f"{worksheet}_{sv}") for sv in split_values]
                if split_values
                else [(project_name, f"{worksheet}_{project_name}")]
            )

            for display_name, project_key in entries:
                meta = metadata.get(project_key, {})

                def _round_val(v):
                    if v is None: return None
                    r = round(float(v), 2)
                    return int(r) if r == int(r) else r
                inv_val  = _round_val(meta.get("investment"))
                goal_val = _round_val(meta.get("monthly_roi_goal"))
                mins_val = _round_val(meta.get("minutes_saved_per_usage"))
                rate_val = _round_val(meta.get("client_hourly_rate"))
                activated_val = meta.get("month_activated") or ""

                safe_key = project_key.replace(" ", "_").replace("/", "_")

                project_fields.append(html.Div([
                    html.P(display_name, style={"fontWeight": "700", "color": DARK, "marginBottom": "8px", "fontSize": "14px"}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Month Activated", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-activated", "key": safe_key},
                                      value=activated_val, placeholder="YYYY-MM", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Investment ($)", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-investment", "key": safe_key},
                                      type="text", inputMode="decimal", value=inv_val, placeholder="e.g. 5000", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Monthly ROI Goal ($)", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-goal", "key": safe_key},
                                      type="text", inputMode="decimal", value=goal_val, placeholder="e.g. 500", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Minutes Saved / Usage", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-minutes", "key": safe_key},
                                      type="text", inputMode="decimal", value=mins_val, placeholder="e.g. 10", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Client Hourly Rate ($/hr)", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-rate", "key": safe_key},
                                      type="text", inputMode="decimal", value=rate_val, placeholder="e.g. 50", size="sm"),
                        ], md=6, className="mb-2"),
                    ]),
                    html.Hr(style={"margin": "12px 0"}),
                ], id=f"proj-block-{safe_key}", **{"data-project-key": project_key}))

        accordion_items.append(
            dbc.AccordionItem(
                project_fields,
                title=client_name,
                item_id=f"accordion-{company_name}",
            )
        )

    return dbc.Accordion(accordion_items, start_collapsed=True, flush=True)


# ---------------------------------------------------------------------------
# 7. Save Configuration
# ---------------------------------------------------------------------------
@app.callback(
    Output("save-config-status", "children"),
    Output("data-store", "data", allow_duplicate=True),
    Input("btn-save-config", "n_clicks"),
    State({"type": "meta-activated", "key": dash.ALL}, "value"),
    State({"type": "meta-activated", "key": dash.ALL}, "id"),
    State({"type": "meta-investment", "key": dash.ALL}, "value"),
    State({"type": "meta-goal", "key": dash.ALL}, "value"),
    State({"type": "meta-minutes", "key": dash.ALL}, "value"),
    State({"type": "meta-rate", "key": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def save_configuration(n_clicks, activated_vals, activated_ids, inv_vals, goal_vals, mins_vals, rate_vals):
    if not n_clicks:
        return no_update, no_update

    metadata = load_project_metadata()

    # Validate all numeric fields before saving anything
    field_labels = {
        "inv":   "Investment ($)",
        "goal":  "Monthly ROI Goal ($)",
        "mins":  "Minutes Saved / Usage",
        "rate":  "Client Hourly Rate ($/hr)",
    }
    validation_errors = []
    all_vals = {"inv": inv_vals, "goal": goal_vals, "mins": mins_vals, "rate": rate_vals}
    for field_key, vals in all_vals.items():
        for i, v in enumerate(vals or []):
            if v is None or str(v).strip() == "":
                continue  # empty is fine — treated as null
            parsed = _parse_num(v)
            if parsed is None:
                safe_key = (activated_ids[i] or {}).get("key", f"row {i+1}")
                validation_errors.append(f'"{v}" is not a valid number for {field_labels[field_key]} (row: {safe_key})')

    if validation_errors:
        return dbc.Alert(
            [html.Strong("Invalid values — nothing was saved:"), html.Br()] +
            [html.Span(f"• {e}") for e in validation_errors[:5]],
            color="danger", duration=8000,
        ), no_update

    for i, id_dict in enumerate(activated_ids):
        safe_key = id_dict["key"]
        original_key = _find_original_key(safe_key, metadata)
        if original_key is None:
            original_key = safe_key.replace("_", " ", 1)

        entry = metadata.get(original_key, {})
        entry["month_activated"] = activated_vals[i] or None
        entry["investment"] = _parse_num(inv_vals[i])
        entry["monthly_roi_goal"] = _parse_num(goal_vals[i])
        entry["minutes_saved_per_usage"] = _parse_num(mins_vals[i])
        entry["client_hourly_rate"] = _parse_num(rate_vals[i])
        metadata[original_key] = entry

    save_project_metadata(metadata)

    # Reload data
    df = fetch_dataframe()
    store_json = df_to_store(df)

    return dbc.Alert("Configuration saved and data reloaded!", color="success", duration=4000), store_json


def _find_original_key(safe_key, metadata):
    """Try to find the original metadata key that corresponds to a safe_key."""
    # Direct match first
    if safe_key in metadata:
        return safe_key
    # Scan existing keys and compare their safe versions
    for k in metadata.keys():
        if k.replace(" ", "_").replace("/", "_") == safe_key:
            return k
    # Scan COMPANY_CONFIGS to find the worksheet+project combo
    for company_name, company_config in COMPANY_CONFIGS.items():
        worksheet = company_config.get("worksheet_name", company_name)
        for project_name in company_config["projects"]:
            candidate = f"{worksheet}_{project_name}"
            if candidate.replace(" ", "_").replace("/", "_") == safe_key:
                return candidate
    return None


def _parse_num(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = round(float(val), 2)
        return int(v) if v == int(v) else v
    s = str(val).replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        v = round(float(s), 2)
        return int(v) if v == int(v) else v
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 8. Hidden Projects management
# ---------------------------------------------------------------------------
@app.callback(
    Output("hidden-projects-list", "children"),
    Output("hide-project-dropdown", "options"),
    Input("data-store", "data"),
    Input("hide-project-status", "children"),
)
def render_hidden_projects(store_data, _status_trigger):
    df = df_from_store(store_data)
    hidden = load_hidden_projects()

    # Build unhide buttons
    hidden_items = []
    for proj in hidden:
        hidden_items.append(
            dbc.Alert([
                html.Span(proj, style={"fontWeight": "600"}),
                dbc.Button("Unhide", id={"type": "btn-unhide", "project": proj},
                           color="success", size="sm", className="float-end"),
            ], color="warning", style={"padding": "8px 12px", "marginBottom": "6px"})
        )
    if not hidden_items:
        hidden_items = [html.P("No hidden projects.", style={"color": "#999", "fontSize": "13px"})]

    # Project options for hide dropdown
    if not df.empty:
        all_projects = sorted(df["PROJECT"].dropna().unique().tolist())
        options = [{"label": p, "value": p} for p in all_projects if p not in hidden]
    else:
        options = []

    return hidden_items, options


@app.callback(
    Output("hide-project-status", "children"),
    Output("hidden-store", "data"),
    Input("btn-hide-project", "n_clicks"),
    Input({"type": "btn-unhide", "project": dash.ALL}, "n_clicks"),
    State("hide-project-dropdown", "value"),
    prevent_initial_call=True,
)
def manage_hidden_projects(hide_clicks, unhide_clicks, project_to_hide):
    triggered = ctx.triggered_id
    triggered_value = ctx.triggered[0]["value"] if ctx.triggered else 0

    # Ignore spurious fires from newly rendered pattern-matched buttons
    if not triggered_value:
        return no_update, no_update

    if isinstance(triggered, dict) and triggered.get("type") == "btn-unhide":
        proj = triggered["project"]
        unhide_project(proj)
        hidden = load_hidden_projects()
        return dbc.Alert(f"'{proj}' unhidden.", color="success", duration=3000), hidden

    if triggered == "btn-hide-project":
        if project_to_hide:
            hide_project(project_to_hide)
            hidden = load_hidden_projects()
            return dbc.Alert(f"'{project_to_hide}' hidden.", color="warning", duration=3000), hidden

    return no_update, no_update


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    app.run(debug=True, port=8050)
