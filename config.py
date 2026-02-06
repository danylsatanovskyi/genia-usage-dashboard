import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_CREDS_FILE = "credentials.json"
GOOGLE_SPREADSHEET_NAME = "CLIENT SOLUTION REPORTING - 2026🔥"
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Company configurations - Add new companies here
COMPANY_CONFIGS = {
    "CELLCOM": {
        "worksheet_name": "CELLCOM",
        "project_name_range": "C3:C8",
        "month_header_range": "K3:V3",
        "projects": {
            "HR CHATBOT": {
                "supabase_table": "genia_analytics_cellcom_hrchatbot",
                "usage_field": "queries_sent",
                "value_type": "boolean"
            },
            "TABLEAU DE MARGE/CELLSELL": {
                "supabase_table": "genia_analytics_cellcom_tableaudemarge",
                "usage_field": "extraction_completed",
                "value_type": "boolean"
            },
            "ACCOUNTS PAYABLE": {
                "supabase_table": "genia_analytics_cellcom_accountspayable",
                "usage_field": "extraction_validated",
                "value_type": "boolean"
            },
        }
    },
    "TECHO BLOC": {
        "worksheet_name": "TECHO BLOC",
        "project_name_range": "C3:C6",
        "month_header_range": "K3:V3",
        "projects": {
            "MATCHING": {
                "supabase_table": "genia_analytics_techobloc_matching",
                "usage_field": "matched_companies",
                "value_type": "numeric"
            },
        }
    },
    "HEMA-QUEBEC": {
        "worksheet_name": "HEMA-QUEBEC",
        "project_name_range": "C3:C5",
        "month_header_range": "K3:V3",
        "projects": {
            "HEMY": {
                "supabase_table": "genia_analytics_hemaquebec_hemy",
                "usage_field": "queries_sent",
                "value_type": "boolean"
            },
            "CALENDRIER RESEAUX SOCIAUX": {
                "supabase_table": "genia_analytics_hemaquebec_calendar",
                "usage_field": "event_created",
                "value_type": "boolean"
            },
        }
    },
    "DIGITAD": {
        "worksheet_name": "DIGITAD",
        "project_name_range": "C3:C5",
        "month_header_range": "K3:V3",
        "projects": {
            "FELLOW INTEGRATION": {
                "supabase_table": "genia_analytics_digitad_fellow-clickup-integration",
                "usage_field": "email_sent",
                "value_type": "boolean"
            },
            "CLICKUP INTEGRATION": {
                "supabase_table": "genia_analytics_digitad_fellow-clickup-integration",
                "usage_field": "clickup_written",
                "value_type": "boolean"
            },
        }
    },
    "CHEMTECH": {
        "worksheet_name": "CHEMTECH",
        "project_name_range": "C3:C5",
        "month_header_range": "K3:V3",
        "projects": {
            "WILLY": {
                "supabase_table": "genia_analytics_chemtech_willy",
                "usage_field": "queries_sent",
                "value_type": "boolean"
            },
        }
    },
}