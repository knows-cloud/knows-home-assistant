#!/command/with-contenv bashio
# ==============================================================================
# Seed Authelia configuration, secrets and users database on first start
# ==============================================================================
set -e

CONFIG=/config/configuration.yml
USERS=/config/users_database.yml
SECRETS=/config/secrets

mkdir -p /config/assets "${SECRETS}"

gen_secret() {
    if ! bashio::fs.file_exists "${SECRETS}/${1}"; then
        openssl rand -hex 32 > "${SECRETS}/${1}"
        chmod 600 "${SECRETS}/${1}"
        bashio::log.info "Generated secret: ${1}"
    fi
}

gen_secret jwt_secret
gen_secret session_secret
gen_secret storage_encryption_key

DOMAIN=$(jq -r '.domain // "example.com"' /data/options.json)

if ! bashio::fs.file_exists "${CONFIG}"; then
    bashio::log.info "Creating initial Authelia configuration for domain '${DOMAIN}'"
    cat > "${CONFIG}" <<EOF
theme: light

server:
  address: tcp://0.0.0.0:9091
  asset_path: /config/assets

log:
  level: info

totp:
  issuer: ${DOMAIN}

identity_validation:
  reset_password:
    jwt_lifespan: 5m

authentication_backend:
  file:
    path: /config/users_database.yml

access_control:
  default_policy: one_factor
  rules: []

session:
  expiration: 1h
  inactivity: 5m
  remember_me: 1M
  cookies:
    - domain: ${DOMAIN}
      authelia_url: https://auth.${DOMAIN}

regulation:
  max_retries: 3
  find_time: 2m
  ban_time: 5m

storage:
  local:
    path: /config/db.sqlite3

notifier:
  filesystem:
    filename: /config/notification.txt
EOF
fi

if ! bashio::fs.file_exists "${USERS}"; then
    PASSWORD=$(openssl rand -base64 15 | tr -d '=+/' | cut -c1-16)
    DIGEST=$(authelia crypto hash generate argon2 --password "${PASSWORD}" | sed 's/^Digest: //')
    cat > "${USERS}" <<EOF
users:
  admin:
    disabled: false
    displayname: Administrator
    password: "${DIGEST}"
    email: admin@${DOMAIN}
    groups:
      - admins
EOF
    chmod 600 "${USERS}"
    bashio::log.warning "=============================================================="
    bashio::log.warning "Created initial Authelia user 'admin'"
    bashio::log.warning "Password: ${PASSWORD}"
    bashio::log.warning "Change it via the admin UI. This is only shown once."
    bashio::log.warning "=============================================================="
fi
