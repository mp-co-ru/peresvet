#!/usr/bin/env bash
set -euo pipefail

show_help() {
    cat <<'EOF'
Usage:
  packaging/build_dev_distribution.sh [--output PATH] [--root-dir NAME] [--local]

Build a development distribution archive that contains only the files needed to run
the platform with ./run_one_app.sh, including MCP servers for Grafana and Peresvet.

Options:
  --output PATH    Archive path. Defaults to dist/peresvet-dev-<version>.tar.gz
  --root-dir NAME  Top-level directory name inside the archive.
  --local          Include pre-installed dependencies (system packages and Python wheels)
                 in the distribution. Use this when internet access is limited.
  -h, --help       Show this help.

Python wheels для one_app хранятся в packages/; пути к wheels — в requirements.txt.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
version="$(git -C "${repo_root}" describe --tags --always --dirty 2>/dev/null || date +%Y%m%d%H%M%S)"
root_dir="peresvet-dev-${version}"
output="${repo_root}/dist/${root_dir}.tar.gz"
local_mode="false"

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
        --local)
            local_mode="true"
            shift
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

# Подготовка локального режима: устанавливаем зависимости на исходники
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

# Подготавливаем локальный режим, если указан флаг
# Сначала устанавливаем зависимости, затем копируем в stage_dir
if [[ "${local_mode}" == "true" ]]; then
    log "Подготовка локального режима (установка зависимостей на исходники)..."
    
    # Устанавливаем системные зависимости для one_app
    log "Установка системных зависимостей (libldap2-dev, libsasl2-dev, slapd, ldap-utils)..."
    if [[ $EUID -ne 0 ]]; then
        log "Предупреждение: Для установки системных зависимостей нужны права root."
        log "Пожалуйста, запустите с sudo или установите пакеты вручную:"
        log "  sudo apt-get update && sudo apt-get install -y --no-install-recommends libldap2-dev libsasl2-dev"
        log "  sudo DEBIAN_FRONTEND=noninteractive apt install -y slapd ldap-utils"
    else
        apt-get update -qq && apt-get install -y --no-install-recommends \
            libldap2-dev libsasl2-dev \
            && bash -c "DEBIAN_FRONTEND=noninteractive apt install -y slapd ldap-utils" || true
    fi
    
    # Устанавливаем Python-зависимости для one_app
    log "Установка Python-зависимостей для one_app..."
    # Используем --break-system-packages для обхода ограничений PEP 668
    python3 -m pip install --no-cache-dir --user --break-system-packages -r "${repo_root}/requirements.txt" || true
    
    log "Локальная подготовка завершена."
    
    # Копируем подготовленные зависимости в stage_dir
    log "Копирование подготовленных зависимостей в дистрибутив..."
    
    # Копируем системные пакеты (cached debs)
    if [[ -d /var/cache/apt/archives ]]; then
        mkdir -p "${stage_dir}/apt-cache"
        cp -p /var/cache/apt/archives/*.deb "${stage_dir}/apt-cache/" 2>/dev/null || true
        log "Копировано системных пакетов: $(find "${stage_dir}/apt-cache" -name '*.deb' 2>/dev/null | wc -l)"
    fi
    
    # Копируем Python-пакеты
    python3_user_site=$(python3 -c "import site; print(site.getuserbase())" 2>/dev/null || echo "~/.local")
    python3_site="${python3_user_site}/lib/python3.12/site-packages"
    if [[ ! -d "${python3_site}" ]]; then
        python3_site="${python3_user_site}/python3.12/site-packages"
    fi
    if [[ ! -d "${python3_site}" ]]; then
        python3_site="/usr/local/lib/python3.12/dist-packages"
    fi
    if [[ ! -d "${python3_site}" ]]; then
        python3_site=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "/usr/local/lib/python3.12/site-packages")
    fi
    log "Копирование Python-пакетов из ${python3_site}"
    if [[ -d "${python3_site}" ]]; then
        mkdir -p "${stage_dir}/python-site-packages"
        cp -Rp "${python3_site}/"* "${stage_dir}/python-site-packages/" 2>/dev/null || true
        log "Копирование Python-зависимостей завершено"
    else
        log "Предупреждение: Python-пакеты не найдены в ${python3_site}. Установите Python-зависимости перед сборкой."
    fi
    
    # Создаем файл .local-mode
    echo "LOCAL_MODE=true" > "${stage_dir}/.local-mode"
else
    # Создаем файл .local-mode
    echo "LOCAL_MODE=false" > "${stage_dir}/.local-mode"
fi

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
    "admin_scripts"
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
    "docker/compose/docker-compose.mcp.grafana.yml"
    "docker/compose/docker-compose.mcp.peresvet.yml"
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
    "docker/docker-files/mcp/Dockerfile.mcp.peresvet"
    "docker/docker-files/mcp/Dockerfile.mcp.grafana"
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

# Копируем .local-mode для Docker-сборки (используем существующий файл)
cp -p "${stage_dir}/.local-mode" "${stage_dir}/.local-mode.bak" 2>/dev/null || true

find "${stage_dir}" -type d -name __pycache__ -print0 | xargs -0 rm -rf

mkdir -p "${stage_dir}/packaging"
cp -p "${repo_root}/packaging/required-images.manifest" "${stage_dir}/packaging/required-images.manifest"

# В локальном режиме добавляем LOCAL_MODE=true к существующему .env
if [[ "${local_mode}" == "true" ]]; then
    if [[ -f "${repo_root}/.env" ]]; then
        cp -p "${repo_root}/.env" "${stage_dir}/.env"
        # Обновляем LOCAL_MODE на true
        sed -i 's/^LOCAL_MODE=.*/LOCAL_MODE=true/' "${stage_dir}/.env"
    else
        cat > "${stage_dir}/.env" <<'EOF'
# Local mode: предустановленные зависимости
LOCAL_MODE=true
EOF
    fi
else
    cp -p "${repo_root}/.env" "${stage_dir}/.env"
fi

mkdir -p "${stage_dir}/log"

python3 - "${stage_dir}" <<'PY'
import pathlib
import sys

stage_dir = pathlib.Path(sys.argv[1])

script = stage_dir / "run_one_app.sh"
text = script.read_text(encoding="utf-8")

# Add MCP compose files to the docker compose command in run_one_app.sh
# Look for the line with docker-compose.restart.yml and add MCP compose files before it
marker = "-f docker/compose/docker-compose.restart.yml \\\n"
replacement = "-f docker/compose/docker-compose.mcp.grafana.yml \\\n-f docker/compose/docker-compose.mcp.peresvet.yml \\\n" + marker

if marker in text:
    text = text.replace(marker, replacement, 1)
    script.write_text(text, encoding="utf-8")
    print("Successfully added MCP compose files to run_one_app.sh")
else:
    print("Warning: Could not find marker to add MCP compose files", file=sys.stderr)
PY

mkdir -p "$(dirname "${output}")"
tar -czf "${output}" -C "${tmp_dir}" "${root_dir}"

log "Готово: ${output}"
echo "${output}"
