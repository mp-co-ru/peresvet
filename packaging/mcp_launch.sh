# Подключается скриптами запуска платформы.
# Ключи --mcp-peresvet и --mcp-grafana: true поднимает сервер и публикует
# его через nginx, false (значение по умолчанию) — не поднимает.

mcp_peresvet=false
mcp_grafana=false
mcp_compose_args=()

mcp_normalize_bool() {
    local value="${1:-}"
    value="${value,,}"
    if [[ -z "${value}" ]]; then
        echo "false"
        return 0
    fi
    case "${value}" in
        true|false)
            echo "${value}"
            ;;
        *)
            return 1
            ;;
    esac
}

mcp_dotenv_value() {
    local key="$1"
    local file="${SCRIPT_DIR}/.env"
    local line name value

    if [[ -n "${!key+x}" ]]; then
        printf '%s' "${!key}"
        return 0
    fi
    [[ -f "${file}" ]] || return 0

    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -n "${line}" && "${line}" == *=* ]] || continue
        name="${line%%=*}"
        value="${line#*=}"
        name="${name%"${name##*[![:space:]]}"}"
        name="${name#"${name%%[![:space:]]*}"}"
        if [[ "${name}" == "${key}" ]]; then
            printf '%s' "${value}"
            return 0
        fi
    done < "${file}"
}

mcp_init() {
    local peresvet grafana raw_peresvet raw_grafana
    raw_peresvet="$(mcp_dotenv_value PRS_MCP_PERESVET)"
    raw_grafana="$(mcp_dotenv_value PRS_MCP_GRAFANA)"
    peresvet="$(mcp_normalize_bool "${raw_peresvet:-false}")" || {
        echo "PRS_MCP_PERESVET принимает только true или false." >&2
        exit 1
    }
    grafana="$(mcp_normalize_bool "${raw_grafana:-false}")" || {
        echo "PRS_MCP_GRAFANA принимает только true или false." >&2
        exit 1
    }
    mcp_peresvet="${peresvet}"
    mcp_grafana="${grafana}"
}

mcp_set_flag() {
    local flag="$1"
    local raw="$2"
    local value
    value="$(mcp_normalize_bool "${raw}")" || {
        echo "Ключ ${flag} принимает только true или false." >&2
        exit 1
    }
    case "${flag}" in
        --mcp-peresvet)
            mcp_peresvet="${value}"
            ;;
        --mcp-grafana)
            mcp_grafana="${value}"
            ;;
        *)
            echo "Неизвестный ключ MCP: ${flag}" >&2
            exit 1
            ;;
    esac
}

mcp_parse_leading_flags() {
    mcp_rest_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mcp-peresvet|--mcp-grafana)
                if [[ $# -lt 2 || -z "${2:-}" ]]; then
                    echo "Ключ $1 принимает только true или false." >&2
                    exit 1
                fi
                mcp_set_flag "$1" "$2"
                shift 2
                ;;
            *)
                mcp_rest_args+=("$1")
                shift
                ;;
        esac
    done
}

mcp_dry_run_report() {
    mcp_fill_compose_args
    echo "mcp-peresvet=${mcp_peresvet}"
    echo "mcp-grafana=${mcp_grafana}"
    echo "mcp-compose:${mcp_compose_args[*]:-}"
    if [[ -n "${PRS_NGINX_OPTIONAL_DIR:-}" ]]; then
        mcp_prepare
    fi
}

mcp_fill_compose_args() {
    mcp_compose_args=()
    if [[ "${mcp_peresvet}" == true ]]; then
        mcp_compose_args+=(-f docker/compose/docker-compose.mcp.peresvet.yml)
    fi
    if [[ "${mcp_grafana}" == true ]]; then
        mcp_compose_args+=(-f docker/compose/docker-compose.mcp.grafana.yml)
    fi
}

mcp_sync_snippet() {
    local name="$1"
    local enabled="$2"
    local src="${SCRIPT_DIR}/config/nginx/mcp/${name}.conf"
    local dst="${PRS_NGINX_OPTIONAL_DIR:-${SCRIPT_DIR}/config/nginx/optional}/${name}.conf"

    mkdir -p "$(dirname "${dst}")"
    if [[ "${enabled}" == true ]]; then
        cp -f "${src}" "${dst}"
    else
        rm -f "${dst}"
    fi
}

mcp_prepare() {
    mcp_sync_snippet mcp-peresvet "${mcp_peresvet}"
    mcp_sync_snippet mcp-grafana "${mcp_grafana}"
}

mcp_stop_disabled() {
    if [[ "${mcp_peresvet}" != true ]]; then
        docker rm -f prs-mcp-peresvet >/dev/null 2>&1 || true
    fi
    if [[ "${mcp_grafana}" != true ]]; then
        docker rm -f prs-mcp-grafana >/dev/null 2>&1 || true
    fi
}

mcp_reload_nginx() {
    docker exec prs-nginx-one-app nginx -t
    docker exec prs-nginx-one-app nginx -s reload
}

mcp_grafana_image() {
    echo "grafana/mcp-grafana:1.3.0"
}
