import time
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

def upload_rows(client, project_id, dataset_id, table_id, schema, rows, partitioning_field="Date", clustering_fields=None, location="EU", dedupe_field=None):
    """
    Generic BigQuery uploader with deduplication support.
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

    # 3. Deduplication (In-memory filter against BigQuery)
    # We assume 'Date' is always one of the dedupe keys
    cutoff_date = min(r["Date"] for r in rows)
    existing_keys = set()
    try:
        select_fields = "Date"
        if dedupe_field:
            select_fields += f", {dedupe_field}"
            
        # Add SiteUrl filter if present in rows
        site_url_val = rows[0].get("SiteUrl")
        site_url_filter = f" AND SiteUrl = '{site_url_val}'" if site_url_val else ""
        
        query = f"SELECT DISTINCT {select_fields} FROM `{project_id}.{dataset_id}.{table_id}` WHERE Date >= '{cutoff_date}'{site_url_filter}"
        query_job = client.query(query)
        for row in query_job.result():
            if dedupe_field:
                existing_keys.add((row.Date.strftime('%Y-%m-%d'), row[dedupe_field]))
            else:
                existing_keys.add(row.Date.strftime('%Y-%m-%d'))
        
        # Filter rows
        original_count = len(rows)
        if dedupe_field:
            rows = [r for r in rows if (r["Date"], r[dedupe_field]) not in existing_keys]
        else:
            rows = [r for r in rows if r["Date"] not in existing_keys]
        
        print(f"Deduplication: {original_count} -> {len(rows)} rows (after checking BQ).")
    except Exception as e:
        print(f"Deduplication check skipped (table might be empty): {e}")

    if not rows:
        print(f"No new data to insert into {table_id}.")
        return

    # 4. Insert
    errors = client.insert_rows_json(table_ref, rows)
    if not errors:
        print(f"Successfully loaded {len(rows)} rows into {dataset_id}.{table_id}.")
    else:
        print(f"BigQuery Insert Errors in {table_id}: {errors}")
