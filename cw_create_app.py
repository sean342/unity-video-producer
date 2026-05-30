import os, requests, json

EMAIL = os.environ.get("CLOUDWAYS_EMAIL")
API_KEY = os.environ.get("CLOUDWAYS_API_KEY")
SERVER_ID = "157540"  # (Personal) Smek Digital

# Get token
r = requests.post("https://api.cloudways.com/api/v1/oauth/access_token",
    json={"email": EMAIL, "api_key": API_KEY},
    headers={"Content-Type": "application/json"}, timeout=15)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print(f"Token obtained")

# List existing apps on the server
r2 = requests.get(f"https://api.cloudways.com/api/v1/app?server_id={SERVER_ID}", headers=headers, timeout=15)
print(f"\nExisting apps status: {r2.status_code}")
try:
    apps_data = r2.json()
    apps = apps_data.get("apps", [])
    print(f"Existing apps: {len(apps)}")
    for a in apps:
        print(f"  ID: {a.get('id')} | Label: {a.get('label')} | App: {a.get('application')} | Status: {a.get('status')}")
except:
    print(f"Response: {r2.text[:300]}")

# Create new PHP app
print(f"\nCreating unity-video-producer app...")
payload = {
    "server_id": SERVER_ID,
    "application": "php",
    "app_version": "8.1",
    "app_label": "unity-video-producer"
}
r3 = requests.post("https://api.cloudways.com/api/v1/app",
    json=payload, headers=headers, timeout=30)
print(f"Create app status: {r3.status_code}")
print(f"Response: {r3.text[:500]}")
