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
SECRET_ID = "BING_API_KEY"  # Name of the secret in GCP Secret Manager

def get_secret(project_id, secret_id, version_id="latest"):
    """Retrieves a secret from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Error retrieving secret {secret_id}: {e}")
        return None

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

def upload_to_bigquery(data_records, project_id, dataset_id, table_id, data_type):
    """Uploads parsed records to BigQuery, creating dataset/table if needed."""
    if not data_records:
        print(f"No records to upload for {table_id}.")
        return
        
    client = bigquery.Client(project=project_id)
    
    # 1. Create dataset if it doesn't exist
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)
    dataset = bigquery.Dataset(dataset_ref)
    
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"Created dataset {client.project}.{dataset.dataset_id}")
        
    # 2. Create table if it doesn't exist
    table_ref = dataset_ref.table(table_id)
    
    # Determine the name of the string field based on the data type
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
    
    # Add partitioning and clustering
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="Date"
    )
    table.clustering_fields = [string_field_name]
    
    try:
        client.get_table(table_ref)
        print(f"Table {table_id} already exists.")
    except NotFound:
        table = client.create_table(table, timeout=30)
        print(f"Created table {table_id}.")
        
    # 3. Format rows for BigQuery
    rows_to_insert = []
    for s in data_records:
        string_val = s.get("Query", "")
        
        row = {
            "Date": parse_bing_date(s.get("Date")),
            string_field_name: string_val,
            "Impressions": s.get("Impressions", 0),
            "Clicks": s.get("Clicks", 0),
            "AvgImpressionPosition": s.get("AvgImpressionPosition", 0),
            "AvgClickPosition": s.get("AvgClickPosition", 0)
        }
        rows_to_insert.append(row)
        
    # 4. Insert data
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if not errors:
        print(f"Successfully loaded {len(rows_to_insert)} rows into {dataset_id}.{table_id}.")
    else:
        print(f"Encountered errors while inserting rows into {table_id}: {errors}")

def main(request=None):
    """
    Entry point for Cloud Function.
    The 'request' parameter is for HTTP triggers in Google Cloud Functions.
    """
    # 0. Retrieve API Key from Secret Manager
    api_key = get_secret(PROJECT_ID, SECRET_ID)
    if not api_key:
        return "Failed to retrieve API Key from Secret Manager", 500

    # 1. Fetch and upload Query Stats
    query_stats = fetch_bing_data(api_key, SITE_URL, "GetQueryStats")
    if query_stats:
        print(f"Found {len(query_stats)} query records.")
        upload_to_bigquery(query_stats, PROJECT_ID, DATASET_ID, TABLE_QUERIES, "query")
    else:
        print("No query stats to upload.")

    print("-" * 30)

    # 2. Fetch and upload Page Stats
    page_stats = fetch_bing_data(api_key, SITE_URL, "GetPageStats")
    if page_stats:
        print(f"Found {len(page_stats)} page records.")
        upload_to_bigquery(page_stats, PROJECT_ID, DATASET_ID, TABLE_PAGES, "page")
    else:
        print("No page stats to upload.")

    return "Process complete", 200

if __name__ == "__main__":
    # Local execution (requires GOOGLE_APPLICATION_CREDENTIALS for local auth)
    # and locally set BING_API_KEY if not fetching from Secret Manager
    main()
