#!/usr/bin/env bash
set -euo pipefail

show_help() {
    cat <<'EOF'
Usage:
  packaging/build_product_distribution.sh [--output PATH] [--root-dir NAME]

Build a product distribution archive that contains only the files needed to run
the platform with ./run_one_app.sh.

Options:
  --output PATH    Archive path. Defaults to dist/peresvet-product-<version>.tar.gz
  --root-dir NAME  Top-level directory name inside the archive.
  -h, --help       Show this help.

Python wheels для one_app хранятся в packages/; пути к wheels — в requirements.txt.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
version="$(git -C "${repo_root}" describe --tags --always --dirty 2>/dev/null || date +%Y%m%d%H%M%S)"
root_dir="peresvet-product-${version}"
output="${repo_root}/dist/${root_dir}.tar.gz"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            output="$2"
            shift 2
            ;;
        --root-dir)
            root_dir="$2"
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

case "${output}" in
    /*) ;;
    *) output="${repo_root}/${output}" ;;
esac

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

verify_packages() {
    local packages_dir="${repo_root}/packages"
    local wheel_count req_lines
    wheel_count="$(find "${packages_dir}" -maxdepth 1 -name '*.whl' 2>/dev/null | wc -l | tr -d ' ')"
    req_lines="$(wc -l < "${repo_root}/requirements.txt" | tr -d ' ')"
    if [[ "${wheel_count}" -lt 10 ]]; then
        die "packages/ неполный (${wheel_count} wheels)"
    fi
    if [[ "${req_lines}" -ne "${wheel_count}" ]]; then
        die "requirements.txt (${req_lines} строк) не совпадает с packages/ (${wheel_count} wheels)"
    fi
    if ! python3 -m pip wheel \
        --no-index --find-links="${packages_dir}" \
        -r "${repo_root}/requirements.txt" \
        -w "${packages_dir}" >/dev/null 2>&1; then
        die "packages/ неполный (pip wheel --no-index не проходит)"
    fi
    log "packages/: ${wheel_count} wheels"
}

verify_packages

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT
stage_dir="${tmp_dir}/${root_dir}"
mkdir -p "${stage_dir}"

copy_tracked_pathspec() {
    local pathspec="$1"
    local copied=0

    while IFS= read -r -d '' file; do
        mkdir -p "${stage_dir}/$(dirname "${file}")"
        cp -p "${repo_root}/${file}" "${stage_dir}/${file}"
        copied=1
    done < <(git -C "${repo_root}" ls-files -z -- "${pathspec}")

    if [[ "${copied}" -eq 0 ]]; then
        echo "No tracked files matched required pathspec: ${pathspec}" >&2
        exit 1
    fi
}

required_pathspecs=(
    "README.md"
    "LICENSE"
    "requirements.txt"
    "run_one_app.sh"
    "run_one_app_ssl_letsencrypt.sh"
    "run_one_app_ssl_letsencrypt_generate_certificates.sh"
    "renew_certificates.sh"
    "certificates/*.sh"
    "config/grafana/logos"
    "config/grafana/plugins/gapit-htmlgraphics-panel"
    "config/grafana/plugins/marcusolsson-dynamictext-panel"
    "config/grafana/plugins/marcusolsson-json-datasource"
    "config/grafana/plugins/volkovlabs-echarts-panel"
    "config/grafana/plugins/volkovlabs-form-panel"
    "config/grafana/provisioning"
    "config/nginx/nginx.conf"
    "config/nginx/no_ssl"
    "config/nginx/peresvet"
    "config/nginx/ssl/default.conf.ssl"
    "config/nginx/ssl/default.conf.ssl_letsencrypt.template"
    "config/nginx/ssl/default.conf.ssl_letsencrypt_generate_certificates.template"
    "docker/compose/.cont_one_app.env"
    "docker/compose/docker-compose.grafana.yml"
    "docker/compose/docker-compose.ldap.one_app.yml"
    "docker/compose/docker-compose.nginx.one_app.ssl.yml"
    "docker/compose/docker-compose.nginx.one_app.yml"
    "docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml"
    "docker/compose/docker-compose.nginx.ssl_letsencrypt_generate_certificates.yml"
    "docker/compose/docker-compose.certbot.ssl_letsencrypt_generate_certificates.yml"
    "docker/compose/docker-compose.one_app.yml"
    "docker/compose/docker-compose.ports.yml"
    "docker/compose/docker-compose.postgresql.data_in_volume.yml"
    "docker/compose/docker-compose.rabbitmq.yml"
    "docker/compose/docker-compose.redis.yml"
    "docker/compose/docker-compose.restart.yml"
    "docker/docker-files/all/Dockerfile.one_app.uvicorn"
    "docker/docker-files/grafana/Dockerfile.grafana"
    "docker/docker-files/ldap/Dockerfile.ldap.one_app"
    "docker/docker-files/ldap/src"
    "docker/docker-files/nginx/Dockerfile.nginx"
    "docker/docker-files/nginx/Dockerfile.nginx.ssl"
    "docker/docker-files/nginx/Dockerfile.nginx.ssl_letsencrypt"
    "docker/docker-files/nginx/Dockerfile.nginx.ssl_letsencrypt_generate_certificates"
    "docker/docker-files/rabbitmq/definitions.json"
    "docker/docker-files/rabbitmq/enabled_plugins"
    "docker/docker-files/rabbitmq/rabbitmq.conf"
    "docs/pdf"
    "methods"
    "src"
)

for pathspec in "${required_pathspecs[@]}"; do
    copy_tracked_pathspec "${pathspec}"
done

mkdir -p "${stage_dir}/packages"
cp -p "${repo_root}"/packages/*.whl "${stage_dir}/packages/"

find "${stage_dir}" -type d -name __pycache__ -print0 | xargs -0 rm -rf

mkdir -p "${stage_dir}/packaging"
cp -p "${repo_root}/packaging/required-images.manifest" "${stage_dir}/packaging/required-images.manifest"
cp -p "${repo_root}/.env" "${stage_dir}/.env"

mkdir -p "${stage_dir}/log"

python3 - "${stage_dir}" <<'PY'
import pathlib
import sys

stage_dir = pathlib.Path(sys.argv[1])

script = stage_dir / "run_one_app.sh"
text = script.read_text(encoding="utf-8")
restart_line = "-f docker/compose/docker-compose.restart.yml \\\n"
if restart_line in text:
    raise SystemExit(0)

marker = "-f docker/compose/docker-compose.ports.yml \\\n"
replacement = marker + restart_line
if marker not in text:
    raise SystemExit("Cannot add restart compose file to run_one_app.sh: marker not found")

script.write_text(text.replace(marker, replacement, 1), encoding="utf-8")
PY

mkdir -p "$(dirname "${output}")"
tar -czf "${output}" -C "${tmp_dir}" "${root_dir}"

log "Готово: ${output}"
echo "${output}"
