#!/usr/bin/env bash
# Скрипт запускает контейнеры с сервисами платформы.
# Имя сервера задаётся ключом --hostname, по умолчанию используется имя хоста.
# HTTPS-вариант запуска включается ключом --ssl true.
# Пересборка контейнеров перед запуском включается ключом --build true.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REQUIRED_IMAGES_MANIFEST="${SCRIPT_DIR}/packaging/required-images.manifest"
DOTENV_FILE="${SCRIPT_DIR}/.env"

show_help() {
    cat <<'EOF'
Usage:
  ./run_one_app.sh [--hostname HOSTNAME] [--ssl true|false] [--build true|false] [--mirror HOST[:PORT]]

Options:
  --hostname HOSTNAME  Server name for nginx. Defaults to PRS_HOSTNAME or host name.
  --ssl true|false     Use HTTPS nginx compose file. Defaults to PRS_SSL from .env.
  --build true|false   Rebuild images before starting containers. Defaults to PRS_BUILD.
  --mirror HOST[:PORT] Registry mirror for missing base images. Defaults to
                       PRS_REGISTRY_MIRROR from .env.
  -h, --help           Show this help.

Configuration:
  Defaults are read from .env next to this script. CLI options override .env.
  Variables: PRS_REGISTRY_MIRROR, PRS_HOSTNAME, PRS_SSL, PRS_BUILD,
             PRS_SKIP_IMAGE_PULL.

Mirror notes:
  - Already present local images are not downloaded again.
  - If a mirror is configured, missing images are pulled from the mirror first,
    then from Docker Hub if the mirror is unavailable.
  - During mirror attempts press Ctrl+I to switch to Docker Hub immediately
    for all remaining images in this run.
  - The mirror is accessed over HTTP(S) directly; daemon.json changes are not required.
  - Do not add the mirror to registry-mirrors in daemon.json.
EOF
}

PULL_SKIP_TO_HUB=0
PULL_MIRROR_FIRST_ANNOUNCED=0

load_dotenv() {
    local file="$1"
    local line key value

    [[ -f "${file}" ]] || return 0

    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -n "${line}" ]] || continue
        [[ "${line}" == *=* ]] || continue

        key="${line%%=*}"
        value="${line#*=}"
        key="${key%"${key##*[![:space:]]}"}"
        key="${key#"${key%%[![:space:]]*}"}"

        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
            value="${value:1:${#value}-2}"
        fi

        if [[ -z "${!key+x}" ]]; then
            export "${key}=${value}"
        fi
    done < "${file}"
}

normalize_registry_mirror() {
    local mirror="${1:-}"
    mirror="${mirror#http://}"
    mirror="${mirror#https://}"
    mirror="${mirror%/}"
    printf '%s' "${mirror}"
}

mirror_registry_image_path() {
    local image="$1"

    # Official Docker Hub images (no namespace) are stored as library/<name> in registry.
    if [[ "${image}" != */* ]]; then
        printf 'library/%s' "${image}"
    else
        printf '%s' "${image}"
    fi
}

mirror_image_ref() {
    local mirror="$1"
    local image="$2"
    printf '%s/%s' "${mirror}" "$(mirror_registry_image_path "${image}")"
}

image_with_explicit_tag() {
    local image="$1"

    if [[ "${image}" == *:* ]]; then
        printf '%s' "${image}"
    else
        printf '%s:latest' "${image}"
    fi
}

report_mirror_pull_requires_python3() {
    cat >&2 <<'EOF'
Cannot pull images from the configured registry mirror.

python3 is required to download images from the mirror without editing
/etc/docker/daemon.json.
EOF
    exit 1
}

pull_mirror_via_registry_api() {
    local mirror_ref="$1"
    local local_image="$2"
    local cache_dir

    if ! command -v python3 >/dev/null 2>&1; then
        report_mirror_pull_requires_python3
    fi

    cache_dir="${TMPDIR:-/tmp}/prs-registry-pull/$(printf '%s' "${mirror_ref}:${local_image}" | sha256sum | awk '{print $1}')"
    mkdir -p "${cache_dir}"

    PRS_PULL_CACHE_DIR="${cache_dir}" python3 - "${mirror_ref}" "${local_image}" <<'PY'
import gzip
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

MANIFEST_V2 = "application/vnd.docker.distribution.manifest.v2+json"
MANIFEST_LIST_V2 = "application/vnd.docker.distribution.manifest.list.v2+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
ACCEPT = ", ".join((MANIFEST_V2, MANIFEST_LIST_V2, OCI_MANIFEST, OCI_INDEX))
EMPTY_LAYER_DIGESTS = frozenset({
    "4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1",
    "5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef",
})
EMPTY_LAYER_TAR = b"\0" * 1024


def eprint(message):
    print(message, file=sys.stderr)


def detect_architecture():
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    return mapping.get(machine, machine)


def registry_base_url(host):
    for scheme in ("http", "https"):
        probe = f"{scheme}://{host}/v2/"
        try:
            req = urllib.request.Request(probe, method="HEAD")
            with urllib.request.urlopen(req, timeout=5):
                return f"{scheme}://{host}"
        except Exception:
            try:
                with urllib.request.urlopen(probe, timeout=5):
                    return f"{scheme}://{host}"
            except Exception:
                continue
    return f"http://{host}"


def parse_mirror_ref(mirror_ref):
    slash_idx = mirror_ref.find("/")
    if slash_idx <= 0:
        raise SystemExit(f"Invalid mirror image reference: {mirror_ref}")

    host = mirror_ref[:slash_idx]
    repo_with_tag = mirror_ref[slash_idx + 1 :]
    if not repo_with_tag:
        raise SystemExit(f"Invalid mirror image reference: {mirror_ref}")

    if ":" in repo_with_tag:
        tag_idx = repo_with_tag.rfind(":")
        tag = repo_with_tag[tag_idx + 1 :]
        repo = repo_with_tag[:tag_idx]
    else:
        repo = repo_with_tag
        tag = "latest"

    if not repo or not tag:
        raise SystemExit(f"Invalid mirror image reference: {mirror_ref}")

    return host, repo, tag


def pull_cache_dir():
    return os.environ.get("PRS_PULL_CACHE_DIR")


def manifest_cache_path(repo, tag):
    cache_dir = pull_cache_dir()
    if not cache_dir:
        return None
    safe_repo = repo.replace("/", "__")
    safe_tag = tag.replace(":", "_")
    return os.path.join(cache_dir, f"manifest__{safe_repo}__{safe_tag}.json")


def load_cached_manifest(repo, tag):
    path = manifest_cache_path(repo, tag)
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as cached:
            return json.load(cached)
    return None


def save_cached_manifest(repo, tag, manifest):
    path = manifest_cache_path(repo, tag)
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as cached:
            json.dump(manifest, cached)


def registry_read_with_retries(url, headers=None, timeout=600, label="", max_attempts=6, initial_delay=2):
    delay = initial_delay
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code >= 500 or exc.code in (408, 429)
            if retryable and attempt < max_attempts:
                eprint(f"{label}ошибка HTTP {exc.code}, повтор {attempt}/{max_attempts} через {delay} с...")
                if "registry-1.docker.io" in body or "auth.docker.io" in body:
                    eprint("Зеркало временно не отдало blob и обратилось к Docker Hub, жду...")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            exc.args = (f"{exc.code} {exc.reason}\n{body}",)
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_attempts:
                eprint(f"{label}ошибка сети ({exc.reason}), повтор {attempt}/{max_attempts} через {delay} с...")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise

    if last_error is not None:
        raise last_error
    raise SystemExit(f"Cannot read registry URL: {url}")


def fetch_manifest(base, repo, ref):
    url = f"{base}/v2/{repo}/manifests/{ref}"
    payload = registry_read_with_retries(
        url,
        headers={"Accept": ACCEPT},
        timeout=120,
        label="Манифест: ",
        max_attempts=4,
    )
    manifest = json.loads(payload)
    if "manifests" in manifest:
        target_arch = detect_architecture()
        selected = None
        fallback = None
        for item in manifest.get("manifests", []):
            platform_info = item.get("platform") or {}
            if platform_info.get("os") != "linux":
                continue
            if fallback is None:
                fallback = item
            if platform_info.get("architecture") == target_arch:
                selected = item
                break
        chosen = selected or fallback
        if chosen is None:
            raise SystemExit(f"No compatible manifest found for {repo}:{ref}")
        return fetch_manifest(base, repo, chosen["digest"])
    return manifest


def cached_blob_path(digest):
    cache_dir = pull_cache_dir()
    if not cache_dir:
        return None
    os.makedirs(os.path.join(cache_dir, "blobs"), exist_ok=True)
    safe_digest = digest.replace(":", "_")
    return os.path.join(cache_dir, "blobs", safe_digest)


def download_blob(base, repo, digest):
    layer_hex = digest.split(":", 1)[-1]
    if layer_hex in EMPTY_LAYER_DIGESTS:
        return None

    cache_path = cached_blob_path(digest)
    if cache_path and os.path.isfile(cache_path):
        eprint(f"Использую кэш blob {digest}...")
        with open(cache_path, "rb") as cached:
            return cached.read()

    url = f"{base}/v2/{repo}/blobs/{digest}"
    blob = registry_read_with_retries(
        url,
        timeout=600,
        label=f"Blob {digest}: ",
        max_attempts=6,
    )

    if cache_path:
        with open(cache_path, "wb") as cached:
            cached.write(blob)

    return blob


def layer_uncompressed_data(base, repo, digest):
    layer_hex = digest.split(":", 1)[-1]
    if layer_hex in EMPTY_LAYER_DIGESTS:
        eprint(f"Слой {digest} — пустой, создаю локально.")
        return EMPTY_LAYER_TAR

    blob = download_blob(base, repo, digest)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gz:
            return gz.read()
    except (OSError, TypeError):
        return blob


def write_layer_tar(uncompressed, layer_dir):
    os.makedirs(layer_dir, exist_ok=True)
    layer_tar = os.path.join(layer_dir, "layer.tar")
    with open(layer_tar, "wb") as out:
        out.write(uncompressed)
    return hashlib.sha256(uncompressed).hexdigest()


def main():
    mirror_ref = sys.argv[1]
    local_image = sys.argv[2]
    host, repo, tag = parse_mirror_ref(mirror_ref)
    base = registry_base_url(host)

    eprint(f"Загрузка манифеста {repo}:{tag} с {base}...")
    manifest = load_cached_manifest(repo, tag)
    if manifest is None:
        manifest = fetch_manifest(base, repo, tag)
        save_cached_manifest(repo, tag, manifest)
    else:
        eprint(f"Использую кэш манифеста {repo}:{tag}...")

    config_digest = manifest["config"]["digest"]
    layers = manifest.get("layers") or []
    config_hex = config_digest.split(":", 1)[-1]

    with tempfile.TemporaryDirectory(prefix="prs-registry-pull-") as tmp:
        eprint(f"Загрузка конфигурации образа ({config_digest})...")
        config_data = download_blob(base, repo, config_digest)
        config_filename = f"{config_hex}.json"
        config_path = os.path.join(tmp, config_filename)
        with open(config_path, "wb") as out:
            out.write(config_data)

        layer_paths = []
        total = len(layers)
        for index, layer in enumerate(layers, start=1):
            digest = layer["digest"]
            layer_hex = digest.split(":", 1)[-1]
            eprint(f"Загрузка слоя {index}/{total} ({digest})...")
            uncompressed = layer_uncompressed_data(base, repo, digest)
            layer_dir = os.path.join(tmp, layer_hex)
            write_layer_tar(uncompressed, layer_dir)
            layer_paths.append(f"{layer_hex}/layer.tar")

        manifest_path = os.path.join(tmp, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as out:
            json.dump(
                [{
                    "Config": config_filename,
                    "RepoTags": [local_image],
                    "Layers": layer_paths,
                }],
                out,
            )

        tar_path = os.path.join(tmp, "image.tar")
        with tarfile.open(tar_path, "w") as archive:
            archive.add(manifest_path, arcname="manifest.json")
            archive.add(config_path, arcname=config_filename)
            for layer_path in layer_paths:
                archive.add(os.path.join(tmp, layer_path), arcname=layer_path)

        eprint(f"Импорт образа {local_image} в Docker...")
        subprocess.run(["docker", "load", "-i", tar_path], check=True)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        eprint(f"HTTP error from registry: {exc.code} {exc.reason}\n{body}")
        if "registry-1.docker.io" in body or "auth.docker.io" in body:
            eprint(
                "Зеркало не смогло отдать слой локально и попыталось скачать его с Docker Hub. "
                "Проверьте, что все слои образа опубликованы на зеркале."
            )
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        eprint(f"Cannot reach registry mirror: {exc.reason}")
        raise SystemExit(1) from exc
PY
}

pull_mirror_ref_with_retries() {
    local mirror_ref="$1"
    local local_image="$2"
    local host="${mirror_ref%%/*}"
    local max_attempts=4
    local delay=4
    local attempt=1

    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        if [[ "${PULL_SKIP_TO_HUB}" == "1" ]]; then
            return 1
        fi

        echo "Загрузка образа ${local_image} с зеркала ${host} (попытка ${attempt}/${max_attempts})..."
        if pull_mirror_once_with_skip_option "${mirror_ref}" "${local_image}"; then
            return 0
        fi

        if [[ "${PULL_SKIP_TO_HUB}" == "1" ]]; then
            return 1
        fi

        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Повтор через ${delay} с... (Ctrl+I — переключиться на Docker Hub)"
            if ! wait_with_skip_option "${delay}"; then
                return 1
            fi
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return 1
}

load_required_images() {
    local -n _images_ref="$1"
    _images_ref=()

    if [[ -f "${REQUIRED_IMAGES_MANIFEST}" ]]; then
        local line
        while IFS= read -r line || [[ -n "${line}" ]]; do
            line="${line%%#*}"
            line="${line#"${line%%[![:space:]]*}"}"
            line="${line%"${line##*[![:space:]]}"}"
            [[ -n "${line}" ]] || continue
            _images_ref+=("${line}")
        done < "${REQUIRED_IMAGES_MANIFEST}"
    fi

    if [[ "${#_images_ref[@]}" -eq 0 ]]; then
        _images_ref=(
            "redis/redis-stack:7.2.0-v6"
            "rabbitmq:4.1.1-management"
            "postgres:16.1"
            "python:3.12-slim"
            "osixia/openldap"
            "grafana/grafana-enterprise:12.4.0-22081664032-ubuntu"
            "nginx:1.25.3-alpine-slim"
        )
    fi
}

pull_tty_available() {
    [[ -r /dev/tty ]]
}

mark_pull_skip_to_hub() {
    if [[ "${PULL_SKIP_TO_HUB}" == "1" ]]; then
        return 0
    fi

    PULL_SKIP_TO_HUB=1
    echo ""
    echo "Переключение на Docker Hub (прервано пользователем: Ctrl+I)."
    echo "Дальнейшие образы также будут загружаться только с Docker Hub."
}

read_skip_to_hub_key() {
    local key=""

    pull_tty_available || return 1
    if IFS= read -r -n 1 -t 0.2 key </dev/tty 2>/dev/null; then
        # Ctrl+I совпадает с символом Tab (^I).
        if [[ "${key}" == $'\t' ]]; then
            mark_pull_skip_to_hub
            return 0
        fi
    fi
    return 1
}

wait_with_skip_option() {
    local remaining="$1"

    while [[ "${remaining}" -gt 0 ]]; do
        if [[ "${PULL_SKIP_TO_HUB}" == "1" ]] || read_skip_to_hub_key; then
            return 1
        fi
        sleep 1
        remaining=$((remaining - 1))
    done
    return 0
}

pull_mirror_once_with_skip_option() {
    local mirror_ref="$1"
    local local_image="$2"
    local pull_pid

    if ! pull_tty_available; then
        pull_mirror_via_registry_api "${mirror_ref}" "${local_image}"
        return $?
    fi

    pull_mirror_via_registry_api "${mirror_ref}" "${local_image}" &
    pull_pid=$!

    while kill -0 "${pull_pid}" 2>/dev/null; do
        if read_skip_to_hub_key; then
            kill "${pull_pid}" 2>/dev/null || true
            wait "${pull_pid}" 2>/dev/null || true
            return 1
        fi
    done

    wait "${pull_pid}"
}

announce_mirror_first() {
    local mirror="$1"

    [[ "${PULL_MIRROR_FIRST_ANNOUNCED}" == "1" ]] && return 0
    PULL_MIRROR_FIRST_ANNOUNCED=1

    cat <<EOF
Настроено зеркало образов: ${mirror}
Сначала пробую загрузить недостающие образы с зеркала.
Если зеркало недоступно, будет использован Docker Hub.
Во время попыток загрузки с зеркала нажмите Ctrl+I, чтобы переключиться на Docker Hub
(и для всех следующих образов в этом запуске).
EOF
}

pull_ref_with_retries() {
    local ref="$1"
    local max_attempts=4
    local delay=4
    local attempt=1

    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Загрузка образа ${ref} (${attempt}/${max_attempts})..."
        if docker pull "${ref}"; then
            return 0
        fi

        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Повтор через ${delay} с..."
            sleep "${delay}"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return 1
}

pull_ref_from_docker_hub_with_retries() {
    local ref="$1"
    local max_attempts=4
    local delay=4
    local attempt=1

    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Загрузка образа ${ref} с Docker Hub (попытка ${attempt}/${max_attempts})..."
        if docker pull "${ref}"; then
            return 0
        fi

        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Повтор через ${delay} с..."
            sleep "${delay}"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return 1
}

report_pull_failure() {
    local image="$1"
    local mirror="${2:-}"
    local tried_hub="${3:-}"

    if [[ -n "${mirror}" ]]; then
        cat >&2 <<EOF
Cannot pull required Docker image: ${image}
$([[ "${tried_hub}" == "1" ]] && echo "" && echo "The configured mirror and Docker Hub were both tried.")
Configured registry mirror: ${mirror}
Expected reference: $(mirror_image_ref "${mirror}" "$(image_with_explicit_tag "${image}")")

Check that:
  - the mirror is reachable from this host
  - the image is published on the mirror under the same name and tag
  - python3 is installed on this host

Do not use registry-mirrors in daemon.json for product installation; set
  PRS_REGISTRY_MIRROR in .env or use --mirror HOST:PORT instead.
EOF
    else
        cat >&2 <<EOF
Cannot pull required Docker image: ${image}

Check that this host can reach Docker registries, including:
  - https://auth.docker.io
  - https://registry-1.docker.io

If Docker Hub is unavailable, set PRS_REGISTRY_MIRROR in .env or use --mirror.

If the error contains an IPv6 address and "i/o timeout", Docker may be trying an
unreachable IPv6 route. Fix IPv6 connectivity on the host or disable IPv6 for
Docker/the host network, then run ./run_one_app.sh again.
EOF
    fi
}

pull_image_with_retries() {
    local image="$1"
    local mirror="${2:-}"
    local image_ref

    image_ref="$(image_with_explicit_tag "${image}")"

    if docker image inspect "${image}" >/dev/null 2>&1 \
        || { [[ "${image_ref}" != "${image}" ]] && docker image inspect "${image_ref}" >/dev/null 2>&1; }; then
        echo "Docker image ${image} is already present locally."
        return 0
    fi

    if [[ -n "${mirror}" ]]; then
        if [[ "${PULL_SKIP_TO_HUB}" != "1" ]]; then
            announce_mirror_first "${mirror}"

            local mirror_ref
            mirror_ref="$(mirror_image_ref "${mirror}" "${image_ref}")"
            if pull_mirror_ref_with_retries "${mirror_ref}" "${image_ref}"; then
                if [[ "${image_ref}" != "${image}" ]]; then
                    docker tag "${image_ref}" "${image}" 2>/dev/null || true
                fi
                return 0
            fi

            if [[ "${PULL_SKIP_TO_HUB}" != "1" ]]; then
                echo "Не удалось загрузить ${image} с зеркала ${mirror}. Пробую Docker Hub..."
            fi
        else
            echo "Загрузка образа ${image} с Docker Hub (зеркало пропущено после Ctrl+I)..."
        fi

        if pull_ref_from_docker_hub_with_retries "${image}"; then
            return 0
        fi
        report_pull_failure "${image}" "${mirror}" "1"
        exit 1
    fi

    if pull_ref_with_retries "${image}"; then
        return 0
    fi

    report_pull_failure "${image}"
    exit 1
}

pull_required_images() {
    if [[ "${PRS_SKIP_IMAGE_PULL:-0}" == "1" ]]; then
        return
    fi

    local required_images=()
    load_required_images required_images

    local image
    for image in "${required_images[@]}"; do
        pull_image_with_retries "${image}" "${registry_mirror}"
    done
}

load_dotenv "${DOTENV_FILE}"

srv="${PRS_HOSTNAME:-${HOSTNAME:-$(hostname)}}"
ssl="${PRS_SSL:-false}"
build="${PRS_BUILD:-false}"
registry_mirror="$(normalize_registry_mirror "${PRS_REGISTRY_MIRROR:-}")"

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
        --build)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --build requires true or false." >&2
                exit 1
            fi
            build="${2,,}"
            shift 2
            ;;
        --mirror)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Option --mirror requires a host[:port] value." >&2
                exit 1
            fi
            registry_mirror="$(normalize_registry_mirror "$2")"
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

case "${build}" in
    true)
        up_args=(up -d --build)
        ;;
    false)
        up_args=(up -d)
        ;;
    *)
        echo "Option --build accepts only true or false." >&2
        exit 1
        ;;
esac

sed -i "s/NGINX_HOST=.*/NGINX_HOST=${srv}/" docker/compose/.cont_one_app.env

extra_env=()
if [ -f docker/compose/.cont_one_app.secrets.env ]; then
    extra_env=(--env-file docker/compose/.cont_one_app.secrets.env)
fi

pull_required_images

docker compose --env-file docker/compose/.cont_one_app.env "${extra_env[@]}" \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_volume.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.grafana.yml \
-f "${nginx_compose}" \
-f docker/compose/docker-compose.ports.yml \
-f docker/compose/docker-compose.restart.yml \
"${up_args[@]}"
