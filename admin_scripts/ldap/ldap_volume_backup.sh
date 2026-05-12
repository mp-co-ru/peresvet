#!/usr/bin/env sh
# Бэкап данных OpenLDAP: том или каталог на хосте определяются по compose_file
# (см. resolve_ldap_storage.py), если не заданы явные ldap_docker_volume / ldap_data_dir.
#
# Запуск только из корня репозитория (см. документацию administration.rst).
# Параметры: только --имя=значение (имена в нижнем регистре); полный перечень — в Sphinx.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

compose_file=docker/compose/docker-compose.ldap.one_app.yml
compose_project_name=
ldap_service=ldap
backup_dir=backups/ldap
ldap_docker_volume=
ldap_data_dir=
backup_helper_image=busybox:stable
skip_stop=0
skip_compose_stop=0

usage() {
	cat <<EOF >&2
Использование (только из корня репозитория): $0 [--параметр=значение ...]

Полное описание параметров — в docs/source/administration.rst (раздел LDAP).
Кратко:
  --compose_file=PATH
  --compose_project_name=NAME
  --ldap_service=NAME
  --backup_dir=PATH
  --ldap_docker_volume=NAME
  --ldap_data_dir=PATH
  --backup_helper_image=IMG
  --skip_stop=0|1
  --skip_compose_stop=0|1
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
		compose_file) compose_file=$val ;;
		compose_project_name) compose_project_name=$val ;;
		ldap_service) ldap_service=$val ;;
		backup_dir) backup_dir=$val ;;
		ldap_docker_volume) ldap_docker_volume=$val ;;
		ldap_data_dir) ldap_data_dir=$val ;;
		backup_helper_image) backup_helper_image=$val ;;
		skip_stop) skip_stop=$(to_bool "$val") ;;
		skip_compose_stop) skip_compose_stop=$(to_bool "$val") ;;
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
	echo "Ошибка: скрипт нужно запускать из корня репозитория." >&2
	echo "  Текущий каталог: $HERE" >&2
	echo "  Ожидаемый корень:  $THERE" >&2
	echo "Пример: cd \"$THERE\" && ./admin_scripts/ldap/$(basename \"$0\") …" >&2
	exit 1
fi

if [ "${compose_file#/}" = "$compose_file" ]; then
	compose_file_abs=$REPO_ROOT/$compose_file
else
	compose_file_abs=$compose_file
fi

if [ "${backup_dir#/}" = "$backup_dir" ]; then
	backup_dir_abs=$REPO_ROOT/$backup_dir
else
	backup_dir_abs=$backup_dir
fi

cd "$REPO_ROOT"

resolve_storage() {
	if [ -n "$ldap_docker_volume" ]; then
		printf 'volume\t%s\n' "$ldap_docker_volume"
		return
	fi
	if [ -n "$ldap_data_dir" ]; then
		printf 'bind\t%s\n' "$ldap_data_dir"
		return
	fi
	RESOLVE_CWD=$REPO_ROOT python3 "$SCRIPT_DIR/resolve_ldap_storage.py" \
		"$compose_file_abs" "$compose_project_name" "$ldap_service"
}

line=$(resolve_storage) || exit 1
mode=$(printf '%s\n' "$line" | cut -f1)
target=$(printf '%s\n' "$line" | cut -f2)

compose_stop() {
	if [ "$skip_compose_stop" = "1" ]; then
		return 0
	fi
	if [ -n "$compose_project_name" ]; then
		echo "docker compose -p $compose_project_name -f $compose_file stop $ldap_service"
		docker compose -p "$compose_project_name" -f "$compose_file_abs" stop "$ldap_service"
	else
		echo "docker compose -f $compose_file stop $ldap_service"
		docker compose -f "$compose_file_abs" stop "$ldap_service"
	fi
}

compose_start() {
	if [ "$skip_compose_stop" = "1" ]; then
		return 0
	fi
	if [ -n "$compose_project_name" ]; then
		docker compose -p "$compose_project_name" -f "$compose_file_abs" start "$ldap_service" || true
	else
		docker compose -f "$compose_file_abs" start "$ldap_service" || true
	fi
}

stop_using_containers() {
	vol=$1
	ids=$(docker ps -q --filter "volume=$vol" 2>/dev/null || true)
	if [ -z "$ids" ]; then
		return 0
	fi
	if [ "$skip_stop" = "1" ]; then
		echo "Предупреждение: том $vol смонтирован в работающие контейнеры; бэкап без остановки." >&2
		return 0
	fi
	echo "Останавливаю контейнеры, использующие том $vol ..."
	docker stop $ids
}

backup_dir_tar() {
	src=$1
	out=$2
	out_dir=$(dirname "$out")
	out_base=$(basename "$out")
	mkdir -p "$out_dir"
	out_abs=$(cd "$out_dir" && pwd)/$out_base
	( cd "$src" && tar czf "$out_abs" . )
}

backup_volume() {
	vol=$1
	out=$2
	mkdir -p "$backup_dir_abs"
	archive_basename=$(basename "$out")
	docker run --rm \
		-v "$vol:/data:ro" \
		-v "$backup_dir_abs:/backup" \
		"$backup_helper_image" \
		sh -c "cd /data && tar czf /backup/$archive_basename ."
}

ts=$(date +%Y-%m-%d_%H-%M-%S)
mkdir -p "$backup_dir_abs"

compose_stop
stopped_containers=""
if [ "$skip_compose_stop" = "1" ]; then
	if [ "$mode" = "volume" ]; then
		stopped_containers=$(docker ps -q --filter "volume=$target" 2>/dev/null || true)
		stop_using_containers "$target"
	fi
fi

if [ "$mode" = "bind" ]; then
	if [ ! -d "$target" ]; then
		echo "Каталог данных LDAP не найден: $target" >&2
		compose_start
		exit 1
	fi
	archive=$backup_dir_abs/ldap_data_${ts}.tar.gz
	echo "Бэкап каталога $target -> $archive"
	backup_dir_tar "$target" "$archive"
else
	archive=$backup_dir_abs/${target}_${ts}.tar.gz
	echo "Бэкап docker volume $target -> $archive"
	backup_volume "$target" "$archive"
fi

if [ "$skip_compose_stop" = "1" ] && [ -n "$stopped_containers" ] && [ "$skip_stop" != "1" ]; then
	echo "Запуск остановленных контейнеров: $stopped_containers"
	docker start $stopped_containers
fi
compose_start

echo "Готово: $archive"
