# Unity Video Producer

Internal web application for generating Unity mascot videos for Unified Home Remodeling.

## Overview

Unity Video Producer is a full-stack web app that automates the creation of branded social media videos featuring **Unity**, Unified's golden retriever mascot. Team members can generate professional 9:16 vertical videos without needing Manus or any technical knowledge.

### Pipeline

```
Topic + Format + Length
        ↓
  GPT-4.1-mini (script writing)
        ↓
  ElevenLabs Unity v2 (voice + timestamps)
        ↓
  Leonardo.ai (keyframe image)
        ↓
  fal.ai Kling Avatar v2 (animation + lip sync)
        ↓
  Pillow (sentence-case caption PNGs)
        ↓
  FFmpeg (assembly: captions + logo + BGM)
        ↓
  Final 9:16 MP4 (1072×1920 @ 30fps)
```

**Generation time:** ~4–6 minutes per video.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python FastAPI + async background tasks |
| Frontend | React + TypeScript + TailwindCSS |
| Voice | ElevenLabs API (Unity v2 voice) |
| Animation | fal.ai Kling Avatar v2 Pro |
| Keyframes | Leonardo.ai Diffusion XL |
| Script | OpenAI GPT-4.1-mini |
| Assembly | FFmpeg + Pillow |
| Hosting | Cloudways (Personal Smek Digital) |
| CI/CD | GitHub Actions → SSH deploy |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 20+
- FFmpeg (`sudo apt install ffmpeg`)
- All API keys (see `.env.example`)

### Setup

```bash
# Clone the repo
git clone https://github.com/sean342/unity-video-producer.git
cd unity-video-producer

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your API keys

# Install backend dependencies
cd backend
pip3 install -r requirements.txt

# Install and build frontend
cd ../frontend
npm install
npm run dev  # starts Vite dev server on :5173
```

### Start Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
The frontend dev server proxies API calls to the backend.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `GET /health` | GET | Health check |
| `POST /generate` | POST | Start a new video generation job |
| `GET /status/{job_id}` | GET | Poll job status and progress |
| `GET /download/{job_id}` | GET | Download finished MP4 |
| `GET /jobs` | GET | List all jobs (last 50) |
| `GET /docs` | GET | Interactive API docs (Swagger) |

### Generate Request Body

```json
{
  "topic": "double-pane windows",
  "format": "myth_or_fact",
  "length": "8s",
  "custom_script": null
}
```

**Formats:** `myth_or_fact` | `quick_tip` | `did_you_know`

**Lengths:** `8s` | `15s` | `20s`

---

## Cloudways Deployment

### Initial Setup (SSH into server)

```bash
# Install dependencies
sudo apt update
sudo apt install -y python3.11 python3-pip ffmpeg nodejs npm

# Clone the repo
cd /var/www
git clone https://github.com/sean342/unity-video-producer.git
cd unity-video-producer

# Set up environment
cp .env.example .env
nano .env  # fill in all API keys

# Install backend
cd backend
pip3 install -r requirements.txt

# Build frontend
cd ../frontend
npm install
npm run build

# Create outputs directory
mkdir -p backend/outputs
```

### Systemd Service

```bash
# Copy service file
sudo cp unity-video-producer.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable unity-video-producer
sudo systemctl start unity-video-producer

# Check status
sudo systemctl status unity-video-producer
```

### Nginx + Basic Auth

```bash
# Install apache2-utils for htpasswd
sudo apt install apache2-utils

# Create password file
sudo htpasswd -c /etc/nginx/.htpasswd teamuser

# Copy nginx config
sudo cp nginx.conf /etc/nginx/sites-available/unity-video-producer
sudo ln -s /etc/nginx/sites-available/unity-video-producer /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### GitHub Actions Secrets

Add these secrets to your GitHub repository (`Settings → Secrets → Actions`):

| Secret | Value |
|---|---|
| `CLOUDWAYS_HOST` | `159.89.81.23` |
| `CLOUDWAYS_SSH_USER` | `master_srkkhpugvw` |
| `CLOUDWAYS_SSH_KEY` | Your SSH private key |

---

## Unity Character Reference

| Asset | Path | Notes |
|---|---|---|
| Front view | `backend/assets/references/unity_ref_front.png` | Primary reference |
| Side view | `backend/assets/references/unity_ref_side.png` | Tail visibility |
| 3/4 angle | `backend/assets/references/unity_ref_front_3q.png` | Best for keyframes |
| Face/head | `backend/assets/references/unity_ref_face.png` | Face detail |
| Back view | `backend/assets/references/unity_ref_back.png` | Full 360° |
| Standing | `backend/assets/references/unity_ref_standing_full.png` | Full body |
| Logo | `backend/assets/templates/unified_logo.png` | Bottom-left overlay |
| BGM | `backend/assets/templates/bgm.mp3` | Background music |

**Voice ID (locked):** `RlSomJYBsxja4xRQuPgO` (Unity v2, ElevenLabs)

---

## Video Specifications

- **Resolution:** 1072×1920 (9:16 vertical)
- **Frame rate:** 30fps
- **Codec:** H.264 (libx264), CRF 18
- **Audio:** AAC 192k
- **Logo:** Unified logo, bottom-left, x=30, 35px from bottom
- **BGM:** 10% volume mixed with voice
- **Captions:** Sentence case, Pillow PNG overlays, auto font-size

---

## Production Audit Checklist

Before delivering any video, verify:

- [ ] Tail visible (golden tail present in all shots)
- [ ] Lip sync accurate (mouth matches audio)
- [ ] Character consistent (same fur, bandana, tool belt)
- [ ] Captions in sentence case (never ALL CAPS)
- [ ] No caption overflow
- [ ] Unified logo bottom-left, readable
- [ ] No fake signs on walls
- [ ] Audio balanced (voice clear, BGM subtle)
- [ ] Format: 9:16 vertical MP4
