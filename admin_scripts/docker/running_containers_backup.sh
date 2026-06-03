#!/usr/bin/env sh
# Создать единый архив всех работающих Docker-контейнеров и их хранилищ.
#
# Архив включает:
# - committed-образы всех контейнеров из docker ps;
# - Docker volumes, смонтированные в эти контейнеры;
# - bind mounts с хоста (если не задан --no_bind_mounts=1);
# - metadata docker inspect и сгенерированный sh-фрагмент для восстановления.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

backup_dir=backups/docker_runtime
archive_name=
helper_image=busybox:stable
skip_stop=0
no_bind_mounts=0
keep_committed_images=0

usage() {
	cat <<EOF >&2
Использование (только из корня репозитория): $0 [--параметр=значение ...]

Создаёт .tar.gz с работающими контейнерами Docker и их хранилищами.

Параметры:
  --backup_dir=PATH             каталог для итогового архива (по умолчанию: backups/docker_runtime)
  --archive_name=NAME.tar.gz    имя итогового архива (по умолчанию: docker_runtime_<дата>.tar.gz)
  --helper_image=IMAGE          образ для архивации Docker volumes (по умолчанию: busybox:stable)
  --skip_stop=0|1               не останавливать контейнеры перед копированием хранилищ
  --no_bind_mounts=0|1          не включать bind mount-пути с хоста
  --keep_committed_images=0|1   оставить временные committed-образы после архивации
  -h, --help                    показать справку
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
		backup_dir) backup_dir=$val ;;
		archive_name) archive_name=$val ;;
		helper_image) helper_image=$val ;;
		skip_stop) skip_stop=$(to_bool "$val") ;;
		no_bind_mounts) no_bind_mounts=$(to_bool "$val") ;;
		keep_committed_images) keep_committed_images=$(to_bool "$val") ;;
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
	echo "Пример: cd \"$THERE\" && ./admin_scripts/docker/$(basename "$0")" >&2
	exit 1
fi

if [ "${backup_dir#/}" = "$backup_dir" ]; then
	backup_dir_abs=$REPO_ROOT/$backup_dir
else
	backup_dir_abs=$backup_dir
fi

timestamp=$(date -u +%Y-%m-%d_%H-%M-%S_UTC)
if [ -z "$archive_name" ]; then
	archive_name=docker_runtime_${timestamp}.tar.gz
fi
case "$archive_name" in
	*.tar.gz) ;;
	*) archive_name=$archive_name.tar.gz ;;
esac

archive_path=$backup_dir_abs/$archive_name
if [ -e "$archive_path" ]; then
	echo "Архив уже существует: $archive_path" >&2
	exit 1
fi

command -v docker >/dev/null 2>&1 || {
	echo "Не найден docker в PATH." >&2
	exit 1
}

safe_part() {
	printf '%s' "$1" |
		tr '[:upper:]' '[:lower:]' |
		sed 's#[^a-z0-9_.-]#-#g; s#^[^a-z0-9]*##; s#[^a-z0-9]*$##; s#^$#container#'
}

hash_id() {
	if command -v sha256sum >/dev/null 2>&1; then
		printf '%s' "$1" | sha256sum | awk '{print $1}'
	elif command -v shasum >/dev/null 2>&1; then
		printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
	else
		printf '%s' "$1" | cksum | awk '{print $1 "_" $2}'
	fi
}

quote_sh() {
	printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

append_unique_line() {
	line=$1
	file=$2
	if [ ! -f "$file" ] || ! grep -Fqx -- "$line" "$file"; then
		printf '%s\n' "$line" >> "$file"
	fi
}

append_run_arg() {
	out_file=$1
	arg=$2
	printf ' %s' "$(quote_sh "$arg")" >> "$out_file"
}

archive_bind_source() {
	source_path=$1
	out_archive=$2
	out_dir=$(dirname "$out_archive")
	mkdir -p "$out_dir"
	if [ -d "$source_path" ] && [ ! -L "$source_path" ]; then
		( cd "$source_path" && tar czf "$out_archive" . )
		printf '%s' directory
	elif [ -f "$source_path" ] || [ -L "$source_path" ]; then
		parent_dir=$(dirname "$source_path")
		base_name=$(basename "$source_path")
		( cd "$parent_dir" && tar czf "$out_archive" "$base_name" )
		printf '%s' file
	else
		return 1
	fi
}

mkdir -p "$backup_dir_abs"
staging_dir=$(mktemp -d "$backup_dir_abs/.docker_runtime_tmp.XXXXXX")
metadata_dir=$staging_dir/metadata
images_dir=$staging_dir/images
volumes_dir=$staging_dir/storages/volumes
binds_dir=$staging_dir/storages/binds
generated_dir=$staging_dir/generated
mkdir -p "$metadata_dir" "$images_dir" "$volumes_dir" "$binds_dir" "$generated_dir"

containers_file=$staging_dir/containers.tsv
storages_file=$staging_dir/storages.tsv
volumes_list=$metadata_dir/volume_names.list
binds_list=$metadata_dir/bind_sources.list
networks_list=$metadata_dir/networks.list
generated_restore=$generated_dir/restore_containers.sh
: > "$containers_file"
: > "$storages_file"
: > "$volumes_list"
: > "$binds_list"
: > "$networks_list"

committed_images=
stopped_ids=

cleanup() {
	rc=$?
	if [ -n "$stopped_ids" ]; then
		echo "Запускаю обратно остановленные контейнеры..."
		docker start $stopped_ids >/dev/null 2>&1 || true
	fi
	if [ -n "$committed_images" ] && [ "$keep_committed_images" != "1" ]; then
		echo "Удаляю временные committed-образы..."
		docker image rm $committed_images >/dev/null 2>&1 || true
	fi
	rm -rf "$staging_dir"
	exit "$rc"
}
trap cleanup EXIT INT TERM

running_ids=$(docker ps -q)
if [ -z "$running_ids" ]; then
	echo "Нет работающих контейнеров для архивации." >&2
	exit 1
fi

docker_server_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)
containers_count=$(printf '%s\n' "$running_ids" | sed '/^$/d' | wc -l | tr -d ' ')

cat > "$staging_dir/manifest.txt" <<EOF
manifest_version=1
created_at_utc=$timestamp
docker_server_version=$docker_server_version
containers_count=$containers_count
skip_stop=$skip_stop
include_bind_mounts=$([ "$no_bind_mounts" = "1" ] && echo 0 || echo 1)
helper_image=$helper_image
EOF

cat > "$generated_restore" <<'EOF'
# Generated by running_containers_backup.sh.
# This file is sourced by running_containers_restore.sh.
EOF

echo "Внимание: архив будет содержать Docker metadata, переменные окружения и данные bind mounts."
echo "Найдено работающих контейнеров: $containers_count"
echo "Сохраняю metadata docker inspect..."
docker inspect $running_ids > "$metadata_dir/containers_inspect.json"

echo "Создаю committed-образы контейнеров..."
for id in $running_ids; do
	name=$(docker inspect -f '{{.Name}}' "$id" | sed 's#^/##')
	short_id=$(printf '%s' "$id" | cut -c 1-12)
	safe_name=$(safe_part "$name")
	tag=peresvet-runtime-backup/${safe_name}:${short_id}

	echo "  docker commit $name -> $tag"
	docker commit "$id" "$tag" >/dev/null
	committed_images="$committed_images $tag"
	printf '%s\t%s\t%s\n' "$id" "$name" "$tag" >> "$containers_file"

	printf '\n# %s (%s)\n' "$name" "$short_id" >> "$generated_restore"
	printf 'restore_docker_container %s %s' "$(quote_sh "$name")" "$(quote_sh "$tag")" >> "$generated_restore"

	hostname=$(docker inspect -f '{{.Config.Hostname}}' "$id")
	if [ -n "$hostname" ]; then
		append_run_arg "$generated_restore" --hostname
		append_run_arg "$generated_restore" "$hostname"
	fi

	restart_name=$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$id")
	restart_count=$(docker inspect -f '{{.HostConfig.RestartPolicy.MaximumRetryCount}}' "$id")
	if [ -n "$restart_name" ] && [ "$restart_name" != "no" ]; then
		if [ "$restart_name" = "on-failure" ] && [ "$restart_count" != "0" ]; then
			append_run_arg "$generated_restore" --restart
			append_run_arg "$generated_restore" "$restart_name:$restart_count"
		else
			append_run_arg "$generated_restore" --restart
			append_run_arg "$generated_restore" "$restart_name"
		fi
	fi

	network_mode=$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$id")
	if [ -n "$network_mode" ] && [ "$network_mode" != "default" ]; then
		append_run_arg "$generated_restore" --network
		append_run_arg "$generated_restore" "$network_mode"
	fi

	docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$id" |
	while IFS= read -r network_name; do
		[ -n "$network_name" ] || continue
		case "$network_name" in
			bridge | host | none) ;;
			*) append_unique_line "$network_name" "$networks_list" ;;
		esac
	done

	docker inspect -f '{{range $port, $bindings := .NetworkSettings.Ports}}{{if $bindings}}{{range $bindings}}{{printf "%s\t%s\t%s\n" .HostPort $port .HostIp}}{{end}}{{end}}{{end}}' "$id" |
	while IFS="$(printf '\t')" read -r host_port container_port host_ip; do
		[ -n "$host_port" ] || continue
		case "$host_ip" in
			"" | "0.0.0.0")
				port_arg=$host_port:$container_port
				;;
			*)
				port_arg=$host_ip:$host_port:$container_port
				;;
		esac
		append_run_arg "$generated_restore" -p
		append_run_arg "$generated_restore" "$port_arg"
	done

	docker inspect -f '{{range .Mounts}}{{if eq .Type "volume"}}{{printf "volume\t%s\t%s\t%v\n" .Name .Destination .RW}}{{else if eq .Type "bind"}}{{printf "bind\t%s\t%s\t%v\n" .Source .Destination .RW}}{{else if eq .Type "tmpfs"}}{{printf "tmpfs\t-\t%s\ttrue\n" .Destination}}{{end}}{{end}}' "$id" |
	while IFS="$(printf '\t')" read -r mount_type mount_key mount_destination mount_rw; do
		[ -n "$mount_type" ] || continue
		case "$mount_type" in
			volume)
				[ -n "$mount_key" ] || continue
				append_unique_line "$mount_key" "$volumes_list"
				mount_arg=type=volume,source=$mount_key,target=$mount_destination
				if [ "$mount_rw" != "true" ]; then
					mount_arg=$mount_arg,readonly
				fi
				append_run_arg "$generated_restore" --mount
				append_run_arg "$generated_restore" "$mount_arg"
				;;
			bind)
				[ "$no_bind_mounts" = "1" ] && continue
				[ -n "$mount_key" ] || continue
				append_unique_line "$mount_key" "$binds_list"
				mount_arg=type=bind,source=$mount_key,target=$mount_destination
				if [ "$mount_rw" != "true" ]; then
					mount_arg=$mount_arg,readonly
				fi
				append_run_arg "$generated_restore" --mount
				append_run_arg "$generated_restore" "$mount_arg"
				;;
			tmpfs)
				append_run_arg "$generated_restore" --tmpfs
				append_run_arg "$generated_restore" "$mount_destination"
				;;
		esac
	done
	printf '\n' >> "$generated_restore"

	docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$id" |
	while IFS= read -r network_name; do
		[ -n "$network_name" ] || continue
		[ "$network_name" = "$network_mode" ] && continue
		case "$network_name" in
			bridge | host | none) ;;
			*)
				printf 'connect_restored_container %s\n' "$(quote_sh "$network_name")" >> "$generated_restore"
				;;
		esac
	done
done

echo "Сохраняю committed-образы в archive image tar..."
docker save -o "$images_dir/container_images.tar" $committed_images
docker image inspect $committed_images > "$metadata_dir/committed_images_inspect.json"

if [ -s "$volumes_list" ]; then
	docker volume inspect $(sort -u "$volumes_list") > "$metadata_dir/volumes_inspect.json"
else
	printf '[]\n' > "$metadata_dir/volumes_inspect.json"
fi

if [ -s "$networks_list" ]; then
	docker network inspect $(sort -u "$networks_list") > "$metadata_dir/networks_inspect.json"
else
	printf '[]\n' > "$metadata_dir/networks_inspect.json"
fi

if [ "$skip_stop" = "1" ]; then
	echo "Контейнеры не останавливаются (--skip_stop=1)."
else
	echo "Останавливаю контейнеры перед копированием хранилищ..."
	stopped_ids=$running_ids
	docker stop $running_ids >/dev/null
fi

if [ -s "$volumes_list" ]; then
	sort -u "$volumes_list" |
	while IFS= read -r volume_name; do
		[ -n "$volume_name" ] || continue
		archive_file=$(hash_id "$volume_name").tar.gz
		echo "Архивирую Docker volume $volume_name..."
		docker run --rm \
			-v "$volume_name:/data:ro" \
			-v "$volumes_dir:/backup" \
			"$helper_image" \
			sh -c "cd /data && tar czf /backup/$archive_file ."
		printf 'volume\t%s\t%s\t-\n' "$volume_name" "storages/volumes/$archive_file" >> "$storages_file"
	done
fi

if [ "$no_bind_mounts" = "1" ]; then
	echo "Bind mounts не включаются в архив (--no_bind_mounts=1)."
else
	sort -u "$binds_list" |
	while IFS= read -r bind_source; do
		[ -n "$bind_source" ] || continue
		if [ ! -e "$bind_source" ] && [ ! -L "$bind_source" ]; then
			echo "Предупреждение: bind mount source не найден, пропускаю: $bind_source" >&2
			continue
		fi
		archive_file=$(hash_id "$bind_source").tar.gz
		echo "Архивирую bind mount $bind_source..."
		source_kind=$(archive_bind_source "$bind_source" "$binds_dir/$archive_file")
		printf 'bind\t%s\t%s\t%s\n' "$bind_source" "storages/binds/$archive_file" "$source_kind" >> "$storages_file"
	done
fi

if [ -n "$stopped_ids" ]; then
	echo "Запускаю обратно остановленные контейнеры..."
	docker start $stopped_ids >/dev/null
	stopped_ids=
fi

echo "Упаковываю итоговый архив: $archive_path"
( cd "$staging_dir" && tar czf "$archive_path" . )
echo "Готово: $archive_path"
