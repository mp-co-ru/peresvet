#!/usr/bin/env sh
# Последовательное восстановление хранилищ LDAP, PostgreSQL (historian) и Grafana.
#
# Запуск только из корня проекта. Вызывает:
#   admin_scripts/ldap/ldap_volume_restore.sh
#   admin_scripts/historian/historian_volume_restore.sh
#   admin_scripts/grafana/grafana_volume_restore.sh
#
# Обязательны пути к архивам (--ldap_archive, --historian_archive, --grafana_archive),
# если соответствующий сервис не пропущен через --skip_*=1.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

ldap_archive=
historian_archive=
grafana_archive=
compose_project_name=
restore_helper_image=
assume_yes=0
skip_stop=
skip_compose_stop=
skip_ldap=0
skip_historian=0
skip_grafana=0

usage() {
	cat <<EOF >&2
Использование (только из корня проекта): $0 \\
  --ldap_archive=PATH --historian_archive=PATH --grafana_archive=PATH \\
  [--параметр=значение ...]

Обязательные архивы (если сервис не пропущен):
  --ldap_archive=PATH
  --historian_archive=PATH
  --grafana_archive=PATH

Общие параметры (передаются во все вызываемые скрипты):
  --compose_project_name=NAME
  --restore_helper_image=IMG
  --assume_yes=0|1
  --skip_stop=0|1
  --skip_compose_stop=0|1

Пропуск сервиса:
  --skip_ldap=0|1
  --skip_historian=0|1
  --skip_grafana=0|1
EOF
}

to_bool() {
	case "$1" in
		1 | true | yes | YES) echo 1 ;;
		*) echo 0 ;;
	esac
}

set_param() {
	key=$1
	val=$2
	case "$key" in
		ldap_archive) ldap_archive=$val ;;
		historian_archive) historian_archive=$val ;;
		grafana_archive) grafana_archive=$val ;;
		compose_project_name) compose_project_name=$val ;;
		restore_helper_image) restore_helper_image=$val ;;
		assume_yes) assume_yes=$(to_bool "$val") ;;
		skip_stop) skip_stop=$val ;;
		skip_compose_stop) skip_compose_stop=$val ;;
		skip_ldap) skip_ldap=$(to_bool "$val") ;;
		skip_historian) skip_historian=$(to_bool "$val") ;;
		skip_grafana) skip_grafana=$(to_bool "$val") ;;
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
	echo "Пример: cd \"$THERE\" && ./admin_scripts/$(basename "$0") …" >&2
	exit 1
fi

if [ "$skip_ldap" != "1" ] && [ -z "$ldap_archive" ]; then
	echo "Нужно указать --ldap_archive=... (или --skip_ldap=1)." >&2
	usage
	exit 1
fi
if [ "$skip_historian" != "1" ] && [ -z "$historian_archive" ]; then
	echo "Нужно указать --historian_archive=... (или --skip_historian=1)." >&2
	usage
	exit 1
fi
if [ "$skip_grafana" != "1" ] && [ -z "$grafana_archive" ]; then
	echo "Нужно указать --grafana_archive=... (или --skip_grafana=1)." >&2
	usage
	exit 1
fi

forward_args="--assume_yes=$assume_yes"
if [ -n "$compose_project_name" ]; then
	forward_args="$forward_args --compose_project_name=$compose_project_name"
fi
if [ -n "$restore_helper_image" ]; then
	forward_args="$forward_args --restore_helper_image=$restore_helper_image"
fi
if [ -n "$skip_stop" ]; then
	forward_args="$forward_args --skip_stop=$skip_stop"
fi
if [ -n "$skip_compose_stop" ]; then
	forward_args="$forward_args --skip_compose_stop=$skip_compose_stop"
fi

run_restore() {
	name=$1
	script=$2
	archive=$3
	echo "=== Восстановление: $name ==="
	# shellcheck disable=SC2086
	sh "$script" $forward_args --archive="$archive"
}

if [ "$skip_ldap" != "1" ]; then
	run_restore "LDAP" "$REPO_ROOT/admin_scripts/ldap/ldap_volume_restore.sh" "$ldap_archive"
fi
if [ "$skip_historian" != "1" ]; then
	run_restore "historian (PostgreSQL)" "$REPO_ROOT/admin_scripts/historian/historian_volume_restore.sh" "$historian_archive"
fi
if [ "$skip_grafana" != "1" ]; then
	run_restore "Grafana" "$REPO_ROOT/admin_scripts/grafana/grafana_volume_restore.sh" "$grafana_archive"
fi

echo "=== Восстановление завершено ==="
