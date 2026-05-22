import os
import json
from google.cloud import secretmanager

def load_config(file_path="config.json"):
    """Loads the public policy configuration."""
    with open(file_path, "r") as f:
        return json.load(f)

def get_registry(project_id_default, secret_id):
    """Retrieves the site registry and global credentials."""
    registry = {
        "bing_api_key": None,
        "project_id": project_id_default,
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

    # 2. Fallback to Secret Manager
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
