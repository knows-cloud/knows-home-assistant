ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG AUTHELIA_VERSION=4.39.4

# Runtime dependencies: Authelia binary + Python for the admin UI
RUN apk add --no-cache \
        python3 \
        py3-flask \
        py3-yaml \
        curl \
        openssl \
        nginx \
    && case "${BUILD_ARCH}" in \
         amd64)   AUTHELIA_ARCH="amd64" ;; \
         aarch64) AUTHELIA_ARCH="arm64" ;; \
         armv7)   AUTHELIA_ARCH="arm" ;; \
         *) echo "Unsupported architecture: ${BUILD_ARCH}" && exit 1 ;; \
       esac \
    && curl -fsSL -o /tmp/authelia.tar.gz \
        "https://github.com/authelia/authelia/releases/download/v${AUTHELIA_VERSION}/authelia-v${AUTHELIA_VERSION}-linux-${AUTHELIA_ARCH}-musl.tar.gz" \
    && mkdir -p /tmp/authelia \
    && tar -xzf /tmp/authelia.tar.gz -C /tmp/authelia \
    && mv "/tmp/authelia/authelia-linux-${AUTHELIA_ARCH}-musl" /usr/local/bin/authelia \
    && chmod +x /usr/local/bin/authelia \
    && rm -rf /tmp/authelia /tmp/authelia.tar.gz

COPY rootfs /

RUN chmod +x /etc/s6-overlay/s6-rc.d/init-authelia/up.sh \
             /etc/s6-overlay/s6-rc.d/authelia/run \
             /etc/s6-overlay/s6-rc.d/admin-ui/run \
             /etc/s6-overlay/s6-rc.d/nginx/run

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
    CMD curl -fs http://127.0.0.1:9091/api/health || exit 1
