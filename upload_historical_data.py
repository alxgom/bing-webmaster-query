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

# Load Public Config
with open("config.json", "r") as f:
    CONFIG = json.load(f)

DATASET_ID = CONFIG["dataset_id"]
LOCATION = CONFIG["location"]
TABLE_QUERIES = CONFIG["tables"]["queries"]
TABLE_PAGES = CONFIG["tables"]["pages"]
TABLE_SITE_DAILY = CONFIG["tables"]["site_daily"]
SECRET_ID = CONFIG["secret_id"]

def get_credentials():
    """Retrieves credentials from local JSON or environment variables."""
    creds = {
        "bing_api_key": None,
        "site_url": "https://alexisgomel.com/", # Default
        "project_id": "web-alexisgomel" # Default
    }

    # 1. Try local JSON first (for local development)
    if os.path.exists("bing_credentials.json"):
        try:
            with open("bing_credentials.json", "r") as f:
                config_file = json.load(f)
                creds.update(config_file)
        except Exception as e:
            print(f"Error reading local credentials: {e}")

    # 2. Fallback to Secret Manager for API Key if not found locally
    if not creds.get("bing_api_key"):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{creds['project_id']}/secrets/{SECRET_ID}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            creds["bing_api_key"] = response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Secret Manager error: {e}")
            creds["bing_api_key"] = os.environ.get("BING_API_KEY")

    return creds

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
    """Fetches all available historical stats from Bing Webmaster API (usually last 16 months)."""
    if not api_key:
        print("API Key is missing. Cannot fetch data.")
        return []

    encoded_url = urllib.parse.quote(site_url, safe='')
    endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/{endpoint_method}?siteUrl={encoded_url}&apikey={api_key}"
    
    print(f"Fetching historical {endpoint_method} for {site_url} ...")
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

def upload_to_bigquery(data_records, project_id, dataset_id, table_id, data_type):
    """Uploads records to BigQuery, creating dataset/table if needed."""
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
        print(f"Created dataset {dataset_id} in {LOCATION}")
        
    # Ensure table exists
    table_ref = dataset_ref.table(table_id)
    
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
        string_field_name = "Query"
        schema = [
            bigquery.SchemaField("Date", "DATE"),
            bigquery.SchemaField(string_field_name, "STRING"),
            bigquery.SchemaField("Impressions", "INTEGER"),
            bigquery.SchemaField("Clicks", "INTEGER"),
            bigquery.SchemaField("AvgImpressionPosition", "FLOAT64"),
            bigquery.SchemaField("AvgClickPosition", "FLOAT64"),
        ]
        clustering_fields = [string_field_name]

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
        
    # Format and Insert
    rows_to_insert = []
    for s in data_records:
        row = {"Date": parse_bing_date(s.get("Date"))}
        
        if data_type == "site_daily":
            row["Impressions"] = s.get("Impressions", 0)
            row["Clicks"] = s.get("Clicks", 0)
        elif data_type == "page":
            url = s.get("Query", "") # Bing uses 'Query' for URLs in GetPageStats
            row["Url"] = url
            path = re.sub(r'^https?://[^/]+', '', url)
            row["LandingPath"] = path if path else "/"
            row["Impressions"] = s.get("Impressions", 0)
            row["Clicks"] = s.get("Clicks", 0)
            row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
            row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)
        else: # query
            string_field_name = "Query"
            row[string_field_name] = s.get(string_field_name, "")
            row["Impressions"] = s.get("Impressions", 0)
            row["Clicks"] = s.get("Clicks", 0)
            row["AvgImpressionPosition"] = s.get("AvgImpressionPosition", 0.0)
            row["AvgClickPosition"] = s.get("AvgClickPosition", 0.0)
            
        rows_to_insert.append(row)
        
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if not errors:
        print(f"Successfully loaded {len(rows_to_insert)} historical rows into {table_id}.")
    else:
        print(f"Errors in {table_id}: {errors}")

def main():
    creds = get_credentials()
    if not creds["bing_api_key"]:
        print("Failed to retrieve API Key.")
        return

    # 1. Historical Query Stats
    query_stats = fetch_bing_data(creds["bing_api_key"], creds["site_url"], "GetQueryStats")
    upload_to_bigquery(query_stats, creds["project_id"], DATASET_ID, TABLE_QUERIES, "query")

    print("-" * 30)

    # 2. Historical Page Stats
    page_stats = fetch_bing_data(creds["bing_api_key"], creds["site_url"], "GetPageStats")
    upload_to_bigquery(page_stats, creds["project_id"], DATASET_ID, TABLE_PAGES, "page")

    print("-" * 30)

    # 3. Historical Site Daily Stats
    site_stats = fetch_bing_data(creds["bing_api_key"], creds["site_url"], "GetRankAndTrafficStats")
    upload_to_bigquery(site_stats, creds["project_id"], DATASET_ID, TABLE_SITE_DAILY, "site_daily")

if __name__ == "__main__":
    main()
