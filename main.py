import re
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from bing_api import fetch_bing_data, parse_bing_date
from bigquery_io import upload_rows
from utils import load_config, get_registry

# Load Configuration
CONFIG = load_config()
LOCATION = CONFIG["location"]
TABLES = CONFIG["tables"]
SECRET_ID = CONFIG["secret_id"]

def process_site(bq_client, registry, site, days_back=7):
    """Processes a single site: fetch from Bing, map to BQ, and upload."""
    site_url = site["site_url"]
    dataset_id = site["dataset_id"]
    api_key = registry["bing_api_key"]
    project_id = registry["project_id"]

    print(f"--- Processing: {site_url} ---")

    # 1. Fetch Data
    endpoints = {
        "queries": "GetQueryStats",
        "pages": "GetPageStats",
        "site_daily": "GetRankAndTrafficStats"
    }

    cutoff_date = None
    if days_back:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')

    for data_type, method in endpoints.items():
        raw_data = fetch_bing_data(api_key, site_url, method)
        if not raw_data:
            continue

        # 2. Map & Filter
        rows = []
        for s in raw_data:
            parsed_date = parse_bing_date(s.get("Date"))
            if not parsed_date: continue
            
            # Date Filter
            if cutoff_date and parsed_date < cutoff_date:
                continue

            row = {
                "Date": parsed_date,
                "SiteUrl": site_url
            }
            if data_type == "site_daily":
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
            elif data_type == "pages":
                url = s.get("Query", "") # Bing uses 'Query' for URL in GetPageStats
                row["Url"] = url
                path = re.sub(r'^https?://[^/]+', '', url)
                row["LandingPath"] = path if path else "/"
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
                row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
                row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)
            else: # queries
                val = s.get("Query", "")
                row["Query"] = val
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
                row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
                row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)

            rows.append(row)

        # 3. Define Schema and Upload
        table_id = TABLES[data_type]
        schema = [
            bigquery.SchemaField("Date", "DATE"),
            bigquery.SchemaField("SiteUrl", "STRING")
        ]
        clustering_fields = []

        if data_type == "site_daily":
            schema += [
                bigquery.SchemaField("Impressions", "INTEGER"),
                bigquery.SchemaField("Clicks", "INTEGER")
            ]
            clustering_fields = ["SiteUrl"]
        elif data_type == "pages":
            schema += [
                bigquery.SchemaField("Url", "STRING"),
                bigquery.SchemaField("LandingPath", "STRING"),
                bigquery.SchemaField("Impressions", "INTEGER"),
                bigquery.SchemaField("Clicks", "INTEGER"),
                bigquery.SchemaField("AvgImpressionPosition", "FLOAT64"),
                bigquery.SchemaField("AvgClickPosition", "FLOAT64")
            ]
            clustering_fields = ["SiteUrl", "LandingPath"]
        else: # queries
            schema += [
                bigquery.SchemaField("Query", "STRING"),
                bigquery.SchemaField("Impressions", "INTEGER"),
                bigquery.SchemaField("Clicks", "INTEGER"),
                bigquery.SchemaField("AvgImpressionPosition", "FLOAT64"),
                bigquery.SchemaField("AvgClickPosition", "FLOAT64")
            ]
            clustering_fields = ["SiteUrl", "Query"]

        upload_rows(
            bq_client, project_id, dataset_id, table_id, 
            schema, rows, clustering_fields=clustering_fields, 
            location=LOCATION
        )

def main(request=None):
    # Standard GCP project default if not in registry
    registry = get_registry(project_id_default="web-alexisgomel", secret_id=SECRET_ID)
    if not registry["bing_api_key"]:
        return "Failed to retrieve API Key", 500

    client = bigquery.Client(project=registry["project_id"])

    for site in registry["sites"]:
        process_site(client, registry, site)

    return "Process complete", 200

if __name__ == "__main__":
    main()
