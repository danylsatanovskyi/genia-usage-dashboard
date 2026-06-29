"""
One-time migration: creates project_metadata and hidden_projects tables in Supabase
and seeds them from the local JSON files.

Run with: python migrate_to_supabase.py
"""
import json, os
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# 1. Seed project_metadata
# ---------------------------------------------------------------------------
META_FILE = "project_metadata.json"
if os.path.exists(META_FILE):
    with open(META_FILE) as f:
        metadata = json.load(f)

    rows = [{"key": k, **v} for k, v in metadata.items()]
    result = sb.table("project_metadata").upsert(rows).execute()
    print(f"project_metadata: upserted {len(rows)} rows")
else:
    print("project_metadata.json not found — skipping")

# ---------------------------------------------------------------------------
# 2. Seed hidden_projects
# ---------------------------------------------------------------------------
HIDDEN_FILE = "hidden_projects.json"
if os.path.exists(HIDDEN_FILE):
    with open(HIDDEN_FILE) as f:
        hidden = json.load(f).get("hidden", [])

    if hidden:
        rows = [{"project_name": p} for p in hidden]
        sb.table("hidden_projects").upsert(rows).execute()
        print(f"hidden_projects: upserted {len(rows)} rows")
    else:
        print("hidden_projects.json is empty — nothing to migrate")
else:
    print("hidden_projects.json not found — skipping")

print("Done.")
