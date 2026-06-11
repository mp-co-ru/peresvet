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
EOF
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
