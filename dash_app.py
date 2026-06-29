"""
Genia Usage Dashboard — Dash rewrite
Replaces the Streamlit app.py without touching it.
"""

import os
import json
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

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
        return "+∞"
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
            "_breakeven":       row.get("breakeven_estimate", "") or "",
            "_project_group":   row.get("_project_group", "") or "",
            "_client":          row.get("CLIENT", "") or "",
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

        data_rows.append(html.Tr([
            html.Td(
                row.get("Project", ""),
                style={**td_base, "fontWeight": "500",
                       "paddingLeft": "32px" if hide_roi else "14px",
                       "borderLeft": f"4px solid {border_color}"},
            ),
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

    return html.Table(
        [headers, html.Tbody(data_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "marginBottom": 0},
    )


# ---------------------------------------------------------------------------
# Column list (defined here so make_portfolio_tab can reference it)
# ---------------------------------------------------------------------------
TABLE_COLS = ["Project", "Active?", "1 mo", "MoM %", "Mo ROI %", "ROI %"]


# ---------------------------------------------------------------------------
# App layout helpers
# ---------------------------------------------------------------------------

def make_sidebar():
    return html.Div(
        style={
            "width": "260px",
            "minHeight": "100vh",
            "background": BRAND,
            "padding": "24px 16px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "20px",
            "position": "fixed",
            "top": 0,
            "left": 0,
            "bottom": 0,
            "overflowY": "auto",
            "zIndex": 100,
        },
        children=[
            # Logo
            html.Div(
                html.Img(
                    src="https://genia.co/wp-content/uploads/2022/10/logo_genia.svg",
                    style={"maxWidth": "100%", "maxHeight": "60px"},
                ),
                style={
                    "background": "white",
                    "borderRadius": "12px",
                    "padding": "12px 16px",
                    "textAlign": "center",
                },
            ),
            # Refresh button
            dbc.Button(
                [html.I(className="bi bi-arrow-clockwise me-2"), "Refresh Data"],
                id="btn-refresh",
                color="light",
                className="w-100",
                style={"fontWeight": "600", "color": DARK},
            ),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.4)", "margin": "0"}),
            # Filters
            html.Div([
                html.Label("Filter by Client", style={"color": "white", "fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                dcc.Dropdown(id="filter-client", options=[], value="All",
                             clearable=False, style={"fontSize": "13px"}),
            ]),
            html.Div([
                html.Label("Filter by Project", style={"color": "white", "fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                dcc.Dropdown(id="filter-project", options=[], value="All",
                             clearable=False, style={"fontSize": "13px"}),
            ]),
            html.Div([
                html.Label("Filter by Activity", style={"color": "white", "fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                dcc.Dropdown(id="filter-activity", options=[], value=None,
                             multi=True, placeholder="Any activity…", style={"fontSize": "13px"}),
            ]),
            html.Div([
                html.Label("Filter by Status", style={"color": "white", "fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                dcc.Dropdown(id="filter-roi-status", options=[], value=None,
                             multi=True, placeholder="Any status…", style={"fontSize": "13px"}),
            ]),
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

            # Portfolio table (grouped by client)
            dcc.Loading(
                id="loading-table",
                type="circle",
                color=BRAND,
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
                    dbc.Button(
                        "Save Configuration",
                        id="btn-save-config",
                        color="primary",
                        style={"background": BRAND, "border": "none", "marginTop": "20px", "fontWeight": "600"},
                    ),
                    html.Div(id="save-config-status", style={"marginTop": "10px"}),
                ], md=8),
                dbc.Col([
                    html.H5("Status Reference", style={"color": BRAND, "fontWeight": "700", "marginBottom": "16px"}),
                    make_status_legend(),
                    html.Hr(style={"margin": "20px 0"}),
                    html.H5("Hidden Projects", style={"color": BRAND, "fontWeight": "700", "marginBottom": "16px"}),
                    html.Div(id="hidden-projects-list"),
                    html.Div([
                        html.Label("Hide a Project:", style={"fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                        dcc.Dropdown(id="hide-project-dropdown", options=[], placeholder="Select project…", style={"marginBottom": "8px"}),
                        dbc.Button("Hide Project", id="btn-hide-project", color="warning", size="sm"),
                    ], style={"marginTop": "20px"}),
                    html.Div(id="hide-project-status", style={"marginTop": "10px"}),
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

app.layout = html.Div(
    style={"fontFamily": "'Inter', 'Segoe UI', sans-serif", "background": BG, "minHeight": "100vh"},
    children=[
        # Stores
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="data-store"),
        dcc.Store(id="settings-inputs-store"),   # holds current settings field values
        dcc.Store(id="hidden-store", data=load_hidden_projects()),  # holds hidden projects list
        dcc.Store(id="modal-raw-store"),         # raw timeseries for open project
        dcc.Store(id="usage-granularity", data="monthly"),  # granularity toggle state

        # Layout: sidebar + main
        html.Div(
            style={"display": "flex"},
            children=[
                # Sidebar
                make_sidebar(),

                # Main content (offset by sidebar width)
                html.Div(
                    style={"marginLeft": "260px", "flex": 1, "padding": "32px 32px 32px 32px", "minHeight": "100vh"},
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
                    dbc.ModalBody(id="solution-modal-body", style={"padding": "24px"}),
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
# 3. Update portfolio table based on filters
# ---------------------------------------------------------------------------
@app.callback(
    Output("client-accordion-container", "children"),
    Input("data-store", "data"),
    Input("hidden-store", "data"),
    Input("filter-client", "value"),
    Input("filter-project", "value"),
    Input("filter-activity", "value"),
    Input("filter-roi-status", "value"),
)
def update_table(store_data, hidden_store, client_filter, project_filter, activity_filter, roi_filter):
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

    accordion_items = []
    for client in df["CLIENT"].unique():
        client_rows = [r for r in all_rows if r.get("Client") == client]
        table = build_client_table(client_rows)
        accordion_items.append(
            dbc.AccordionItem(
                html.Div(table, style={"overflowX": "auto"}),
                title=client,
                item_id=f"client-{client}",
            )
        )

    return dbc.Accordion(
        accordion_items,
        start_collapsed=False,
        always_open=True,
        flush=True,
        style={"marginBottom": "16px"},
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


@app.callback(
    Output("solution-modal", "is_open"),
    Output("solution-modal-title", "children"),
    Output("solution-modal-body", "children"),
    Output("modal-raw-store", "data"),
    Input({"type": "row-details-btn", "index": dash.ALL}, "n_clicks"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def show_solution_modal(all_n_clicks, store_data):
    import traceback
    try:
        return _show_solution_modal_inner(all_n_clicks, store_data)
    except Exception:
        traceback.print_exc()
        return False, "", "", None


def _show_solution_modal_inner(all_n_clicks, store_data):
    triggered = ctx.triggered_id
    if not triggered or not any(n for n in (all_n_clicks or []) if n):
        return False, "", "", no_update

    project_key = triggered["index"]
    client, project = project_key.split("___", 1)

    df = df_from_store(store_data)
    if df.empty:
        return False, "", "", None

    mask = (df["CLIENT"] == client) & (df["PROJECT"] == project)
    matching_df = df[mask]
    if matching_df.empty:
        return False, "", "", None

    _, all_rows = build_grid_data(matching_df)
    if not all_rows:
        return False, "", "", None

    row = all_rows[0]
    project_group = row.get("_project_group", project)

    # --- Fetch raw timeseries + build monthly savings for the store ---
    raw_store = _fetch_project_timeseries(client, project, project_group) or {}
    minutes_saved = _safe_num(matching_df.iloc[0].get("Minutes Saved per usage"))
    hourly_rate   = _safe_num(matching_df.iloc[0].get("Client Hourly Rate"))
    raw_store['minutes_saved'] = minutes_saved
    raw_store['hourly_rate']   = hourly_rate
    # Monthly savings from stored monthly usage × rates (key = "Janvier 2025" etc.)
    now = pd.Timestamp.now()
    current_month_idx = now.month - 1
    monthly_savings = {}
    for i in range(11, -1, -1):
        idx  = (current_month_idx - i) % 12
        year = now.year if idx <= current_month_idx else now.year - 1
        mname = MONTHS_FR[idx]
        usage = _safe_num(matching_df.iloc[0].get(mname, 0))
        monthly_savings[f"{mname} {year}"] = round(usage * minutes_saved / 60 * hourly_rate, 2)
    raw_store['monthly_savings'] = monthly_savings

    roi_status      = row.get("_roi_status", "")
    activity_status = row.get("_activity_status", "")

    def _modal_chip(label, color_map):
        bg, fg = color_map.get(label, ("#e2e3e5", "#383d41"))
        return html.Span(label, style={
            "marginLeft": "8px", "fontSize": "11px", "fontWeight": "700",
            "background": bg, "color": fg,
            "padding": "3px 10px", "borderRadius": "12px", "verticalAlign": "middle",
        })

    title = html.Div([
        html.Span(f"{client}  —  {project}", style={"fontWeight": "700", "fontSize": "17px", "color": DARK}),
        _modal_chip(activity_status, ACTIVITY_CHIP),
        _modal_chip(roi_status, ROI_CHIP),
    ])

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

    roi_bar  = _build_roi_bar(row)
    breakeven = row.get("_breakeven", "")

    # --- YTD calculations ---
    current_month_idx = pd.Timestamp.now().month - 1  # 0-based
    ytd_months = MONTHS_FR[:current_month_idx + 1]
    row_data = matching_df.iloc[0]
    ytd_usage = int(sum(_safe_num(row_data.get(m, 0)) for m in ytd_months))
    ytd_savings = ytd_usage * minutes_saved / 60 * hourly_rate

    # --- Tab 1: Usage ---
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

    # --- Tab 2: ROI & Financials ---
    tab_roi = dbc.Tab(label="ROI & Financials", tab_id="tab-roi", children=html.Div([
        dbc.Row([
            dbc.Col(_pill("Investment",   row.get("_investment",    "—")),              xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("Total Saved",  row.get("_total_saved",   "—")),              xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("YTD Savings",  fmt_currency(ytd_savings) if ytd_savings else "—"), xs=6, md=3, className="mb-3"),
            dbc.Col(_pill("ROI %",        row.get("_roi_pct",       "—"), accent=True), xs=6, md=3, className="mb-3"),
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

    # --- Tab 3: Hours Saved ---
    hrs_this_mo_raw = row.get("_hrs_this_mo", "—")
    hrs_prev_mo_raw = row.get("_hrs_prev_mo", "—")
    hrs_12mo_raw    = row.get("_hrs_12mo",    "—")

    def _parse_hrs(s):
        try: return float(str(s).replace("h", "").strip())
        except: return 0

    h1 = _parse_hrs(hrs_this_mo_raw)
    hp = _parse_hrs(hrs_prev_mo_raw)
    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        x=["Last Month", "This Month"], y=[hp, h1],
        marker_color=["#80e0e6", BRAND],
        text=[hrs_prev_mo_raw, hrs_this_mo_raw],
        textposition="outside", cliponaxis=False,
        textfont={"size": 13, "color": DARK},
    ))
    bar_fig.update_layout(
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False,
               "range": [0, max(h1, hp, 0.1) * 1.35]},
        xaxis={"showgrid": False}, height=220, showlegend=False,
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

    body = dbc.Tabs(
        [tab_usage, tab_roi, tab_hours],
        active_tab="tab-usage",
        style={"borderBottom": f"2px solid {BRAND}"},
    )

    return True, title, body, raw_store


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

                inv_val = meta.get("investment")
                goal_val = meta.get("monthly_roi_goal")
                mins_val = meta.get("minutes_saved_per_usage")
                rate_val = meta.get("client_hourly_rate")
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
                                      type="number", value=inv_val, placeholder="e.g. 5000", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Monthly ROI Goal ($)", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-goal", "key": safe_key},
                                      type="number", value=goal_val, placeholder="e.g. 500", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Minutes Saved / Usage", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-minutes", "key": safe_key},
                                      type="number", value=mins_val, placeholder="e.g. 10", size="sm"),
                        ], md=6, className="mb-2"),
                        dbc.Col([
                            dbc.Label("Client Hourly Rate ($/hr)", style={"fontSize": "12px", "fontWeight": "600"}),
                            dbc.Input(id={"type": "meta-rate", "key": safe_key},
                                      type="number", value=rate_val, placeholder="e.g. 50", size="sm"),
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

    for i, id_dict in enumerate(activated_ids):
        safe_key = id_dict["key"]
        # Reverse the safe_key encoding to get back the original project_key
        # We store the original key in data-project-key on the block — but since
        # pattern-match callbacks only give us the component ID, we reconstruct from safe_key.
        # The safe_key replaced spaces and slashes with underscores, so we can't perfectly
        # reverse it. Instead we look up by safe_key directly in metadata by scanning keys.
        original_key = _find_original_key(safe_key, metadata)
        if original_key is None:
            # New key — build from safe_key (best effort)
            original_key = safe_key.replace("_", " ", 1)  # only first underscore = worksheet sep

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
        return float(val)
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
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
