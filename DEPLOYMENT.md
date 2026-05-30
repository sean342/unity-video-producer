# Unity Video Producer — Cloudways Deployment Guide

## Server Details

| Item | Value |
|---|---|
| Server | Personal Smek Digital |
| Server ID | 157540 |
| IP Address | 159.89.81.23 |
| Platform | Debian 11 |
| SSH User | master_srkkhpugvw |

---

## Step 1 — SSH Into the Server

```bash
ssh master_srkkhpugvw@159.89.81.23
```

If you don't have SSH keys set up, add them via Cloudways Dashboard → Server → SSH Keys.

---

## Step 2 — Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Install Python 3.11, FFmpeg, Node.js
sudo apt install -y python3.11 python3-pip python3.11-venv ffmpeg

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
python3.11 --version  # Python 3.11.x
ffmpeg -version       # FFmpeg 4.x+
node --version        # v20.x
```

---

## Step 3 — Clone the Repository

```bash
cd /var/www
sudo git clone https://github.com/sean342/unity-video-producer.git
sudo chown -R master_srkkhpugvw:master_srkkhpugvw unity-video-producer
cd unity-video-producer
```

---

## Step 4 — Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Fill in all values:

```env
ELEVENLABS_API_KEY=your_elevenlabs_key
FAL_KEY=efc35cb5-2721-4551-927a-9e551b153bb2:da72a3ac272f43067486b6bd43d05929
LEONARDO_API_KEY=your_leonardo_key
OPENAI_API_KEY=your_openai_key
APP_PASSWORD=your_team_password
APP_HOST=0.0.0.0
APP_PORT=8000
```

---

## Step 5 — Install Backend Dependencies

```bash
cd /var/www/unity-video-producer/backend
pip3 install -r requirements.txt
mkdir -p outputs
```

---

## Step 6 — Build Frontend

```bash
cd /var/www/unity-video-producer/frontend
npm install
npm run build
```

---

## Step 7 — Set Up Systemd Service

```bash
# Update the service file with correct paths if needed
sudo cp /var/www/unity-video-producer/unity-video-producer.service /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable unity-video-producer
sudo systemctl start unity-video-producer

# Check status
sudo systemctl status unity-video-producer
```

---

## Step 8 — Configure Nginx

The app runs on port 8000. Set up Nginx as a reverse proxy with basic auth:

```bash
# Install apache2-utils for htpasswd
sudo apt install -y apache2-utils

# Create password file (replace 'teamuser' and enter a password when prompted)
sudo htpasswd -c /etc/nginx/.htpasswd teamuser

# Copy the nginx config
sudo cp /var/www/unity-video-producer/nginx.conf /etc/nginx/sites-available/unity-video-producer
sudo ln -s /etc/nginx/sites-available/unity-video-producer /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # remove default site

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

The app will be accessible at `http://159.89.81.23` (or your domain).

---

## Step 9 — Set Up GitHub Actions CI/CD

In your GitHub repository (`sean342/unity-video-producer`), go to:
**Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:

| Secret Name | Value |
|---|---|
| `CLOUDWAYS_HOST` | `159.89.81.23` |
| `CLOUDWAYS_SSH_USER` | `master_srkkhpugvw` |
| `CLOUDWAYS_SSH_KEY` | Your SSH private key (the full content of `~/.ssh/id_rsa`) |

Then add the workflow file:
1. In the repo, create `.github/workflows/deploy.yml`
2. Copy the content from `.github/workflows_pending/deploy.yml`
3. Commit and push — future pushes to `main` will auto-deploy

---

## Verification

After deployment, verify the app is working:

```bash
# Check service
sudo systemctl status unity-video-producer

# Check logs
sudo journalctl -u unity-video-producer -f

# Test API
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"Unity Video Producer"}
```

Open `http://159.89.81.23` in a browser — you should see the Unity Video Producer login page.

---

## Updating the App

After the initial setup, updates deploy automatically via GitHub Actions on every push to `main`.

For manual updates:
```bash
cd /var/www/unity-video-producer
git pull origin main
cd backend && pip3 install -r requirements.txt
cd ../frontend && npm install && npm run build
sudo systemctl restart unity-video-producer
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Service won't start | Check logs: `journalctl -u unity-video-producer -n 50` |
| 502 Bad Gateway | Backend not running: `systemctl restart unity-video-producer` |
| Video generation fails | Check API keys in `.env` |
| Kling job timeout | Normal — retry the generation |
| Out of disk space | Clear old outputs: `rm -rf backend/outputs/*/` |
