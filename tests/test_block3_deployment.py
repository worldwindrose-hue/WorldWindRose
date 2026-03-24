"""Tests for Block 3: VPS deployment files."""

from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_dockerfile_production_exists():
    assert (ROOT / "Dockerfile.production").exists()
    content = (ROOT / "Dockerfile.production").read_text()
    assert "FROM python:3.11-slim" in content
    assert "HEALTHCHECK" in content
    assert "rosa" in content  # non-root user


def test_docker_compose_production_exists():
    assert (ROOT / "docker-compose.production.yml").exists()
    content = (ROOT / "docker-compose.production.yml").read_text()
    assert "restart: always" in content
    assert "rosa_memory" in content
    assert "nginx" in content


def test_nginx_conf_exists():
    assert (ROOT / "nginx.conf").exists()
    content = (ROOT / "nginx.conf").read_text()
    assert "proxy_pass" in content
    assert "WebSocket" in content or "upgrade" in content.lower()


def test_sync_memory_script_exists_and_executable():
    script = ROOT / "scripts" / "sync_memory.sh"
    assert script.exists()
    content = script.read_text()
    assert "rsync" in content
    assert "ROSA_VPS" in content
    import os
    assert os.access(script, os.X_OK)


def test_deploy_vps_script_exists():
    script = ROOT / "scripts" / "deploy_vps.sh"
    assert script.exists()
    content = script.read_text()
    assert "docker-compose" in content
    assert "rsync" in content


def test_cloudflare_tunnel_script_exists():
    script = ROOT / "scripts" / "setup_cloudflare_tunnel.sh"
    assert script.exists()
    content = script.read_text()
    assert "cloudflared" in content
    assert "TUNNEL_PROVIDER" in content or "cloudflare" in content.lower()
