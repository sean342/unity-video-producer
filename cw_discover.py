import os, requests, json

EMAIL = os.environ.get("CLOUDWAYS_EMAIL")
API_KEY = os.environ.get("CLOUDWAYS_API_KEY")
SERVER_ID = "157540"

r = requests.post("https://api.cloudways.com/api/v1/oauth/access_token",
    json={"email": EMAIL, "api_key": API_KEY},
    headers={"Content-Type": "application/json"}, timeout=15)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Try different endpoints to discover valid app types
endpoints = [
    "/api/v1/support/appVersions",
    "/api/v1/support/app",
    "/api/v1/app",
    "/api/v1/server/157540/app",
]

for ep in endpoints:
    r2 = requests.get(f"https://api.cloudways.com{ep}", headers=headers, timeout=15)
    print(f"{ep}: {r2.status_code} | {r2.text[:200]}")
    print()
