#!/usr/bin/env sh
# Восстановить контейнеры и хранилища из архива running_containers_backup.sh.
#
# Если Docker volume или bind mount-путь уже существуют, скрипт спрашивает,
# перезаписать хранилище или пропустить его восстановление.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

archive=
helper_image=alpine:3.20
assume_yes=0
skip_stop=0
skip_containers=0

usage() {
	cat <<EOF >&2
Использование (только из корня проекта): $0 --archive=ARCHIVE.tar.gz [--параметр=значение ...]

Параметры:
  --archive=PATH          обязательный путь к архиву running_containers_backup.sh
  --helper_image=IMAGE    образ для очистки/распаковки хранилищ (по умолчанию: alpine:3.20)
  --assume_yes=0|1        перезаписывать существующие хранилища и контейнеры без вопросов
  --skip_stop=0|1         не останавливать контейнеры, использующие перезаписываемое хранилище
  --skip_containers=0|1   восстановить только образы и хранилища, контейнеры не запускать
  -h, --help              показать справку
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
		archive) archive=$val ;;
		helper_image) helper_image=$val ;;
		assume_yes) assume_yes=$(to_bool "$val") ;;
		skip_stop) skip_stop=$(to_bool "$val") ;;
		skip_containers) skip_containers=$(to_bool "$val") ;;
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
	echo "Пример: cd \"$THERE\" && ./admin_scripts/docker/$(basename "$0") --archive=..." >&2
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

command -v docker >/dev/null 2>&1 || {
	echo "Не найден docker в PATH." >&2
	exit 1
}

work_dir=$(mktemp -d "$REPO_ROOT/.docker_runtime_restore_tmp.XXXXXX")
stopped_ids=

cleanup() {
	rc=$?
	if [ -n "$stopped_ids" ]; then
		echo "Запускаю обратно остановленные контейнеры..."
		docker start $stopped_ids >/dev/null 2>&1 || true
	fi
	rm -rf "$work_dir"
	exit "$rc"
}
trap cleanup EXIT INT TERM

ask_yes_no() {
	prompt=$1
	if [ "$assume_yes" = "1" ]; then
		return 0
	fi
	printf '%s [y/N] ' "$prompt"
	read -r ans
	case "$ans" in
		y | yes | Y | YES) return 0 ;;
		*) return 1 ;;
	esac
}

stop_using_storage() {
	storage=$1
	ids=$(docker ps -q --filter "volume=$storage" 2>/dev/null || true)
	if [ -z "$ids" ]; then
		return 0
	fi
	if [ "$skip_stop" = "1" ]; then
		echo "Ошибка: хранилище $storage используется работающими контейнерами, а задан --skip_stop=1." >&2
		return 1
	fi
	echo "Останавливаю контейнеры, использующие $storage ..."
	docker stop $ids >/dev/null
	stopped_ids="$stopped_ids $ids"
}

restore_volume_storage() {
	volume_name=$1
	archive_rel=$2
	archive_file=$work_dir/$archive_rel
	if [ ! -f "$archive_file" ]; then
		echo "Архив Docker volume не найден: $archive_file" >&2
		return 1
	fi

	exists=0
	if docker volume inspect "$volume_name" >/dev/null 2>&1; then
		exists=1
	fi
	if [ "$exists" = "1" ]; then
		if ! ask_yes_no "Docker volume $volume_name уже существует. Перезаписать его содержимое?"; then
			echo "Пропускаю Docker volume $volume_name."
			return 0
		fi
		stop_using_storage "$volume_name"
	else
		echo "Создаю Docker volume $volume_name ..."
		docker volume create "$volume_name" >/dev/null
	fi

	archive_dir=$(dirname "$archive_file")
	archive_base=$(basename "$archive_file")
	echo "Восстанавливаю Docker volume $volume_name ..."
	docker run --rm \
		-v "$volume_name:/data" \
		-v "$archive_dir:/backup:ro" \
		-e "ARCHIVE_BASE=$archive_base" \
		"$helper_image" \
		sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf "/backup/$ARCHIVE_BASE" -C /data'
}

restore_bind_storage() {
	bind_source=$1
	archive_rel=$2
	source_kind=$3
	archive_file=$work_dir/$archive_rel
	if [ ! -f "$archive_file" ]; then
		echo "Архив bind mount не найден: $archive_file" >&2
		return 1
	fi

	exists=0
	if [ -e "$bind_source" ] || [ -L "$bind_source" ]; then
		exists=1
	fi
	if [ "$exists" = "1" ]; then
		if ! ask_yes_no "Bind mount $bind_source уже существует. Перезаписать его содержимое?"; then
			echo "Пропускаю bind mount $bind_source."
			return 0
		fi
		stop_using_storage "$bind_source"
	fi

	archive_dir=$(dirname "$archive_file")
	archive_base=$(basename "$archive_file")

	case "$source_kind" in
		directory)
			if [ "$exists" = "1" ] && { [ ! -d "$bind_source" ] || [ -L "$bind_source" ]; }; then
				rm -rf "$bind_source"
			fi
			mkdir -p "$bind_source"
			echo "Восстанавливаю каталог bind mount $bind_source ..."
			docker run --rm \
				--mount "type=bind,source=$bind_source,target=/data" \
				-v "$archive_dir:/backup:ro" \
				-e "ARCHIVE_BASE=$archive_base" \
				"$helper_image" \
				sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf "/backup/$ARCHIVE_BASE" -C /data'
			;;
		file)
			parent_dir=$(dirname "$bind_source")
			file_base=$(basename "$bind_source")
			mkdir -p "$parent_dir"
			echo "Восстанавливаю файл bind mount $bind_source ..."
			docker run --rm \
				--mount "type=bind,source=$parent_dir,target=/target" \
				-v "$archive_dir:/backup:ro" \
				-e "ARCHIVE_BASE=$archive_base" \
				-e "FILE_BASE=$file_base" \
				"$helper_image" \
				sh -c 'rm -rf "/target/$FILE_BASE" && tar xzf "/backup/$ARCHIVE_BASE" -C /target'
			;;
		*)
			echo "Неизвестный тип bind mount в manifest: $source_kind" >&2
			return 1
			;;
	esac
}

restore_docker_container() {
	name=$1
	shift
	image=$1
	shift
	RESTORED_CONTAINER_NAME=

	if [ "$skip_containers" = "1" ]; then
		echo "Пропускаю контейнер $name (--skip_containers=1)."
		return 0
	fi

	if docker container inspect "$name" >/dev/null 2>&1; then
		if ! ask_yes_no "Контейнер $name уже существует. Удалить и создать заново?"; then
			echo "Пропускаю контейнер $name."
			return 0
		fi
		echo "Удаляю существующий контейнер $name ..."
		docker rm -f "$name" >/dev/null
	fi

	echo "Восстанавливаю контейнер $name ..."
	docker run -d --name "$name" "$@" "$image" >/dev/null
	RESTORED_CONTAINER_NAME=$name
}

connect_restored_container() {
	network_name=$1
	if [ "$skip_containers" = "1" ] || [ -z "${RESTORED_CONTAINER_NAME:-}" ]; then
		return 0
	fi
	if ! docker network inspect "$network_name" >/dev/null 2>&1; then
		echo "Предупреждение: сеть $network_name не существует, подключение контейнера пропущено." >&2
		return 0
	fi
	docker network connect "$network_name" "$RESTORED_CONTAINER_NAME" >/dev/null 2>&1 || true
}

echo "Распаковываю архив: $archive_abs"
tar xzf "$archive_abs" -C "$work_dir"

if [ ! -f "$work_dir/manifest.txt" ] || [ ! -f "$work_dir/images/container_images.tar" ]; then
	echo "Некорректный архив: нет manifest.txt или images/container_images.tar" >&2
	exit 1
fi

echo "Загружаю Docker images из архива..."
docker load -i "$work_dir/images/container_images.tar"

if [ -f "$work_dir/metadata/networks.list" ]; then
	while IFS= read -r network_name; do
		[ -n "$network_name" ] || continue
		if docker network inspect "$network_name" >/dev/null 2>&1; then
			echo "Сеть $network_name уже существует."
		else
			echo "Создаю сеть $network_name ..."
			docker network create "$network_name" >/dev/null
		fi
	done < "$work_dir/metadata/networks.list"
fi

if [ -f "$work_dir/storages.tsv" ]; then
	while IFS="$(printf '\t')" read -r storage_type storage_key archive_rel source_kind; do
		[ -n "$storage_type" ] || continue
		case "$storage_type" in
			volume)
				restore_volume_storage "$storage_key" "$archive_rel"
				;;
			bind)
				restore_bind_storage "$storage_key" "$archive_rel" "$source_kind"
				;;
			*)
				echo "Неизвестный тип хранилища в manifest: $storage_type" >&2
				exit 1
				;;
		esac
	done < "$work_dir/storages.tsv"
fi

if [ -f "$work_dir/generated/restore_containers.sh" ]; then
	echo "Восстанавливаю контейнеры..."
	# shellcheck disable=SC1091
	. "$work_dir/generated/restore_containers.sh"
else
	echo "Предупреждение: в архиве нет generated/restore_containers.sh, контейнеры не восстановлены." >&2
fi

echo "Готово."
