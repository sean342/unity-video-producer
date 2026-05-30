import os, requests, json

EMAIL = os.environ.get("CLOUDWAYS_EMAIL")
API_KEY = os.environ.get("CLOUDWAYS_API_KEY")

print(f"Email: {EMAIL}")
print(f"API Key: {API_KEY[:10] if API_KEY else 'NOT SET'}...")

# Get token
r = requests.post("https://api.cloudways.com/api/v1/oauth/access_token",
    json={"email": EMAIL, "api_key": API_KEY},
    headers={"Content-Type": "application/json"}, timeout=15)

print(f"Auth status: {r.status_code}")
print(f"Auth response: {r.text[:300]}")

if r.status_code == 200:
    token = r.json().get("access_token")
    print(f"Token: {token[:20]}...")

    # List servers
    r2 = requests.get("https://api.cloudways.com/api/v1/server",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    print(f"\nServers status: {r2.status_code}")
    data = r2.json()
    servers = data.get("servers", [])
    print(f"Total servers: {len(servers)}")
    for s in servers:
        print(json.dumps({k: s.get(k,'?') for k in ['id','label','status','public_ip','platform','server_size','master_user']}, indent=2))
