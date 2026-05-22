# Bing Webmaster to BigQuery

This project automates the retrieval of Search Performance statistics (Queries and Pages) from the Bing Webmaster API and stores them in Google BigQuery. It is designed to run daily as a Google Cloud Function.

## Features
- **Historical Backfill**: A script to fetch the last 16 months of data upon initial setup.
- **Daily Updates**: A Cloud Function-ready script that fetches and stores the last 7 days of data to keep your dataset up-to-date.
- **Secure Credentials**: Uses Google Cloud Secret Manager to store the Bing API Key.
- **Optimized Storage**: BigQuery tables are partitioned by date and clustered by Query/URL for performance.

## Setup Walkthrough

### 1. Prerequisites
- A Google Cloud Platform (GCP) project.
- A Bing Webmaster API Key (obtain from [Bing Webmaster Tools](https://www.bing.com/webmasters/)).

### 2. Google Cloud Setup
1. **Enable APIs**:
   - BigQuery API
   - Secret Manager API
   - Cloud Functions API
2. **Store Bing API Key**:
   - Go to Secret Manager and create a secret named `BING_API_KEY`.
   - Paste your Bing API Key as the secret value.
3. **Create a Service Account**:
   - Create a service account with the following roles:
     - `BigQuery Data Editor`
     - `BigQuery Job User`
     - `Secret Manager Secret Accessor`
   - Download the JSON key file for local setup (keep it secure and never commit it!).

### 3. Initial Data Backfill
Before starting daily updates, run the historical upload script to populate your tables with existing data.
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your environment variable for GCP authentication (Windows example):
   ```powershell
   $env:GOOGLE_APPLICATION_CREDENTIALS="path\to\your\service-account.json"
   ```
3. Run the script:
   ```bash
   python upload_historical_data.py
   ```

### 4. Deploy Daily Updates
Deploy the `main.py` script as a Google Cloud Function.
- **Trigger**: Cloud Pub/Sub (recommended to schedule it daily using Cloud Scheduler).
- **Runtime**: Python 3.9+
- **Entry point**: `main`

## Repository Security
This project includes a `safe-commit` skill for Gemini CLI users to ensure that credentials and sensitive files are never accidentally committed to the repository.

---
*Note: This project is intended for educational and personal use. Ensure you comply with Bing Webmaster API terms of service.*
