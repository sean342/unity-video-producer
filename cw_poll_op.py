import os, requests, json, time

EMAIL = os.environ.get("CLOUDWAYS_EMAIL")
API_KEY = os.environ.get("CLOUDWAYS_API_KEY")
SERVER_ID = "157540"
OPERATION_ID = "127271843"

r = requests.post("https://api.cloudways.com/api/v1/oauth/access_token",
    json={"email": EMAIL, "api_key": API_KEY},
    headers={"Content-Type": "application/json"}, timeout=15)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Poll operation status
print(f"Polling operation {OPERATION_ID}...")
for i in range(20):
    r2 = requests.get(f"https://api.cloudways.com/api/v1/operation/{OPERATION_ID}",
        headers=headers, timeout=15)
    data = r2.json()
    status = data.get("operation", {}).get("status", "unknown")
    print(f"  [{i+1}] Status: {status}")
    if status in ("completed", "failed"):
        print(f"Full response: {json.dumps(data, indent=2)}")
        break
    time.sleep(8)

# List apps on server to find the new one
print("\nListing apps on server...")
r3 = requests.get(f"https://api.cloudways.com/api/v1/app?server_id={SERVER_ID}",
    headers=headers, timeout=15)
print(f"Apps status: {r3.status_code}")
try:
    apps_data = r3.json()
    apps = apps_data.get("apps", [])
    print(f"Total apps: {len(apps)}")
    for a in apps:
        print(f"  ID: {a.get('id')} | Label: {a.get('label')} | App: {a.get('application')} | Status: {a.get('status')} | URL: {a.get('app_fqdn','')}")
except Exception as e:
    print(f"Error: {e}")
    print(r3.text[:300])
