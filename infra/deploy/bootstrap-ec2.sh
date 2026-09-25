#!/usr/bin/env bash
# One-shot bootstrap for the demo instance (Ubuntu 24.04 LTS, t3.large).
# Run ONCE on the EC2 box, as root (or with sudo):
#   sudo bash bootstrap-ec2.sh
#
# It only installs the runtime: Docker + compose plugin, a small swap file and
# the deployment directory. Images are built in CI and pulled from ECR, so the
# instance never compiles anything.
set -euo pipefail

echo "==> Installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg git unzip

echo "==> Installing Docker Engine + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
	curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
usermod -aG docker ubuntu || true

echo "==> Adding a 2 GB swap file (safety net for bursts)"
if [ ! -f /swapfile ]; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

echo "==> Preparing the deployment directory"
mkdir -p /opt/shift-rescue
chown ubuntu:ubuntu /opt/shift-rescue

echo "==> Verifying"
docker --version
docker compose version
echo "Bootstrap complete. Next: run the Deploy workflow from GitHub Actions."
