import time
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

def upload_rows(client, project_id, dataset_id, table_id, schema, rows, partitioning_field="Date", clustering_fields=None, location="EU"):
    """
    BigQuery uploader with clear-and-insert (overwrite) support for mutable recent data.
    """
    if not rows:
        print(f"No rows to upload for {table_id}.")
        return

    # 1. Ensure Dataset exists
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = location
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"Created dataset {dataset_id} in {location}")

    # 2. Ensure Table exists
    table_ref = dataset_ref.table(table_id)
    table = bigquery.Table(table_ref, schema=schema)
    if partitioning_field:
        table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field=partitioning_field)
    if clustering_fields:
        table.clustering_fields = clustering_fields

    try:
        client.get_table(table_ref)
    except NotFound:
        table = client.create_table(table, timeout=30)
        print(f"Created table {table_id}. Waiting for propagation...")
        time.sleep(10)

    # 3. In-Memory Deduplication of input data (just in case)
    seen = set()
    deduped_rows = []
    for r in rows:
        if "Url" in r:
            key = (r["Date"], r.get("SiteUrl"), r["Url"])
        elif "Query" in r:
            key = (r["Date"], r.get("SiteUrl"), r["Query"])
        else:
            key = (r["Date"], r.get("SiteUrl"))
            
        if key not in seen:
            seen.add(key)
            deduped_rows.append(r)
    
    original_count = len(rows)
    rows = deduped_rows
    if len(rows) < original_count:
        print(f"In-memory deduplication reduced count from {original_count} to {len(rows)} rows.")

    # 4. Overwrite Strategy: Delete existing records in BigQuery for the sliding date window
    cutoff_date = min(r["Date"] for r in rows)
    try:
        # Add SiteUrl filter if present in rows
        site_url_val = rows[0].get("SiteUrl")
        site_url_filter = f" AND SiteUrl = '{site_url_val}'" if site_url_val else ""
        
        delete_query = f"DELETE FROM `{project_id}.{dataset_id}.{table_id}` WHERE Date >= '{cutoff_date}'{site_url_filter}"
        print(f"Clearing old records: {delete_query}")
        delete_job = client.query(delete_query)
        delete_job.result() # Wait for completion
        print(f"Successfully cleared old records in {table_id} for Date >= {cutoff_date}.")
    except Exception as e:
        print(f"Clear query skipped (table might be empty or query failed): {e}")

    # 5. Insert
    errors = client.insert_rows_json(table_ref, rows)
    if not errors:
        print(f"Successfully loaded {len(rows)} rows into {dataset_id}.{table_id}.")
    else:
        print(f"BigQuery Insert Errors in {table_id}: {errors}")

