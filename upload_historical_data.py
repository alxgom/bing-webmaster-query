import os
import urllib.request
import urllib.parse
import json
import re
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound

# Configuration
SITE_URL = "https://alexisgomel.com/"
PROJECT_ID = "web-alexisgomel"
DATASET_ID = "webmaster"
TABLE_QUERIES = "searchdata_queries"
TABLE_PAGES = "searchdata_pages"
SECRET_ID = "BING_API_KEY"

def get_secret(project_id, secret_id, version_id="latest"):
    """Retrieves a secret from local JSON or GCP Secret Manager."""
    # 1. Try local JSON first (for local development)
    if os.path.exists("bing_credentials.json"):
        try:
            with open("bing_credentials.json", "r") as f:
                config = json.load(f)
                return config.get("bing_api_key")
        except Exception as e:
            print(f"Error reading local credentials: {e}")

    # 2. Fallback to GCP Secret Manager
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Secret Manager not available or secret {secret_id} not found. (Using local or environment if provided). Error: {e}")
        return os.environ.get("BING_API_KEY")

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
    
    # Ensure dataset exists
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)
    dataset = bigquery.Dataset(dataset_ref)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"Created dataset {dataset_id}")
        
    # Ensure table exists
    table_ref = dataset_ref.table(table_id)
    string_field_name = "Query" if data_type == "query" else "Url"
    schema = [
        bigquery.SchemaField("Date", "DATE"),
        bigquery.SchemaField(string_field_name, "STRING"),
        bigquery.SchemaField("Impressions", "INTEGER"),
        bigquery.SchemaField("Clicks", "INTEGER"),
        bigquery.SchemaField("AvgImpressionPosition", "INTEGER"),
        bigquery.SchemaField("AvgClickPosition", "INTEGER"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="Date")
    table.clustering_fields = [string_field_name]
    
    try:
        client.get_table(table_ref)
    except NotFound:
        table = client.create_table(table, timeout=30)
        print(f"Created table {table_id}")
        
    # Format and Insert
    rows_to_insert = []
    for s in data_records:
        row = {
            "Date": parse_bing_date(s.get("Date")),
            string_field_name: s.get(string_field_name, ""),
            "Impressions": s.get("Impressions", 0),
            "Clicks": s.get("Clicks", 0),
            "AvgImpressionPosition": s.get("AvgImpressionPosition", 0),
            "AvgClickPosition": s.get("AvgClickPosition", 0)
        }
        rows_to_insert.append(row)
        
    # Large historical data might need chunking, but for 16 months of stats it's usually fine in one go.
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if not errors:
        print(f"Successfully loaded {len(rows_to_insert)} historical rows into {table_id}.")
    else:
        print(f"Errors in {table_id}: {errors}")

def main():
    api_key = get_secret(PROJECT_ID, SECRET_ID)
    if not api_key:
        print("Failed to retrieve API Key.")
        return

    # 1. Historical Query Stats
    query_stats = fetch_bing_data(api_key, SITE_URL, "GetQueryStats")
    upload_to_bigquery(query_stats, PROJECT_ID, DATASET_ID, TABLE_QUERIES, "query")

    print("-" * 30)

    # 2. Historical Page Stats
    page_stats = fetch_bing_data(api_key, SITE_URL, "GetPageStats")
    upload_to_bigquery(page_stats, PROJECT_ID, DATASET_ID, TABLE_PAGES, "page")

if __name__ == "__main__":
    main()
