#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 24.04 Lightsail server. Run from your Mac:
#   ssh ubuntu@<server-ip> 'bash -s' < deploy/setup-server.sh
set -euo pipefail

# Docker Engine + Compose plugin
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

# 2 GB swap so image builds don't run a small server out of memory
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Automatic security updates
sudo apt-get update -y
sudo apt-get install -y unattended-upgrades rsync
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# Shared network that Caddy and every app join
sudo docker network inspect web >/dev/null 2>&1 || sudo docker network create web

sudo mkdir -p /srv/caddy /srv/fake-sportsbook /srv/site
sudo chown "$USER:$USER" /srv/caddy /srv/fake-sportsbook /srv/site

echo "Done. Log out and back in so the docker group applies."
