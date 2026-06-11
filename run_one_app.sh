#!/usr/bin/env bash
# Скрипт запускает контейнеры с сервисами платформы.
# Имя сервера задаётся ключом --hostname, по умолчанию используется имя хоста.
# HTTPS-вариант запуска включается ключом --ssl true.

set -euo pipefail

show_help() {
    cat <<'EOF'
Usage:
  ./run_one_app.sh [--hostname HOSTNAME] [--ssl true|false]

Options:
  --hostname HOSTNAME  Server name for nginx. Defaults to current host name.
  --ssl true|false     Use HTTPS nginx compose file. Defaults to false.
  -h, --help           Show this help.

Environment:
  PRS_SKIP_IMAGE_PULL=1  Skip the pre-flight pull of required Docker images.
EOF
}

pull_image_with_retries() {
    local image="$1"
    local max_attempts=4
    local delay=4
    local attempt=1

    if docker image inspect "${image}" >/dev/null 2>&1; then
        return
    fi

    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Pull Docker image ${image} (${attempt}/${max_attempts})..."
        if docker pull "${image}"; then
            return
        fi

        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Retry ${image} in ${delay}s..."
            sleep "${delay}"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    cat >&2 <<EOF
Cannot pull required Docker image: ${image}

Check that this host can reach Docker registries, including:
  - https://auth.docker.io
  - https://registry-1.docker.io

If the error contains an IPv6 address and "i/o timeout", Docker may be trying an
unreachable IPv6 route. Fix IPv6 connectivity on the host or disable IPv6 for
Docker/the host network, then run ./run_one_app.sh again.
EOF
    exit 1
}

pull_required_images() {
    if [[ "${PRS_SKIP_IMAGE_PULL:-0}" == "1" ]]; then
        return
    fi

    local required_images=(
        "redis/redis-stack:7.2.0-v6"
        "rabbitmq:4.1.1-management"
        "postgres:16.1"
        "python:3.12-slim"
        "osixia/openldap"
        "grafana/grafana-enterprise:12.4.0-22081664032-ubuntu"
        "nginx:1.25.3-alpine-slim"
    )

    local image
    for image in "${required_images[@]}"; do
        pull_image_with_retries "${image}"
    done
}

srv="${HOSTNAME:-$(hostname)}"
ssl="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostname)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --hostname requires a value." >&2
                exit 1
            fi
            srv="$2"
            shift 2
            ;;
        --ssl)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --ssl requires true or false." >&2
                exit 1
            fi
            ssl="${2,,}"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 1
            ;;
    esac
done

case "${ssl}" in
    true)
        nginx_compose="docker/compose/docker-compose.nginx.one_app.ssl.yml"
        ;;
    false)
        nginx_compose="docker/compose/docker-compose.nginx.one_app.yml"
        ;;
    *)
        echo "Option --ssl accepts only true or false." >&2
        exit 1
        ;;
esac

sed -i "s/NGINX_HOST=.*/NGINX_HOST=${srv}/" docker/compose/.cont_one_app.env

extra_env=()
if [ -f docker/compose/.cont_one_app.secrets.env ]; then
    extra_env=(--env-file docker/compose/.cont_one_app.secrets.env)
fi

pull_required_images

docker compose --env-file docker/compose/.cont_one_app.env "${extra_env[@]}" \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_volume.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.grafana.yml \
-f "${nginx_compose}" \
-f docker/compose/docker-compose.ports.yml \
up
