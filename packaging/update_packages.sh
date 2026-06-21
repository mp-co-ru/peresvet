#!/usr/bin/env bash
set -euo pipefail

show_help() {
    cat <<'EOF'
Usage:
  packaging/update_packages.sh

Собирает wheels всех зависимостей one_app в packages/.
python_ldap и fast_ldap_pool — готовые wheels, остальные — с PyPI (или зеркала).

Environment:
  PIP_INDEX_URL   Зеркало PyPI (если pypi.org недоступен).
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"

while [[ $# -gt 0 ]]; do
    case "$1" in
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

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

command -v python3 >/dev/null 2>&1 || die "python3 не найден в PATH"

packages_dir="${repo_root}/packages"
pip_cache="${repo_root}/packaging/pip-cache"
requirements_file="${repo_root}/requirements.txt"

mkdir -p "${packages_dir}" "${pip_cache}"

log "Проверка локальных wheels в packages/"
if python3 -m pip wheel \
    --no-index \
    --find-links="${packages_dir}" \
    -r "${requirements_file}" \
    -w "${packages_dir}" 2>/dev/null; then
    log "Все wheels (включая зависимости python_ldap) уже в packages/"
else
    mirrors=()
    if [[ -n "${PIP_INDEX_URL:-}" ]]; then
        mirrors+=("${PIP_INDEX_URL}")
    fi
    mirrors+=(
        "https://pypi.tuna.tsinghua.edu.cn/simple"
        "https://mirrors.aliyun.com/pypi/simple/"
        "https://pypi.org/simple"
    )

    fetched=0
    for index_url in "${mirrors[@]}"; do
        host="${index_url#https://}"
        host="${host#http://}"
        host="${host%%/*}"
        log "pip wheel: ${index_url}"
        if python3 -m pip wheel \
            --cache-dir "${pip_cache}" \
            --default-timeout=300 \
            --retries=10 \
            --prefer-binary \
            --find-links="${packages_dir}" \
            --index-url "${index_url}" \
            --trusted-host "${host}" \
            -r "${requirements_file}" \
            -w "${packages_dir}"; then
            fetched=1
            break
        fi
    done

    if [[ "${fetched}" -eq 0 ]] && command -v docker >/dev/null 2>&1; then
        log "pip wheel на хосте не удался — пробуем контейнер python:3.12-slim"
        for index_url in "${mirrors[@]}"; do
            log "docker pip wheel: ${index_url}"
            if docker run --rm \
                -e "PIP_INDEX_URL=${index_url}" \
                -v "${pip_cache}:/pip-cache" \
                -v "${packages_dir}:/out_packages" \
                -v "${requirements_file}:/requirements.txt:ro" \
                python:3.12-slim \
                bash -ce '
                  DEBIAN_FRONTEND=noninteractive apt-get update -qq
                  apt-get install -y -qq --no-install-recommends gcc build-essential python3-dev
                  host="${PIP_INDEX_URL#https://}"; host="${host#http://}"; host="${host%%/*}"
                  pip wheel --cache-dir /pip-cache --default-timeout=300 --retries=10 --prefer-binary \
                    --find-links=/out_packages --index-url "${PIP_INDEX_URL}" --trusted-host "${host}" \
                    -r /requirements.txt -w /out_packages
                '; then
                fetched=1
                break
            fi
        done
    fi

    [[ "${fetched}" -eq 1 ]] \
        || die "Не удалось загрузить wheels (задайте PIP_INDEX_URL или повторите при доступном PyPI)"
fi

wheel_count="$(find "${packages_dir}" -maxdepth 1 -name '*.whl' | wc -l | tr -d ' ')"
[[ "${wheel_count}" -ge 2 ]] || die "packages/ пуст после обновления"

if ! python3 -m pip wheel \
    --no-index \
    --find-links="${packages_dir}" \
    -r "${requirements_file}" \
    -w "${packages_dir}" >/dev/null 2>&1; then
    die "pip wheel --no-index не проходит — в packages/ не хватает wheels. Повторите с доступным PyPI."
fi

log "packages/: ${wheel_count} wheels"
