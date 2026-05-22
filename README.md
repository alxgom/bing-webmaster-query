# Bing Webmaster to BigQuery

This project automates the retrieval of Search Performance statistics from the Bing Webmaster API and stores them in Google BigQuery. It is designed as a **modular, scalable multi-site engine** that follows the UNIX philosophy of specialized components working together.

## Features
- **Scalable Registry**: Manage 1 or 100 websites by simply adding them to a local JSON registry.
- **Modular Architecture**: Decoupled components for Bing API logic, BigQuery IO, and global orchestration (UNIX philosophy).
- **In-Code Deduplication**: Automatically checks BigQuery before each insert to prevent duplicate records for the same date/site.
- **Daily Site-Level Stats**: Fetches daily clicks and impressions for the entire site.
- **Weekly Query & Page Stats**: Fetches detailed keyword and URL performance data.
- **Historical Backfill**: A script to fetch the last 16 months of available data for all sites in the registry.
- **Secure Credentials**: Uses Google Cloud Secret Manager for production and a private JSON registry for development.
- **Optimized Storage**: BigQuery tables are partitioned by date and clustered for performance.

## Setup Walkthrough

### 1. Prerequisites
- A Google Cloud Platform (GCP) project.
- A Bing Webmaster API Key (obtain from [Bing Webmaster Tools](https://www.bing.com/webmasters/)).

### 2. Google Cloud Setup
1. **Enable APIs**: BigQuery, Secret Manager, Cloud Functions, and Artifact Registry.
2. **Store Bing API Key**: Create a secret named `BING_API_KEY` in Secret Manager.
3. **Service Account**: Create a service account with `BigQuery Data Editor`, `BigQuery Job User`, and `Secret Manager Secret Accessor` roles.

### 3. Site Registry Configuration
1. **Global Config**: Edit `config.json` to set your preferred **GCP Region** (`EU` or `US`) and table names.
2. **Private Registry**: Create a file named `bing_credentials.json` in the root directory (this file is gitignored). Use this file to list all the websites you want to track:
```json
{
  "bing_api_key": "YOUR_BING_API_KEY",
  "project_id": "your-gcp-project-id",
  "sites": [
    {
      "site_url": "https://website-a.com/",
      "dataset_id": "seo_dataset_a"
    },
    {
      "site_url": "https://website-b.com/",
      "dataset_id": "seo_dataset_b"
    }
  ]
}
```

### 4. Initial Data Backfill
1. Install dependencies: `pip install -r requirements.txt`
2. Authenticate with GCP: `export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account.json"`
3. Run the backfill for all registered sites: `python upload_historical_data.py`

### 5. Deploy Daily Updates
Deploy the engine via the included **GitHub Actions** workflow, which uses **Workload Identity Federation** for secure, keyless deployment.

## Future Roadmap (TODO)
- **Concurrency**: Implement `asyncio` to fetch data for multiple sites in parallel to improve performance for large registries.
- **Advanced Monitoring**: Add Slack/Discord webhook alerts for failed data ingestion runs.
- **Extended Metrics**: Support for Keyword Research and Sitemap status endpoints.

---
*Note: This project is intended for educational and personal use. Ensure you comply with Bing Webmaster API terms of service.*
