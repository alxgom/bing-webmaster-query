import os
import urllib.request
import urllib.parse
import json
import re
import time
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound

# Load Public Policy Config
with open("config.json", "r") as f:
    CONFIG = json.load(f)

LOCATION = CONFIG["location"]
TABLE_QUERIES = CONFIG["tables"]["queries"]
TABLE_PAGES = CONFIG["tables"]["pages"]
TABLE_SITE_DAILY = CONFIG["tables"]["site_daily"]
SECRET_ID = CONFIG["secret_id"]

def get_registry():
    """Retrieves the site registry and global credentials."""
    registry = {
        "bing_api_key": None,
        "project_id": "web-alexisgomel", # Default
        "sites": []
    }

    # 1. Try local JSON first (for local development and Multi-Site Registry)
    if os.path.exists("bing_credentials.json"):
        try:
            with open("bing_credentials.json", "r") as f:
                config_file = json.load(f)
                registry.update(config_file)
        except Exception as e:
            print(f"Error reading site registry: {e}")

    # 2. Fallback to Secret Manager for API Key if not found locally
    if not registry.get("bing_api_key"):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{registry['project_id']}/secrets/{SECRET_ID}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            registry["bing_api_key"] = response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Secret Manager error: {e}")
            registry["bing_api_key"] = os.environ.get("BING_API_KEY")

    return registry

def parse_bing_date(date_str):
    """Parses Bing Webmaster API date format like /Date(1771574400000-0800)/ to YYYY-MM-DD."""
    if not date_str:
        return None
    match = re.search(r'/Date\((\d+)([+-]\d{4})?\)/', date_str)
    if match:
        timestamp_ms = int(match.group(1))
        offset_str = match.group(2)
        
        timestamp_s = timestamp_ms / 1000.0
        if offset_str:
            hours = int(offset_str[:3])
            minutes = int(offset_str[0] + offset_str[3:])
            tz = timezone(timedelta(hours=hours, minutes=minutes))
        else:
            tz = timezone.utc
            
        dt = datetime.fromtimestamp(timestamp_s, tz)
        return dt.strftime('%Y-%m-%d')
    return date_str

def fetch_bing_data(api_key, site_url, endpoint_method):
    """Fetches Stats from Bing Webmaster API based on the endpoint method."""
    if not api_key:
        print("API Key is missing. Cannot fetch data.")
        return []

    encoded_url = urllib.parse.quote(site_url, safe='')
    endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/{endpoint_method}?siteUrl={encoded_url}&apikey={api_key}"
    
    print(f"Fetching {endpoint_method} for {site_url} ...")
    req = urllib.request.Request(endpoint)
    
    try:
        with urllib.request.urlopen(req) as response:
            res = response.read()
            data = json.loads(res.decode('utf-8'))
            if "d" in data:
                return data["d"]
            else:
                print(f"No 'd' key in {endpoint_method} response data.")
                return []
    except Exception as e:
        print(f"Error fetching {endpoint_method} data from Bing: {e}")
        return []

def upload_to_bigquery(data_records, project_id, dataset_id, table_id, data_type, days_back=7):
    """Uploads recent records to BigQuery, creating dataset/table if needed."""
    if not data_records:
        print(f"No records to upload for {table_id}.")
        return
        
    client = bigquery.Client(project=project_id)
    
    # 1. Create dataset if it doesn't exist
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = LOCATION
    
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"Created dataset {client.project}.{dataset.dataset_id} in {LOCATION}")
        
    # Determine table schema and clustering
    if data_type == "site_daily":
        schema = [
            bigquery.SchemaField("Date", "DATE"),
            bigquery.SchemaField("Impressions", "INTEGER"),
            bigquery.SchemaField("Clicks", "INTEGER"),
        ]
        clustering_fields = []
    elif data_type == "page":
        schema = [
            bigquery.SchemaField("Date", "DATE"),
            bigquery.SchemaField("Url", "STRING"),
            bigquery.SchemaField("LandingPath", "STRING"),
            bigquery.SchemaField("Impressions", "INTEGER"),
            bigquery.SchemaField("Clicks", "INTEGER"),
            bigquery.SchemaField("AvgImpressionPosition", "FLOAT64"),
            bigquery.SchemaField("AvgClickPosition", "FLOAT64"),
        ]
        clustering_fields = ["LandingPath"]
    else: # query
        schema = [
            bigquery.SchemaField("Date", "DATE"),
            bigquery.SchemaField("Query", "STRING"),
            bigquery.SchemaField("Impressions", "INTEGER"),
            bigquery.SchemaField("Clicks", "INTEGER"),
            bigquery.SchemaField("AvgImpressionPosition", "FLOAT64"),
            bigquery.SchemaField("AvgClickPosition", "FLOAT64"),
        ]
        clustering_fields = ["Query"]

    table_ref = dataset_ref.table(table_id)
    table = bigquery.Table(table_ref, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="Date")
    if clustering_fields:
        table.clustering_fields = clustering_fields
    
    try:
        client.get_table(table_ref)
    except NotFound:
        table = client.create_table(table, timeout=30)
        print(f"Created table {table_id}. Waiting for propagation...")
        time.sleep(10)
        
    # 3. Format rows and filter for recent dates
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
    print(f"Filtering records for {table_id} since {cutoff_date}...")

    # --- DEDUPLICATION CHECK ---
    # Check what data already exists in BigQuery for this date range
    existing_records = set()
    try:
        query = f"""
            SELECT DISTINCT Date, {string_field_name}
            FROM `{project_id}.{dataset_id}.{table_id}`
            WHERE Date >= '{cutoff_date}'
        """
        if data_type == "site_daily":
            # Site daily doesn't have a string key, just dedupe by Date
            query = f"SELECT DISTINCT Date FROM `{project_id}.{dataset_id}.{table_id}` WHERE Date >= '{cutoff_date}'"
        
        query_job = client.query(query)
        results = query_job.result()
        for row in results:
            if data_type == "site_daily":
                existing_records.add(row.Date.strftime('%Y-%m-%d'))
            else:
                existing_records.add((row.Date.strftime('%Y-%m-%d'), row[string_field_name]))
        print(f"Found {len(existing_records)} existing records in BigQuery for the current window.")
    except Exception as e:
        print(f"Could not check for existing records (likely first run): {e}")

    rows_to_insert = []
    for s in data_records:
        parsed_date = parse_bing_date(s.get("Date"))
        
        if parsed_date and parsed_date >= cutoff_date:
            # Check if this specific record already exists
            if data_type == "site_daily":
                if parsed_date in existing_records:
                    continue
            else:
                val = s.get("Query", "")
                if (parsed_date, val) in existing_records:
                    continue

            row = {"Date": parsed_date}
            
            if data_type == "site_daily":
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
            elif data_type == "page":
                url = s.get("Query", "")
                row["Url"] = url
                path = re.sub(r'^https?://[^/]+', '', url)
                row["LandingPath"] = path if path else "/"
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
                row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
                row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)
            else: # query
                row["Query"] = s.get("Query", "")
                row["Impressions"] = s.get("Impressions", 0)
                row["Clicks"] = s.get("Clicks", 0)
                row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
                row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)
            
            rows_to_insert.append(row)
        
    if not rows_to_insert:
        print(f"No new records to insert into {table_id} (all were duplicates or outside window).")
        return

    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if not errors:
        print(f"Successfully loaded {len(rows_to_insert)} recent rows into {dataset_id}.{table_id}.")
    else:
        print(f"Errors in {table_id}: {errors}")

def main(request=None):
    registry = get_registry()
    if not registry["bing_api_key"]:
        return "Failed to retrieve API Key", 500

    if not registry["sites"]:
        print("No sites found in registry.")
        return "No sites configured", 200

    for site in registry["sites"]:
        site_url = site["site_url"]
        dataset_id = site["dataset_id"]
        print(f"Processing site: {site_url} -> Dataset: {dataset_id}")

        # 1. Query Stats
        query_stats = fetch_bing_data(registry["bing_api_key"], site_url, "GetQueryStats")
        upload_to_bigquery(query_stats, registry["project_id"], dataset_id, TABLE_QUERIES, "query")

        print("-" * 15)

        # 2. Page Stats
        page_stats = fetch_bing_data(registry["bing_api_key"], site_url, "GetPageStats")
        upload_to_bigquery(page_stats, registry["project_id"], dataset_id, TABLE_PAGES, "page")

        print("-" * 15)

        # 3. Site Daily Stats
        site_stats = fetch_bing_data(registry["bing_api_key"], site_url, "GetRankAndTrafficStats")
        upload_to_bigquery(site_stats, registry["project_id"], dataset_id, TABLE_SITE_DAILY, "site_daily")

        print("=" * 30)

    return "Process complete", 200

if __name__ == "__main__":
    main()
