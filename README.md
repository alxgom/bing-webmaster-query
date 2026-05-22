# Bing Webmaster to BigQuery

This project automates the retrieval of Search Performance statistics from the Bing Webmaster API and stores them in Google BigQuery. It is designed to run daily as a Google Cloud Function.

## Features
- **Daily Site-Level Stats**: Fetches daily clicks and impressions for the entire site (2-3 day lag).
- **Weekly Query & Page Stats**: Fetches detailed keyword and URL performance data (weekly buckets).
- **Historical Backfill**: A script to fetch the last 16 months of available data upon initial setup.
- **Daily Updates**: A Cloud Function-ready script that keeps your dataset up-to-date.
- **Secure Credentials**: Uses Google Cloud Secret Manager for production and a local JSON fallback for development.
- **Optimized Storage**: BigQuery tables are partitioned by date and clustered for performance.

## Setup Walkthrough

### 1. Prerequisites
- A Google Cloud Platform (GCP) project.
- A Bing Webmaster API Key (obtain from [Bing Webmaster Tools](https://www.bing.com/webmasters/)).

### 2. Google Cloud Setup
1. **Enable APIs**: BigQuery, Secret Manager, Cloud Functions, and Artifact Registry.
2. **Store Bing API Key**: Create a secret named `BING_API_KEY` in Secret Manager.
3. **Service Account**: Create a service account with `BigQuery Data Editor`, `BigQuery Job User`, and `Secret Manager Secret Accessor` roles.

### 3. Local Configuration
1. **Public Config**: Edit `config.json` to set your desired BigQuery Dataset ID, Table names, and **GCP Region** (e.g., `EU` or `US`).
2. **Private Credentials**: Create a file named `bing_credentials.json` (this file is gitignored):
```json
{
  "bing_api_key": "YOUR_BING_API_KEY",
  "site_url": "https://yourwebsite.com/",
  "project_id": "your-gcp-project-id"
}
```

### 4. Initial Data Backfill
1. Install dependencies: `pip install -r requirements.txt`
2. Authenticate with GCP: `export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account.json"`
3. Run the backfill: `python upload_historical_data.py`

### 5. Deploy Daily Updates
The recommended deployment method is via the included **GitHub Actions** workflow, which uses **Workload Identity Federation** for keyless, secure deployment. 

**Note**: To change the deployment region for the Cloud Function, update the `region` field in `.github/workflows/deploy.yml`.

## Repository Security
This project includes a `safe-commit` skill for Gemini CLI users to ensure that credentials, AI tools, and sensitive files are never accidentally committed.

---
*Note: This project is intended for educational and personal use. Ensure you comply with Bing Webmaster API terms of service.*
