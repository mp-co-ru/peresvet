#!/usr/bin/env bash
# Скрипт запускает контейнеры с сервисами платформы.
# Имя сервера задаётся ключом --hostname, по умолчанию используется имя хоста.
# HTTPS-вариант запуска включается ключом --ssl true.
# Пересборка контейнеров перед запуском включается ключом --build true.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REQUIRED_IMAGES_MANIFEST="${SCRIPT_DIR}/packaging/required-images.manifest"
DOTENV_FILE="${SCRIPT_DIR}/.env"

show_help() {
    cat <<'EOF'
Usage:
  ./run_one_app.sh [--hostname HOSTNAME] [--ssl true|false] [--build true|false] [--mirror HOST[:PORT]]

Options:
  --hostname HOSTNAME  Server name for nginx. Defaults to PRS_HOSTNAME or host name.
  --ssl true|false     Use HTTPS nginx compose file. Defaults to PRS_SSL from .env.
  --build true|false   Rebuild images before starting containers. Defaults to PRS_BUILD.
  --mirror HOST[:PORT] Registry mirror for missing base images. Defaults to
                       PRS_REGISTRY_MIRROR from .env.
  -h, --help           Show this help.

Configuration:
  Defaults are read from .env next to this script. CLI options override .env.
  Variables: PRS_REGISTRY_MIRROR, PRS_HOSTNAME, PRS_SSL, PRS_BUILD,
             PRS_SKIP_IMAGE_PULL.

Mirror notes:
  - Already present local images are not downloaded again.
  - If a mirror is configured, missing images are pulled only from the mirror.
  - Do not add the mirror to registry-mirrors in daemon.json.
  - For HTTP mirrors, add the host to insecure-registries in daemon.json.
EOF
}

load_dotenv() {
    local file="$1"
    local line key value

    [[ -f "${file}" ]] || return 0

    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -n "${line}" ]] || continue
        [[ "${line}" == *=* ]] || continue

        key="${line%%=*}"
        value="${line#*=}"
        key="${key%"${key##*[![:space:]]}"}"
        key="${key#"${key%%[![:space:]]*}"}"

        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
            value="${value:1:${#value}-2}"
        fi

        if [[ -z "${!key+x}" ]]; then
            export "${key}=${value}"
        fi
    done < "${file}"
}

normalize_registry_mirror() {
    local mirror="${1:-}"
    mirror="${mirror#http://}"
    mirror="${mirror#https://}"
    mirror="${mirror%/}"
    printf '%s' "${mirror}"
}

mirror_registry_image_path() {
    local image="$1"

    # Official Docker Hub images (no namespace) are stored as library/<name> in registry.
    if [[ "${image}" != */* ]]; then
        printf 'library/%s' "${image}"
    else
        printf '%s' "${image}"
    fi
}

mirror_image_ref() {
    local mirror="$1"
    local image="$2"
    printf '%s/%s' "${mirror}" "$(mirror_registry_image_path "${image}")"
}

mirror_registry_host() {
    local mirror="$1"
    mirror="${mirror%%/*}"
    printf '%s' "${mirror}"
}

docker_insecure_registry_includes() {
    local host="$1"
    local secure

    secure="$(docker info --format '{{if index .RegistryConfig.IndexConfigs "'"${host}"'"}}{{(index .RegistryConfig.IndexConfigs "'"${host}"'").Secure}}{{end}}' 2>/dev/null || true)"
    [[ "${secure}" == "false" ]]
}

report_insecure_registry_required() {
    local host="$1"

    cat >&2 <<EOF
HTTP registry mirror requires insecure-registries in /etc/docker/daemon.json.

Add:
  "insecure-registries": ["${host}"]

Example /etc/docker/daemon.json:
{
  "insecure-registries": ["${host}"]
}

Then run:
  sudo systemctl restart docker

Do not use registry-mirrors for product installation; keep PRS_REGISTRY_MIRROR in .env only.
EOF
    exit 1
}

ensure_registry_mirror_ready() {
    local mirror="$1"
    local host

    [[ -n "${mirror}" ]] || return 0

    host="$(mirror_registry_host "${mirror}")"
    if docker_insecure_registry_includes "${host}"; then
        return 0
    fi

    if curl -fsS --max-time 5 "http://${host}/v2/" >/dev/null 2>&1; then
        report_insecure_registry_required "${host}"
    fi
}

load_required_images() {
    local -n _images_ref="$1"
    _images_ref=()

    if [[ -f "${REQUIRED_IMAGES_MANIFEST}" ]]; then
        local line
        while IFS= read -r line || [[ -n "${line}" ]]; do
            line="${line%%#*}"
            line="${line#"${line%%[![:space:]]*}"}"
            line="${line%"${line##*[![:space:]]}"}"
            [[ -n "${line}" ]] || continue
            _images_ref+=("${line}")
        done < "${REQUIRED_IMAGES_MANIFEST}"
    fi

    if [[ "${#_images_ref[@]}" -eq 0 ]]; then
        _images_ref=(
            "redis/redis-stack:7.2.0-v6"
            "rabbitmq:4.1.1-management"
            "postgres:16.1"
            "python:3.12-slim"
            "osixia/openldap"
            "grafana/grafana-enterprise:12.4.0-22081664032-ubuntu"
            "nginx:1.25.3-alpine-slim"
        )
    fi
}

pull_ref_with_retries() {
    local ref="$1"
    local max_attempts=4
    local delay=4
    local attempt=1

    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Pull Docker image ${ref} (${attempt}/${max_attempts})..."
        if docker pull "${ref}"; then
            return 0
        fi

        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Retry ${ref} in ${delay}s..."
            sleep "${delay}"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return 1
}

report_pull_failure() {
    local image="$1"
    local mirror="${2:-}"

    if [[ -n "${mirror}" ]]; then
        cat >&2 <<EOF
Cannot pull required Docker image: ${image}

Configured registry mirror: ${mirror}
Expected reference: $(mirror_image_ref "${mirror}" "${image}")

Check that:
  - the mirror is reachable from this host
  - the image is published on the mirror under the same name and tag
  - for HTTP mirrors, ${mirror%%/*} is listed in insecure-registries

Do not use registry-mirrors in daemon.json for product installation; set
  PRS_REGISTRY_MIRROR in .env or use --mirror HOST:PORT instead.
EOF
    else
        cat >&2 <<EOF
Cannot pull required Docker image: ${image}

Check that this host can reach Docker registries, including:
  - https://auth.docker.io
  - https://registry-1.docker.io

If Docker Hub is unavailable, set PRS_REGISTRY_MIRROR in .env or use --mirror.

If the error contains an IPv6 address and "i/o timeout", Docker may be trying an
unreachable IPv6 route. Fix IPv6 connectivity on the host or disable IPv6 for
Docker/the host network, then run ./run_one_app.sh again.
EOF
    fi
}

pull_image_with_retries() {
    local image="$1"
    local mirror="${2:-}"

    if docker image inspect "${image}" >/dev/null 2>&1; then
        echo "Docker image ${image} is already present locally."
        return 0
    fi

    if [[ -n "${mirror}" ]]; then
        local mirror_ref
        mirror_ref="$(mirror_image_ref "${mirror}" "${image}")"
        if pull_ref_with_retries "${mirror_ref}"; then
            if [[ "${mirror_ref}" != "${image}" ]]; then
                docker tag "${mirror_ref}" "${image}"
            fi
            return 0
        fi
        report_pull_failure "${image}" "${mirror}"
        exit 1
    fi

    if pull_ref_with_retries "${image}"; then
        return 0
    fi

    report_pull_failure "${image}"
    exit 1
}

pull_required_images() {
    if [[ "${PRS_SKIP_IMAGE_PULL:-0}" == "1" ]]; then
        return
    fi

    local required_images=()
    load_required_images required_images

    if [[ -n "${registry_mirror}" ]]; then
        echo "Using registry mirror: ${registry_mirror}"
        ensure_registry_mirror_ready "${registry_mirror}"
    fi

    local image
    for image in "${required_images[@]}"; do
        pull_image_with_retries "${image}" "${registry_mirror}"
    done
}

load_dotenv "${DOTENV_FILE}"

srv="${PRS_HOSTNAME:-${HOSTNAME:-$(hostname)}}"
ssl="${PRS_SSL:-false}"
build="${PRS_BUILD:-false}"
registry_mirror="$(normalize_registry_mirror "${PRS_REGISTRY_MIRROR:-}")"

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
        --build)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --build requires true or false." >&2
                exit 1
            fi
            build="${2,,}"
            shift 2
            ;;
        --mirror)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --mirror requires a host[:port] value." >&2
                exit 1
            fi
            registry_mirror="$(normalize_registry_mirror "$2")"
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

case "${build}" in
    true)
        up_args=(up -d --build)
        ;;
    false)
        up_args=(up -d)
        ;;
    *)
        echo "Option --build accepts only true or false." >&2
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
-f docker/compose/docker-compose.restart.yml \
"${up_args[@]}"
