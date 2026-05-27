#!/usr/bin/env bash
# Tchoucti — one-time VPS bootstrap.
# Run as root on a fresh Debian/Ubuntu VPS.
#
#   curl -fsSL https://raw.githubusercontent.com/SergeNoah000/tchoucti/main/deploy/init-server.sh | bash
#
# or copy the file and: bash init-server.sh
#
# Does:
#   1. Updates packages, installs Docker + ufw + git
#   2. Configures the firewall (22, 80, 443)
#   3. Sets the timezone (Africa/Douala by default)
#   4. Creates /opt/tchoucti and clones the repo (uses the SSH deploy key
#      placed at /root/.ssh/id_ed25519 — copy yours there before running)
#   5. Reminds you to fill deploy/.env and then run deploy/deploy.sh

set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:SergeNoah000/tchoucti.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/tchoucti}"
TIMEZONE="${TIMEZONE:-Africa/Douala}"

log() { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run as root."
        exit 1
    fi
}

install_packages() {
    log "Updating apt + installing base packages"
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates curl gnupg lsb-release git ufw htop fail2ban
}

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        log "Docker already installed — skipping"
        return
    fi
    log "Installing Docker engine + compose plugin"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
      $(. /etc/os-release; echo "$VERSION_CODENAME") stable" \
      | tee /etc/apt/sources.list.d/docker.list >/dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
}

configure_firewall() {
    log "Configuring ufw (22, 80, 443)"
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment "SSH"
    ufw allow 80/tcp comment "HTTP (Traefik)"
    ufw allow 443/tcp comment "HTTPS (Traefik)"
    ufw --force enable
    systemctl enable --now fail2ban
}

set_timezone() {
    log "Setting timezone to $TIMEZONE"
    timedatectl set-timezone "$TIMEZONE" || true
}

ensure_deploy_key() {
    local key="/root/.ssh/id_ed25519"
    if [ ! -f "$key" ]; then
        echo
        echo "⚠️  No SSH key at $key."
        echo "    Copy your deploy private key there before re-running:"
        echo "      scp ~/.ssh/tchoucti_deploy root@<vps>:/root/.ssh/id_ed25519"
        echo "      ssh root@<vps> 'chmod 600 /root/.ssh/id_ed25519'"
        echo
        exit 1
    fi
    chmod 600 "$key"
    # Pre-trust github.com so `git clone` doesn't prompt interactively.
    ssh-keyscan -t ed25519,rsa github.com >> /root/.ssh/known_hosts 2>/dev/null || true
}

clone_or_update() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        log "Repo already cloned — pulling latest"
        git -C "$INSTALL_DIR" pull --ff-only
    else
        log "Cloning $REPO_URL → $INSTALL_DIR"
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

print_next_steps() {
    cat <<EOF

────────────────────────────────────────────────────────────────────
✅ Server bootstrap complete.

Next steps (manual):

  1. cd $INSTALL_DIR
  2. cp deploy/.env.example deploy/.env
  3. Edit deploy/.env — replace every CHANGE-ME value.
       openssl rand -hex 48                      # JWT_SECRET_KEY
       openssl rand -base64 24                   # POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD
       docker run --rm httpd:alpine htpasswd -nbB admin 'YOUR_PASS' \\
         | sed -e 's/\\\$/\\\$\\\$/g'             # TRAEFIK_AUTH (doubles \$)
  4. Point DNS A records to this VPS for:
       myappsuite.com
       www.myappsuite.com
       api.myappsuite.com
       storage.myappsuite.com
       minio.myappsuite.com
       traefik.myappsuite.com
  5. Run the deploy:
       bash $INSTALL_DIR/deploy/deploy.sh

Traefik will request Let's Encrypt certs on first request to each host.
Watch progress with:  docker compose -f $INSTALL_DIR/deploy/docker-compose.prod.yml logs -f traefik
────────────────────────────────────────────────────────────────────
EOF
}

main() {
    require_root
    install_packages
    install_docker
    configure_firewall
    set_timezone
    ensure_deploy_key
    clone_or_update
    print_next_steps
}

main "$@"
