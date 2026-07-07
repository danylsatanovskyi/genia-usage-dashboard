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
        "client_name": "CELLCOM",
        "projects": {
            "HR CHATBOT": {
                "supabase_table": "genia_analytics_cellcom_hrchatbot",
                "usage_field": "queries_sent",
                "value_type": "boolean",
                "investment": None,  # TODO: Add actual investment amount
                "monthly_roi_goal": None,  # TODO: Add monthly target
                "hourly_rate": None,  # TODO: Add client hourly rate
                "minutes_saved_per_usage": None,  # TODO: Add time saved per usage
                "month_activated": None  # TODO: Add activation date (YYYY-MM-DD)
            },
            "TABLEAU DE MARGE/CELLSELL": {
                "supabase_table": "genia_analytics_cellcom_tableaudemarge",
                "usage_field": "extraction_completed",
                "value_type": "boolean",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
            "ACCOUNTS PAYABLE": {
                "supabase_table": "genia_analytics_cellcom_accountspayable",
                "usage_field": "extraction_validated",
                "value_type": "numeric",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
        }
    },
    "TECHO BLOC": {
        "worksheet_name": "TECHO BLOC",
        "client_name": "TECHO BLOC",
        "projects": {
            "MATCHING": {
                "supabase_table": "genia_analytics_techobloc_matching",
                "usage_field": "matched_companies",
                "value_type": "numeric",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
        }
    },
    "HEMA-QUEBEC": {
        "worksheet_name": "HEMA-QUEBEC",
        "client_name": "HEMA-QUEBEC",
        "projects": {
            "HEMY": {
                "supabase_table": "genia_analytics_hemaquebec_hemy",
                "usage_field": "queries_sent",
                "value_type": "boolean",
                "split_by_field": "project",
                "split_values": ["hemy", "email_agent", "phone_agent"],
                "split_display_names": {
                    "hemy": "Hemy Reseaux Sociaux",
                    "email_agent": "Hemy Agent Courriel",
                    "phone_agent": "Hemy Agent Telephonique",
                },
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
            "CALENDRIER RESEAUX SOCIAUX": {
                "supabase_table": "genia_analytics_hemaquebec_calendar",
                "usage_field": "event_created",
                "value_type": "boolean",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
        }
    },
    "DIGITAD": {
        "worksheet_name": "DIGITAD",
        "client_name": "DIGITAD",
        "projects": {
            "FELLOW INTEGRATION": {
                "supabase_table": "genia_analytics_digitad_fellow-clickup-integration",
                "usage_field": "email_sent",
                "value_type": "boolean",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
            "CLICKUP INTEGRATION": {
                "supabase_table": "genia_analytics_digitad_fellow-clickup-integration",
                "usage_field": "clickup_written",
                "value_type": "boolean",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
        }
    },
    "CHEMTECH": {
        "worksheet_name": "CHEMTECH",
        "client_name": "CHEMTECH",
        "projects": {
            "WILLY": {
                "supabase_table": "genia_analytics_chemtech_willy",
                "usage_field": "queries_sent",
                "value_type": "boolean",
                "investment": None,
                "monthly_roi_goal": None,
                "hourly_rate": None,
                "minutes_saved_per_usage": None,
                "month_activated": None
            },
        }
    },
    "TOURISME MONTREAL": {
        "worksheet_name": "RETROMTL",
        "client_name": "TOURISME MONTREAL",
        "projects": {
            "FINANCIAL AID": {
                "supabase_table": "genia_analytics_tourisme-montreal_financial_aid",
                "usage_field": "file_processed",
                "value_type": "boolean"
            },
            "TICKETING": {
                "supabase_table": "genia_analytics_tourisme-montreal_ticketing",
                "usage_field": "Type",
                "value_type": "match",
                "match_value": "platform_visit",
            },
        }
    },
    # "SERIE CONSEIL": {
    #     "worksheet_name": "SERIE CONSEIL",
    #     "client_name": "SERIE CONSEIL",
    #     "projects": {
    #         # Add projects here when ready
    #     }
    # },
}