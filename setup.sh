#!/usr/bin/env bash
# Project Holden — environment bootstrap
# Installs everything needed to run the Phase 0-1 (and beyond) test checklist.
# Run from repo root: ./setup.sh
set -euo pipefail

echo "== Project Holden setup =="

# ---- Docker (required by Containerlab) ----
if ! command -v docker &>/dev/null; then
  echo "-- Installing Docker --"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "!! You must log out/in (or run 'newgrp docker') for docker group membership to take effect."
else
  echo "-- Docker already installed --"
fi

# ---- Containerlab ----
if ! command -v containerlab &>/dev/null; then
  echo "-- Installing Containerlab --"
  bash -c "$(curl -sL https://get.containerlab.dev)"
else
  echo "-- Containerlab already installed --"
fi

# ---- Scoped sudoers rule for containerlab (avoids interactive pkexec/polkit prompts) ----
CLAB_BIN="$(command -v containerlab || echo /usr/bin/containerlab)"
SUDOERS_FILE=/etc/sudoers.d/containerlab
if [ ! -f "$SUDOERS_FILE" ]; then
  echo "-- Staging scoped sudoers rule for containerlab (requires sudo) --"
  echo "$USER ALL=(root) NOPASSWD: $CLAB_BIN" | sudo tee "$SUDOERS_FILE" > /dev/null
  sudo chmod 0440 "$SUDOERS_FILE"
  sudo visudo -c
else
  echo "-- sudoers rule for containerlab already present --"
fi

# ---- Smallstep CLI + CA (NOTE: do not use 'apt install step' — that's an unrelated KDE package) ----
if ! command -v step &>/dev/null || ! command -v step-ca &>/dev/null; then
  echo "-- Installing Smallstep step-cli + step-ca --"
  wget -O - https://packages.smallstep.com/keys/apt/repo-signing-key.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/smallstep.gpg
  echo 'deb [signed-by=/usr/share/keyrings/smallstep.gpg] https://packages.smallstep.com/stable/debian debs main' | sudo tee /etc/apt/sources.list.d/smallstep.list
  sudo apt update
  sudo apt install -y step-cli step-ca
else
  echo "-- step-cli and step-ca already installed --"
fi

# ---- HashiCorp Vault (air-gap mode) ----
if ! command -v vault &>/dev/null; then
  echo "-- Installing Vault --"
  wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
  sudo apt update
  sudo apt install -y vault
else
  echo "-- Vault already installed --"
fi

# ---- Python + project dependencies ----
if ! command -v python3 &>/dev/null; then
  sudo apt install -y python3 python3-pip python3-venv
fi

echo "-- Setting up Python virtual environment --"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Adjust this list as the project's actual requirements.txt grows.
pip install --break-system-packages \
  jsonschema \
  pyyaml \
  requests

# If you maintain a requirements.txt in the repo, prefer this instead:
if [ -f requirements.txt ]; then
  pip install --break-system-packages -r requirements.txt
fi

echo ""
echo "== Setup complete =="
echo "Verify with:"
echo "  docker --version && containerlab version && step version && step-ca version && vault --version"
echo ""
echo "If Docker was just installed, log out/in (or run 'newgrp docker') before running containerlab."
