import os
import json
from google.cloud import secretmanager

def load_config(file_path="config.json"):
    """Loads the public policy configuration."""
    with open(file_path, "r") as f:
        return json.load(f)

def get_registry(project_id_default, secret_id):
    """Retrieves the site registry and global credentials."""
    # Try getting project_id from env first, otherwise use default
    project_id = os.environ.get("PROJECT_ID", project_id_default)

    registry = {
        "bing_api_key": None,
        "project_id": project_id,
        "sites": []
    }

    # 1. Try local JSON first
    if os.path.exists("bing_credentials.json"):
        try:
            with open("bing_credentials.json", "r") as f:
                config_file = json.load(f)
                registry.update(config_file)
        except Exception as e:
            print(f"Error reading site registry: {e}")

    # 2. Fallback to environment variables for sites configuration
    if not registry.get("sites"):
        sites_config_str = os.environ.get("SITES_CONFIG")
        if sites_config_str:
            try:
                registry["sites"] = json.loads(sites_config_str)
                print(f"Loaded {len(registry['sites'])} sites from SITES_CONFIG env var.")
            except Exception as e:
                print(f"Error parsing SITES_CONFIG env var: {e}")
        
        # If still empty, fall back to single SITE_URL and DATASET_ID
        if not registry.get("sites"):
            site_url = os.environ.get("SITE_URL")
            dataset_id = os.environ.get("DATASET_ID")
            if site_url and dataset_id:
                registry["sites"] = [{"site_url": site_url, "dataset_id": dataset_id}]
                print(f"Loaded site {site_url} with dataset {dataset_id} from env vars.")

    # 3. Fallback to Secret Manager for API Key
    if not registry.get("bing_api_key"):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{registry['project_id']}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            registry["bing_api_key"] = response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Secret Manager error: {e}")
            registry["bing_api_key"] = os.environ.get("BING_API_KEY")

    return registry

