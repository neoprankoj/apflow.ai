#!/usr/bin/env bash
set -euo pipefail

# Conservative Ubuntu 24.04 VPS bootstrap for APFlow AI staging.
# By default this prints the commands. Pass --execute to install Docker.

MODE="${1:---dry-run}"
APP_DIR="${APP_DIR:-/opt/apflow-ai}"

if [[ "$MODE" != "--dry-run" && "$MODE" != "--execute" ]]; then
  echo "Usage: scripts/bootstrap_vps.sh [--dry-run|--execute]" >&2
  exit 1
fi

run() {
  if [[ "$MODE" == "--execute" ]]; then
    echo "+ $*"
    "$@"
  else
    printf '%q ' "$@"
    echo
  fi
}

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This bootstrap script is intended for Ubuntu Linux VPS hosts." >&2
  exit 1
fi

if [[ "$MODE" == "--dry-run" ]]; then
  echo "Dry run. Re-run with --execute on the VPS to perform installation."
fi

run sudo apt-get update
run sudo apt-get install -y ca-certificates curl gnupg git
run sudo install -m 0755 -d /etc/apt/keyrings

if [[ "$MODE" == "--execute" ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" |
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
else
  echo "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
  echo "echo Docker apt source for the Ubuntu codename into /etc/apt/sources.list.d/docker.list"
fi

run sudo apt-get update
run sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
run sudo systemctl enable --now docker
run sudo mkdir -p "$APP_DIR"
run sudo chown "$USER:$USER" "$APP_DIR"

echo "Verifying Docker installation..."
if [[ "$MODE" == "--execute" ]]; then
  docker --version
  docker compose version
  sudo systemctl is-active docker
else
  echo "docker --version"
  echo "docker compose version"
  echo "sudo systemctl is-active docker"
fi

echo "Bootstrap complete. Copy or clone APFlow AI into $APP_DIR, then create .env.staging."
