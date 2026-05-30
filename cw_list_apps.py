import os, requests, json, time

EMAIL = os.environ.get("CLOUDWAYS_EMAIL")
API_KEY = os.environ.get("CLOUDWAYS_API_KEY")
SERVER_ID = "157540"

print("Getting access token...")
r = requests.post("https://api.cloudways.com/api/v1/oauth/access_token",
    json={"email": EMAIL, "api_key": API_KEY},
    headers={"Content-Type": "application/json"}, timeout=15)
print(f"Token status: {r.status_code}")
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Retry up to 5 times with 30s delay
for attempt in range(5):
    print(f"\nAttempt {attempt+1}: Listing apps on server {SERVER_ID}...")
    r2 = requests.get(f"https://api.cloudways.com/api/v1/app?server_id={SERVER_ID}",
        headers=headers, timeout=15)
    print(f"Status: {r2.status_code}")
    if r2.status_code == 200:
        try:
            data = r2.json()
            apps = data.get("apps", [])
            print(f"Total apps: {len(apps)}")
            for a in apps:
                print(f"  ID: {a.get('id')} | Label: {a.get('label')} | App: {a.get('application')} | FQDN: {a.get('app_fqdn','N/A')}")
            break
        except Exception as e:
            print(f"Parse error: {e}")
            print(r2.text[:500])
    else:
        print(f"Response: {r2.text[:200]}")
        if attempt < 4:
            print(f"Waiting 30s before retry...")
            time.sleep(30)
