# Task 0 — data-sync sample application

FastAPI contract fixture used by Helm (Task 1) and Ansible (Task 2).

## Endpoints

| Path | Purpose |
|------|---------|
| `GET /health` | Liveness/readiness — `{"status": "ok"}` (no Redis dependency) |
| `GET /metrics` | Prometheus scrape target |
| `GET /cache/ping` | Smoke test Redis AUTH + connectivity |

## Environment variables

Copy `.env.example` → `.env` (gitignored). `python-dotenv` loads `.env` for local / VM process runs; Compose uses `env_file: .env`.

| Variable | Required | Notes |
|----------|----------|-------|
| `APP_ENV` | no (default `local`) | `staging` / `production` when deployed |
| `REDIS_HOST` | yes (default `127.0.0.1`) | Compose overrides to `redis` |
| `REDIS_PORT` | no (default `6379`) | |
| `REDIS_PASSWORD` | **yes** | Used for Redis AUTH; never commit real values |
| `LOG_LEVEL` | no | `DEBUG` for local |
| `WORKERS` | no | Config signal; use uvicorn `--workers` on VMs if desired |
| `MAX_CONNECTIONS` | no | Redis connection pool size |

---

## Option A — Docker Compose (local)

Best for laptop smoke tests without a VM.

```bash
cd task-0-sample-app
cp .env.example .env   # set REDIS_PASSWORD
docker compose up --build

curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/cache/ping
curl -s http://127.0.0.1:8080/metrics | head
```

Image tag: `data-sync:0.1.0` (referenced by Task 1 Helm values).

Compose starts **Redis with `--requirepass`** and the app on port **8080**.

---

## Option B — Run as a foreground process on a VM

Use this when validating the same path Ansible (Task 2) will automate: Python venv + uvicorn on CentOS/Rocky (or any Linux VM / Multipass / local Rocky container). No Docker required for the app process.

### 1. Prerequisites on the VM

```bash
# Rocky / CentOS 8 style (matches assignment Ansible target)
sudo dnf install -y python39 python39-pip git redis   # or yum on older images

# Ensure Redis requires a password (same value as REDIS_PASSWORD in .env)
sudo redis-cli CONFIG SET requirepass 'YOUR_REDIS_PASSWORD'
# Persist via /etc/redis.conf: requirepass YOUR_REDIS_PASSWORD, then:
sudo systemctl enable --now redis
```

On a cloud VM, open port **8080** (or front with a load balancer) only as needed for smoke tests.

### 2. Clone / copy the app and configure secrets

```bash
# Example layout aligned with Task 2: /srv/data-sync
sudo mkdir -p /srv/data-sync
sudo chown "$USER":"$USER" /srv/data-sync

# Copy this task folder contents into /srv/data-sync (or git clone your repo and cd into task-0-sample-app)
cp -a task-0-sample-app/. /srv/data-sync/
cd /srv/data-sync

cp .env.example .env
chmod 600 .env
# Edit .env — set at least:
#   REDIS_HOST=127.0.0.1   (or remote Redis hostname)
#   REDIS_PORT=6379
#   REDIS_PASSWORD=YOUR_REDIS_PASSWORD
#   APP_ENV=staging
#   LOG_LEVEL=INFO
```

### 3. Create venv and install dependencies

```bash
cd /srv/data-sync

# Prefer 3.9 on Rocky 8 to match Task 2; on newer hosts python3.13 is fine
python3.9 -m venv /srv/data-sync/venv
# or: python3.13 -m venv /srv/data-sync/venv

source /srv/data-sync/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run foreground (smoke test)

```bash
cd /srv/data-sync
set -a && source .env && set +a
source venv/bin/activate

uvicorn src.main:app --host 0.0.0.0 --port 8080
# Optional multi-worker on a VM (HPA is N/A here):
# uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers "${WORKERS:-4}"
```

From the VM or your laptop (if port is reachable):

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/cache/ping
curl -s http://127.0.0.1:8080/metrics | head
```

Stop with `Ctrl+C`. Long-lived systemd install is owned by **Task 2 Ansible**, not this README.

---

## Which option when?

| Goal | Use |
|------|-----|
| Quick local smoke + Redis | **A — Docker Compose** |
| Prove VM process path before Ansible | **B — foreground on VM** |
| Production-like VM fleet | **Task 2 Ansible** (`be-data-sync`) |
| Kubernetes | **Task 1 Helm** (image from Dockerfile) |

---

## Why Python 3.13 in Docker (not 3.9)?

The BrightEdge assignment’s **Ansible (Task 2)** text pins **Python 3.9 via yum on CentOS/Rocky 8** — that is a VM OS constraint, not a requirement for the container image.

- Python 3.9 is past end-of-life; it should not be the default for new images.
- Latest stable language line (as of this work) is **3.14**; we use **`python:3.13-slim`** as the container runtime.
- **On VMs (Option B / Task 2), use Python 3.9** as specified. Same app source; keep deps compatible with 3.9+.

## Assumptions

- Infra contract app, not full SEO business logic.
- Secrets live in `.env` on VMs/laptops and Kubernetes Secrets in cluster — never in image layers or git.
- Horizontal scale: Compose/HPA for containers; more VM hosts or uvicorn `--workers` for process installs.

## Future scalability

- Split readiness (Redis AUTH ping) from liveness (process-only).
- External Secrets / sealed secrets instead of plain `.env` on shared hosts.
- Redis ACL users; dual-password rotation (see Task 3 design).
