# ROSA OS — VPS Deployment Guide

## Prerequisites

- VPS with Ubuntu 22.04+ (2GB RAM minimum, 4GB recommended)
- Docker + Docker Compose installed
- Domain name (optional, for HTTPS)
- OpenRouter API key

## Quick Deploy

```bash
# 1. Set VPS host
export ROSA_VPS=ubuntu@your-vps-ip

# 2. Copy .env to VPS and deploy
./scripts/deploy_vps.sh

# 3. ROSA will be running at http://your-vps-ip:8000
```

## Docker Production Stack

`Dockerfile.production` creates a minimal Python 3.11 image:
- Non-root `rosa` user (uid 1000) for security
- HEALTHCHECK at `/health` every 30s
- ENV `ROSA_MODE=cloud`

`docker-compose.production.yml` includes:
- **rosa**: Main ROSA OS server (port 8000)
- **nginx**: Reverse proxy (80/443)
- **certbot**: SSL certificate renewal (ssl profile)

```bash
# Start production stack
docker-compose -f docker-compose.production.yml up -d

# With SSL
docker-compose -f docker-compose.production.yml --profile ssl up -d
```

## Memory Sync

`scripts/sync_memory.sh` syncs the `memory/` directory between local and VPS:

```bash
# Push local memory to VPS
./scripts/sync_memory.sh push

# Pull VPS memory to local
./scripts/sync_memory.sh pull

# Auto (pull then push)
./scripts/sync_memory.sh auto
```

Add to crontab for hourly sync:
```bash
0 * * * * /path/to/scripts/sync_memory.sh auto >> /tmp/rosa_sync.log 2>&1
```

## Cloudflare Tunnel (Free Public URL)

Alternative to ngrok with no rate limits:

```bash
./scripts/setup_cloudflare_tunnel.sh 8000
# → Public URL: https://rosa-os.cfargotunnel.com

# Start tunnel
cloudflared tunnel run rosa-os
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | ✅ | Kimi K2.5 / Claude access |
| `GITHUB_TOKEN` | ⚪ | GitHub integration (60→5000 req/h) |
| `TELEGRAM_API_ID` | ⚪ | Telegram user connector |
| `TELEGRAM_API_HASH` | ⚪ | Telegram user connector |
| `TELEGRAM_PHONE` | ⚪ | Telegram user connector |
| `TELEGRAM_SESSION` | ⚪ | Telethon StringSession |
| `CLOUDFLARE_TUNNEL_URL` | ⚪ | Public URL |
| `NGROK_AUTO_START` | ⚪ | Auto-start ngrok on boot |
| `NGROK_AUTH_TOKEN` | ⚪ | ngrok authentication |

## Security Notes

- The `ImmutableKernel` (`core/security/immutable_kernel.py`) monitors core file hashes
- Seal on first deploy: `POST /api/transparency/kernel/seal`
- Check on each startup: `GET /api/transparency/kernel/status`
- Self-improvement patches never auto-apply to `core/` — only to `experimental/`

## Health Check

```bash
curl http://your-vps-ip:8000/health
# → {"status": "ok", "version": "6.0.0"}

curl http://your-vps-ip:8000/api/audit/startup
# → Startup audit report
```
