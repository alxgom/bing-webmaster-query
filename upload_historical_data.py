from google.cloud import bigquery
from main import process_site
from utils import load_config, get_registry

# Load Configuration
CONFIG = load_config()
SECRET_ID = CONFIG["secret_id"]

def main():
    registry = get_registry(project_id_default="web-alexisgomel", secret_id=SECRET_ID)
    if not registry["bing_api_key"]:
        print("Failed to retrieve API Key.")
        return

    if not registry["sites"]:
        print("No sites found in registry.")
        return

    client = bigquery.Client(project=registry["project_id"])

    for site in registry["sites"]:
        print(f"--- STARTING HISTORICAL BACKFILL: {site['site_url']} ---")
        # days_back=None means fetch everything
        process_site(client, registry, site, days_back=None)
        print(f"--- COMPLETED HISTORICAL BACKFILL: {site['site_url']} ---")

if __name__ == "__main__":
    main()
