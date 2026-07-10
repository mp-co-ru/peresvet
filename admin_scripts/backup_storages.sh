#!/usr/bin/env sh
# Последовательный бэкап хранилищ LDAP, PostgreSQL (historian) и Grafana.
#
# Запуск только из корня проекта. Вызывает:
#   admin_scripts/ldap/ldap_volume_backup.sh
#   admin_scripts/historian/historian_volume_backup.sh
#   admin_scripts/grafana/grafana_volume_backup.sh
#
# Общие параметры (--compose_project_name, --skip_stop и т.д.) передаются во все
# три скрипта. Параметры, специфичные для сервиса, задавайте в отдельных скриптах.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

compose_project_name=
backup_helper_image=
skip_stop=
skip_compose_stop=

usage() {
	cat <<EOF >&2
Использование (только из корня проекта): $0 [--параметр=значение ...]

Создаёт бэкапы хранилищ LDAP, historian (PostgreSQL) и Grafana подряд.

Общие параметры (передаются во все три скрипта):
  --compose_project_name=NAME
  --backup_helper_image=IMG
  --skip_stop=0|1
  --skip_compose_stop=0|1

Архивы по умолчанию:
  backups/ldap/
  backups/historian/
  backups/grafana/
EOF
}

set_param() {
	key=$1
	val=$2
	case "$key" in
		compose_project_name) compose_project_name=$val ;;
		backup_helper_image) backup_helper_image=$val ;;
		skip_stop) skip_stop=$val ;;
		skip_compose_stop) skip_compose_stop=$val ;;
		help | h) usage; exit 0 ;;
		*)
			echo "Неизвестный параметр: --$key" >&2
			usage
			exit 1
			;;
	esac
}

while [ $# -gt 0 ]; do
	case "$1" in
		--*=*)
			key=${1%%=*}
			key=${key#--}
			val=${1#*=}
			set_param "$key" "$val"
			shift
			;;
		-h | --help)
			usage
			exit 0
			;;
		*)
			echo "Ожидается --параметр=значение, получено: $1" >&2
			usage
			exit 1
			;;
	esac
done

HERE=$(pwd -P)
THERE=$(cd "$REPO_ROOT" && pwd -P)
if [ "$HERE" != "$THERE" ]; then
	echo "Ошибка: скрипт нужно запускать из корня проекта." >&2
	echo "  Текущий каталог: $HERE" >&2
	echo "  Ожидаемый корень:  $THERE" >&2
	echo "Пример: cd \"$THERE\" && ./admin_scripts/$(basename "$0")" >&2
	exit 1
fi

forward_args=
if [ -n "$compose_project_name" ]; then
	forward_args="$forward_args --compose_project_name=$compose_project_name"
fi
if [ -n "$backup_helper_image" ]; then
	forward_args="$forward_args --backup_helper_image=$backup_helper_image"
fi
if [ -n "$skip_stop" ]; then
	forward_args="$forward_args --skip_stop=$skip_stop"
fi
if [ -n "$skip_compose_stop" ]; then
	forward_args="$forward_args --skip_compose_stop=$skip_compose_stop"
fi

run_backup() {
	name=$1
	script=$2
	echo "=== Бэкап: $name ==="
	# shellcheck disable=SC2086
	sh "$script" $forward_args
}

run_backup "LDAP" "$REPO_ROOT/admin_scripts/ldap/ldap_volume_backup.sh"
run_backup "historian (PostgreSQL)" "$REPO_ROOT/admin_scripts/historian/historian_volume_backup.sh"
run_backup "Grafana" "$REPO_ROOT/admin_scripts/grafana/grafana_volume_backup.sh"

echo "=== Все бэкапы завершены ==="
