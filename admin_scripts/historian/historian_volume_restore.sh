#!/usr/bin/env sh
# Восстановление PostgreSQL (историческая БД) из tar.gz (созданного historian_volume_backup.sh).
# Том или каталог определяются по compose_file (resolve_historian_storage.py),
# если не заданы historian_docker_volume / historian_data_dir.
#
# Запуск только из корня репозитория. Обязательно: --archive=ПУТЬ.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

compose_file=docker/compose/docker-compose.postgresql.data_in_volume.yml
compose_project_name=
postgres_service=psql
archive=
historian_docker_volume=
historian_data_dir=
restore_helper_image=alpine:3.20
assume_yes=0
skip_stop=0
skip_compose_stop=0

usage() {
	cat <<EOF >&2
Использование (только из корня репозитория): $0 --archive=ARCHIVE.tar.gz [--параметр=значение ...]

Обязательно: --archive=PATH

Аналог admin_scripts/ldap/ldap_volume_restore.sh для данных PostgreSQL (/var/lib/postgresql/data).

Параметры:
  --compose_file=PATH
  --compose_project_name=NAME
  --postgres_service=NAME
  --historian_docker_volume=NAME
  --historian_data_dir=PATH
  --restore_helper_image=IMG   (по умолчанию: alpine:3.20)
  --assume_yes=0|1
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
		postgres_service) postgres_service=$val ;;
		archive) archive=$val ;;
		historian_docker_volume) historian_docker_volume=$val ;;
		historian_data_dir) historian_data_dir=$val ;;
		restore_helper_image) restore_helper_image=$val ;;
		assume_yes) assume_yes=$(to_bool "$val") ;;
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
	echo "Пример: cd \"$THERE\" && ./admin_scripts/historian/$(basename \"$0\") …" >&2
	exit 1
fi

if [ -z "$archive" ]; then
	echo "Нужно указать --archive=..." >&2
	usage
	exit 1
fi

if [ "${archive#/}" = "$archive" ]; then
	archive_abs=$REPO_ROOT/$archive
else
	archive_abs=$archive
fi

if [ ! -f "$archive_abs" ]; then
	echo "Архив не найден: $archive_abs" >&2
	exit 1
fi

if [ "${compose_file#/}" = "$compose_file" ]; then
	compose_file_abs=$REPO_ROOT/$compose_file
else
	compose_file_abs=$compose_file
fi

cd "$REPO_ROOT"

resolve_storage() {
	if [ -n "$historian_docker_volume" ]; then
		printf 'volume\t%s\n' "$historian_docker_volume"
		return
	fi
	if [ -n "$historian_data_dir" ]; then
		printf 'bind\t%s\n' "$historian_data_dir"
		return
	fi
	RESOLVE_CWD=$REPO_ROOT python3 "$SCRIPT_DIR/resolve_historian_storage.py" \
		"$compose_file_abs" "$compose_project_name" "$postgres_service"
}

line=$(resolve_storage) || exit 1
mode=$(printf '%s\n' "$line" | cut -f1)
target=$(printf '%s\n' "$line" | cut -f2)

ARCHIVE_DIR=$(cd "$(dirname "$archive_abs")" && pwd)
ARCHIVE_BASE=$(basename "$archive_abs")

compose_stop() {
	if [ "$skip_compose_stop" = "1" ]; then
		return 0
	fi
	if [ -n "$compose_project_name" ]; then
		echo "docker compose -p $compose_project_name -f $compose_file stop $postgres_service"
		docker compose -p "$compose_project_name" -f "$compose_file_abs" stop "$postgres_service"
	else
		echo "docker compose -f $compose_file stop $postgres_service"
		docker compose -f "$compose_file_abs" stop "$postgres_service"
	fi
}

compose_start() {
	if [ "$skip_compose_stop" = "1" ]; then
		return 0
	fi
	if [ -n "$compose_project_name" ]; then
		docker compose -p "$compose_project_name" -f "$compose_file_abs" start "$postgres_service" || true
	else
		docker compose -f "$compose_file_abs" start "$postgres_service" || true
	fi
}

stop_using_containers() {
	vol=$1
	ids=$(docker ps -q --filter "volume=$vol" 2>/dev/null || true)
	if [ -z "$ids" ]; then
		return 0
	fi
	if [ "$skip_stop" = "1" ]; then
		echo "Ошибка: том $vol занят работающими контейнерами. Остановите PostgreSQL или уберите --skip_stop=1." >&2
		exit 1
	fi
	echo "Останавливаю контейнеры, использующие том $vol ..."
	docker stop $ids
}

restore_dir() {
	tgt=$1
	if [ "$assume_yes" != "1" ]; then
		printf 'Восстановление перезапишет содержимое %s. Продолжить? [y/N] ' "$tgt"
		read -r ans
		case "$ans" in
			y | yes | Y | YES) ;;
			*) echo "Отмена."; exit 1 ;;
		esac
	fi
	if [ ! -d "$tgt" ]; then
		echo "Каталог не существует: $tgt" >&2
		exit 1
	fi
	echo "Очистка $tgt и распаковка $archive_abs ..."
	docker run --rm \
		-v "$tgt:/data" \
		-v "$ARCHIVE_DIR:/backup:ro" \
		"$restore_helper_image" \
		sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf "/backup/'"$ARCHIVE_BASE"'" -C /data'
	echo "Готово: данные в $tgt"
}

restore_volume() {
	vol=$1
	if [ "$assume_yes" != "1" ]; then
		printf 'Восстановление перезапишет содержимое docker volume %s. Продолжить? [y/N] ' "$vol"
		read -r ans
		case "$ans" in
			y | yes | Y | YES) ;;
			*) echo "Отмена."; exit 1 ;;
		esac
	fi
	echo "Очистка тома $vol и распаковка $archive_abs ..."
	docker run --rm \
		-v "$vol:/data" \
		-v "$ARCHIVE_DIR:/backup:ro" \
		"$restore_helper_image" \
		sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf "/backup/'"$ARCHIVE_BASE"'" -C /data'
	echo "Готово: том $vol"
}

compose_stop
stopped_containers=""
if [ "$skip_compose_stop" = "1" ] && [ "$mode" = "volume" ]; then
	stopped_containers=$(docker ps -q --filter "volume=$target" 2>/dev/null || true)
	stop_using_containers "$target"
fi

if [ "$mode" = "bind" ]; then
	restore_dir "$target"
else
	restore_volume "$target"
fi

if [ "$skip_compose_stop" = "1" ] && [ -n "$stopped_containers" ] && [ "$skip_stop" != "1" ]; then
	echo "Запуск контейнеров: $stopped_containers"
	docker start $stopped_containers
fi
compose_start
