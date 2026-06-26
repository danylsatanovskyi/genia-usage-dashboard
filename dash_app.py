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
PROJECT_METADATA_FILE = "project_metadata.json"
HIDDEN_PROJECTS_FILE = "hidden_projects.json"

# ---------------------------------------------------------------------------
# Helpers — metadata / hidden projects
# ---------------------------------------------------------------------------

def load_project_metadata():
    if os.path.exists(PROJECT_METADATA_FILE):
        with open(PROJECT_METADATA_FILE) as f:
            return json.load(f)
    return {}


def save_project_metadata(metadata):
    with open(PROJECT_METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def load_hidden_projects():
    if os.path.exists(HIDDEN_PROJECTS_FILE):
        with open(HIDDEN_PROJECTS_FILE) as f:
            data = json.load(f)
            return data.get("hidden", [])
    return []


def save_hidden_projects(hidden_list):
    with open(HIDDEN_PROJECTS_FILE, "w") as f:
        json.dump({"hidden": hidden_list}, f, indent=2)


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
    return pd.read_json(store_data, orient="split")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_currency(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    return f"${val:,.0f}"


def fmt_hours(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    return f"{val:.1f}h"


def fmt_mom(curr, prev, month_activated=None):
    if curr == 0 and prev == 0:
        return "–"
    if prev == 0 and curr > 0:
        # Only label "New" if the project was activated within the last 2 months
        if month_activated:
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
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    return f"{val:.0f}%"


def fmt_activated(val):
    if not val:
        return ""
    # Keep only YYYY-MM
    return str(val)[:7]


# ---------------------------------------------------------------------------
# Row color by roi_status
# ---------------------------------------------------------------------------

STATUS_BG = {
    "ROI Reached":    "#d4edda",   # green tint
    "Above Target":   "#d4edda",
    "On Track":       "#fff3cd",   # amber tint
    "Below Target":   "#f8d7da",   # red tint
    "Usage Dropped":  "#f8d7da",
    "No Recent Usage":"#fff3cd",
    "Inactive":       "#e2e3e5",   # gray
    "Active (Config Needed)": "#e8f4f8",
}


# ---------------------------------------------------------------------------
# Build AgGrid column defs and row data from a DataFrame
# ---------------------------------------------------------------------------

def build_grid_data(df):
    if df.empty:
        return [], []

    rows = []
    for _, row in df.iterrows():
        curr = row.get("usage_this_month", 0) or 0
        prev = row.get("usage_prev_month", 0) or 0
        month_activated = row.get("Month Activated") or None
        status = row.get("roi_status", "")
        hide_roi = row.get("_hide_roi", False)

        rows.append({
            "_id":            str(_),
            "_roi_status":    status,
            "_hide_roi":      hide_roi,
            "Client":         row.get("CLIENT", ""),
            "Project":        row.get("PROJECT", ""),
            "Activated":      fmt_activated(row.get("Month Activated")),
            "1 mo":           int(curr),
            "MoM %":          fmt_mom(curr, prev, month_activated),
            "3 mo":           int(row.get("usage_last_3_months", 0) or 0),
            "12 mo":          int(row.get("usage_last_12_months", 0) or 0),
            "Hours Saved":    fmt_hours(row.get("time_saved_hours_12mo")),
            "Investment":     fmt_currency(row.get("project_cost")) if row.get("project_cost") else "",
            "Total Saved":    fmt_currency(row.get("cumulative_cost_saved")),
            "ROI %":          fmt_roi(row.get("roi_progress_percent")),
            # Raw values for the detail panel
            "_usage_1mo":     curr,
            "_mom_pct":       fmt_mom(curr, prev, month_activated),
            "_hours_saved":   fmt_hours(row.get("time_saved_hours_12mo")),
            "_total_saved":   fmt_currency(row.get("cumulative_cost_saved")),
            "_roi_pct":       fmt_roi(row.get("roi_progress_percent")),
            "_roi_pct_raw":   row.get("roi_progress_percent"),
            "_mom_pct_raw":   row.get("mom_usage_percent"),
            "_breakeven":     row.get("breakeven_estimate", ""),
            "_project_group": row.get("_project_group", ""),
            "_client":        row.get("CLIENT", ""),
        })

    col_defs = [
        {"field": "Client",      "sortable": True,"width": 140},
        {"field": "Project",     "sortable": True,"width": 150,
         "cellStyle": {"function": "return params.data._hide_roi ? {paddingLeft: '28px'} : {}"}},
        {"field": "Activated",   "sortable": True,"flex": 1, "minWidth": 100},
        {"field": "1 mo",        "sortable": True,"flex": 1, "minWidth": 60,  "type": "numericColumn"},
        {"field": "MoM %",       "sortable": True,"flex": 1, "minWidth": 70,
         "cellStyle": {"function": "params.data._mom_pct_raw == null ? {} : params.data._mom_pct_raw > 0 ? {background: '#d4edda', fontWeight: '600'} : params.data._mom_pct_raw < 0 ? {background: '#f8d7da', fontWeight: '600'} : {}"}},
        {"field": "3 mo",        "sortable": True,"flex": 1, "minWidth": 60,  "type": "numericColumn"},
        {"field": "12 mo",       "sortable": True,"flex": 1, "minWidth": 60,  "type": "numericColumn"},
        {"field": "Hours Saved", "sortable": True,"flex": 1, "minWidth": 90},
        {"field": "Investment",  "sortable": True,"flex": 1, "minWidth": 90},
        {"field": "Total Saved", "sortable": True,"flex": 1, "minWidth": 95},
        {"field": "ROI %",       "sortable": True,"flex": 1, "minWidth": 70,
         "cellStyle": {"function": "params.data._roi_pct_raw == null ? {} : params.data._roi_pct_raw >= 100 ? {background: '#d4edda', fontWeight: '600'} : params.data._roi_pct_raw >= 70 ? {background: '#fff3cd', fontWeight: '600'} : {background: '#f8d7da', fontWeight: '600'}"}},
    ]

    return col_defs, rows


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
                html.Label("Filter by Status", style={"color": "white", "fontWeight": "600", "fontSize": "13px", "marginBottom": "4px"}),
                dcc.Dropdown(id="filter-status", options=[], value="All",
                             clearable=False, style={"fontSize": "13px"}),
            ]),
        ],
    )


def make_metric_card(title, value_id, icon=""):
    return dbc.Card(
        dbc.CardBody([
            html.P(title, style={"fontSize": "12px", "color": "#666", "marginBottom": "4px", "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
            html.H4(id=value_id, children="—", style={"color": BRAND, "fontWeight": "700", "marginBottom": 0}),
        ]),
        style={
            "borderLeft": f"4px solid {BRAND}",
            "borderRadius": "8px",
            "boxShadow": "0 1px 4px rgba(0,0,0,0.08)",
        },
    )


def make_portfolio_tab():
    return dbc.Tab(
        label="Portfolio",
        tab_id="tab-portfolio",
        children=[
            # Summary cards
            dbc.Row([
                dbc.Col(make_metric_card("Total Solutions", "metric-total-solutions"), xs=12, sm=6, md=True, className="mb-3"),
                dbc.Col(make_metric_card("Hours Saved (12mo)", "metric-hours-saved"), xs=12, sm=6, md=True, className="mb-3"),
                dbc.Col(make_metric_card("Total Savings (12mo)", "metric-total-savings"), xs=12, sm=6, md=True, className="mb-3"),
                dbc.Col(make_metric_card("Total Investment", "metric-total-investment"), xs=12, sm=6, md=True, className="mb-3"),
                dbc.Col(make_metric_card("ROI Reached", "metric-roi-reached"), xs=12, sm=6, md=True, className="mb-3"),
            ], className="mb-4"),

            # Column visibility toggle
            html.Div([
                dbc.DropdownMenu(
                    label="Columns",
                    id="columns-dropdown",
                    color="light",
                    size="sm",
                    style={"marginBottom": "12px"},
                    children=dbc.Checklist(
                        id="column-visibility",
                        options=[
                            {"label": col, "value": col}
                            for col in ["Project", "Activated", "1 mo", "MoM %", "3 mo", "12 mo", "Hours Saved", "Investment", "Total Saved", "ROI %"]
                        ],
                        value=["Project", "Activated", "1 mo", "MoM %", "3 mo", "12 mo", "Hours Saved", "Investment", "Total Saved", "ROI %"],
                        style={"padding": "8px 16px"},
                    ),
                ),
            ]),

            # Portfolio table (grouped by client)
            dcc.Loading(
                id="loading-table",
                type="circle",
                color=BRAND,
                children=html.Div(id="client-accordion-container"),
            ),

            # Solution details panel
            html.Div(id="solution-details", style={"marginTop": "24px"}),
        ],
    )


def make_settings_tab():
    return dbc.Tab(
        label="Settings",
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
        dcc.Store(id="hidden-store"),            # holds hidden projects list
        dcc.Store(id="col-vis-store", storage_type="local"),  # persists column visibility across reloads

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
@app.callback(
    Output("filter-client", "options"),
    Output("filter-project", "options"),
    Output("filter-status", "options"),
    Input("data-store", "data"),
)
def update_filter_options(store_data):
    df = df_from_store(store_data)
    if df.empty:
        empty = [{"label": "All", "value": "All"}]
        return empty, empty, empty

    clients = ["All"] + sorted(df["CLIENT"].dropna().unique().tolist())
    projects = ["All"] + sorted(df["PROJECT"].dropna().unique().tolist())
    statuses = ["All"] + sorted(df["roi_status"].dropna().unique().tolist())

    return (
        [{"label": c, "value": c} for c in clients],
        [{"label": p, "value": p} for p in projects],
        [{"label": s, "value": s} for s in statuses],
    )


# ---------------------------------------------------------------------------
# Column visibility persistence
# ---------------------------------------------------------------------------
ALL_COLS = ["Project", "Activated", "1 mo", "MoM %", "3 mo", "12 mo", "Hours Saved", "Investment", "Total Saved", "ROI %"]

@app.callback(
    Output("col-vis-store", "data"),
    Input("column-visibility", "value"),
    prevent_initial_call=True,
)
def save_col_visibility(value):
    return value

@app.callback(
    Output("column-visibility", "value"),
    Input("url", "pathname"),
    State("col-vis-store", "data"),
)
def load_col_visibility(_, stored):
    return stored if stored is not None else ALL_COLS


# ---------------------------------------------------------------------------
# 3. Update portfolio table based on filters
# ---------------------------------------------------------------------------
@app.callback(
    Output("client-accordion-container", "children"),
    Input("data-store", "data"),
    Input("filter-client", "value"),
    Input("filter-project", "value"),
    Input("filter-status", "value"),
    Input("column-visibility", "value"),
)
def update_table(store_data, client_filter, project_filter, status_filter, visible_cols):
    df = df_from_store(store_data)
    if df.empty:
        return []

    if client_filter and client_filter != "All":
        df = df[df["CLIENT"] == client_filter]
    if project_filter and project_filter != "All":
        df = df[df["PROJECT"] == project_filter]
    if status_filter and status_filter != "All":
        df = df[df["roi_status"] == status_filter]

    col_defs, all_rows = build_grid_data(df)
    visible_set = set(visible_cols or [])
    col_defs_no_client = [
        c for c in col_defs
        if c["field"] != "Client" and c["field"] in visible_set
    ]

    ROW_H, HEADER_H = 42, 48
    accordion_items = []
    for client in df["CLIENT"].unique():
        client_rows = [r for r in all_rows if r.get("Client") == client]
        grid_height = max(120, len(client_rows) * ROW_H + HEADER_H)
        grid = dag.AgGrid(
            id={"type": "client-grid", "index": client},
            rowData=client_rows,
            columnDefs=col_defs_no_client,
            defaultColDef={
                "resizable": True,
                "suppressMovable": False,
                "suppressMenu": True,
                "cellStyle": {"fontSize": "13px"},
            },
            dashGridOptions={
                "rowSelection": "single",
                "animateRows": True,
                "suppressCellFocus": True,
            },
            style={"height": f"{grid_height}px", "width": "100%"},
            className="ag-theme-alpine",
        )

        accordion_items.append(
            dbc.AccordionItem(
                grid,
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
    Output("metric-hours-saved", "children"),
    Output("metric-total-savings", "children"),
    Output("metric-total-investment", "children"),
    Output("metric-roi-reached", "children"),
    Input("data-store", "data"),
    Input("filter-client", "value"),
    Input("filter-project", "value"),
    Input("filter-status", "value"),
)
def update_metrics(store_data, client_filter, project_filter, status_filter):
    df = df_from_store(store_data)
    if df.empty:
        return "—", "—", "—", "—", "—"

    if client_filter and client_filter != "All":
        df = df[df["CLIENT"] == client_filter]
    if project_filter and project_filter != "All":
        df = df[df["PROJECT"] == project_filter]
    if status_filter and status_filter != "All":
        df = df[df["roi_status"] == status_filter]

    total_solutions = len(df)

    hours_saved = df["time_saved_hours_12mo"].sum() if "time_saved_hours_12mo" in df.columns else 0
    total_savings = df["cost_saved_12mo"].sum() if "cost_saved_12mo" in df.columns else 0

    primary_df = df[df["_split_primary"] == True] if "_split_primary" in df.columns else df
    total_investment = primary_df["project_cost"].sum() if "project_cost" in primary_df.columns else 0
    roi_reached = int(primary_df["roi_reached"].sum()) if "roi_reached" in primary_df.columns else 0

    return (
        str(total_solutions),
        fmt_hours(hours_saved),
        fmt_currency(total_savings),
        fmt_currency(total_investment),
        f"{roi_reached}",
    )


# ---------------------------------------------------------------------------
# 5. Solution details panel on row selection
# ---------------------------------------------------------------------------
@app.callback(
    Output("solution-details", "children"),
    Input({"type": "client-grid", "index": dash.ALL}, "selectedRows"),
    State("data-store", "data"),
)
def show_solution_details(all_selected_rows, store_data):
    selected_rows = next((sr for sr in all_selected_rows if sr), None)
    if not selected_rows:
        return html.Div(
            "Click a row to see solution details.",
            style={"color": "#999", "fontStyle": "italic", "textAlign": "center", "padding": "32px"},
        )

    row = selected_rows[0]
    df = df_from_store(store_data)

    # Find matching row in full df for chart data
    client = row.get("_client", row.get("Client", ""))
    project = row.get("Project", "")
    matching = df[(df["CLIENT"] == client) & (df["PROJECT"] == project)] if not df.empty else pd.DataFrame()

    # --- Metric pills ---
    pills = dbc.Row([
        dbc.Col(_detail_pill("Usage (1mo)", row.get("_usage_1mo", "—")), xs=6, sm=4, md=2),
        dbc.Col(_detail_pill("MoM %", row.get("_mom_pct", "—")), xs=6, sm=4, md=2),
        dbc.Col(_detail_pill("Hours Saved", row.get("_hours_saved", "—")), xs=6, sm=4, md=2),
        dbc.Col(_detail_pill("Total Saved", row.get("_total_saved", "—")), xs=6, sm=4, md=2),
        dbc.Col(_detail_pill("ROI %", row.get("_roi_pct", "—")), xs=6, sm=4, md=2),
        dbc.Col(_detail_pill("Status", row.get("_roi_status", "—")), xs=6, sm=4, md=2),
    ], className="mb-3")

    # --- Monthly usage trend chart ---
    chart = _build_trend_chart(matching)

    # --- ROI progress bar ---
    roi_bar = _build_roi_bar(row)

    # --- Break-even estimate ---
    breakeven = row.get("_breakeven", "")
    breakeven_div = html.P(
        f"Break-even estimate: {breakeven}" if breakeven else "",
        style={"fontSize": "13px", "color": "#555", "marginTop": "8px"},
    )

    title = f"{client} — {project}"
    panel = dbc.Card([
        dbc.CardHeader(
            html.H6(title, style={"margin": 0, "color": BRAND, "fontWeight": "700"}),
            style={"background": "#f0fafb"},
        ),
        dbc.CardBody([
            pills,
            html.Hr(),
            dbc.Row([
                dbc.Col(chart, md=8),
                dbc.Col([roi_bar, breakeven_div], md=4),
            ]),
        ]),
    ], style={"borderTop": f"3px solid {BRAND}", "boxShadow": "0 2px 8px rgba(0,0,0,0.08)"})

    return panel


def _detail_pill(label, value):
    return html.Div([
        html.P(label, style={"fontSize": "11px", "color": "#888", "marginBottom": "2px", "fontWeight": "600", "textTransform": "uppercase"}),
        html.P(str(value), style={"fontWeight": "700", "color": DARK, "fontSize": "15px", "marginBottom": 0}),
    ], style={"background": "#f0fafb", "borderRadius": "8px", "padding": "10px 12px", "marginBottom": "8px"})


def _build_trend_chart(matching_df):
    """Build a 12-month usage trend line chart."""
    current_month_idx = pd.Timestamp.now().month - 1
    months_ordered = []
    for i in range(11, -1, -1):
        idx = (current_month_idx - i) % 12
        months_ordered.append(MONTHS_FR[idx])

    if matching_df.empty:
        values = [0] * 12
    else:
        row_data = matching_df.iloc[0]
        values = [int(row_data.get(m, 0) or 0) for m in months_ordered]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months_ordered,
        y=values,
        mode="lines+markers",
        line={"color": BRAND, "width": 2.5},
        marker={"color": BRAND, "size": 7},
        fill="tozeroy",
        fillcolor=f"rgba(0,196,206,0.12)",
        name="Usage",
    ))
    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title={"text": "Monthly Usage (12 months)", "font": {"size": 13, "color": DARK}, "x": 0.02},
        yaxis={"gridcolor": "#eee", "showline": False, "zeroline": False},
        xaxis={"showgrid": False, "tickfont": {"size": 10}},
        height=220,
        showlegend=False,
    )

    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _build_roi_bar(row):
    """Build a custom HTML ROI progress bar."""
    roi_pct_raw = row.get("_roi_pct_raw")
    if roi_pct_raw is None or (isinstance(roi_pct_raw, float) and math.isnan(roi_pct_raw)):
        return html.Div("ROI data not available", style={"color": "#999", "fontSize": "13px"})

    clamped = max(0, min(100, roi_pct_raw + 100))   # -100% → 0, 0% → 100
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
    Input("btn-hide-project", "n_clicks"),
    Input({"type": "btn-unhide", "project": dash.ALL}, "n_clicks"),
    State("hide-project-dropdown", "value"),
    prevent_initial_call=True,
)
def manage_hidden_projects(hide_clicks, unhide_clicks, project_to_hide):
    triggered = ctx.triggered_id

    hidden = load_hidden_projects()

    if isinstance(triggered, dict) and triggered.get("type") == "btn-unhide":
        proj = triggered["project"]
        if proj in hidden:
            hidden.remove(proj)
            save_hidden_projects(hidden)
            return dbc.Alert(f"'{proj}' unhidden.", color="success", duration=3000)

    if triggered == "btn-hide-project":
        if project_to_hide and project_to_hide not in hidden:
            hidden.append(project_to_hide)
            save_hidden_projects(hidden)
            return dbc.Alert(f"'{project_to_hide}' hidden.", color="warning", duration=3000)

    return no_update


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    app.run(debug=True, port=8050)
