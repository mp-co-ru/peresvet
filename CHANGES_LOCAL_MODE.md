# Изменения для локального режима (v0.17.0)

## Новые возможности

### 1. Флаг `--local` в `build_dev_distribution.sh`

Добавлен флаг `--local`, который позволяет создавать дистрибутив с предустановленными зависимостями:

```bash
./packaging/build_dev_distribution.sh --local
```

При использовании этого флага:
- Устанавливаются системные пакеты (libldap2-dev, libsasl2-dev, slapd, ldap-utils)
- Устанавливаются Python-пакеты из requirements.txt
- FastMCP и aiohttp НЕ устанавливаются, так как они будут установлены при сборке Docker-образов
- Подготовленные зависимости копируются в дистрибутив в папки `apt-cache/` и `python-site-packages/`

### 2. Флаг `--local` в `run_one_app.sh`

Добавлен флаг `--local`, который активирует локальный режим:

```bash
./run_one_app.sh --local
```

Или через переменную окружения:
```bash
LOCAL_MODE=true ./run_one_app.sh
```

### 3. Обновленные Dockerfile

Все Dockerfile-ы обновлены для поддержки локального режима:

- `Dockerfile.one_app.uvicorn` - устанавливает системные пакеты и Python-пакеты из подготовленных артефактов
- `Dockerfile.mcp.peresvet` - использует подготовленные Python-пакеты (fastmcp, aiohttp)
- `Dockerfile.grafana` - использует подготовленные системные пакеты (если есть)

### 4. Обновленные Docker Compose файлы

Все Docker Compose файлы обновлены для передачи аргумента `LOCAL_MODE`:

- `docker-compose.one_app.yml`
- `docker-compose.mcp.peresvet.yml`
- `docker-compose.grafana.yml`

### 5. Обновлённая документация

- Добавлен документ `LOCAL_MODE.md` с подробным описанием локального режима
- Обновлён `README.md` с описанием новых флагов и переменных окружения
- Добавлен скрипт `cleanup_local_dependencies.sh` для очистки подготовленных зависимостей

## Обратная совместимость

Все изменения обратно совместимы. Локальный режим по умолчанию отключён (`LOCAL_MODE=false`).

Для использования локального режима необходимо:
1. Подготовить дистрибутив с флагом `--local`
2. Запустить `run_one_app.sh` с флагом `--local` или установить `LOCAL_MODE=true`

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `LOCAL_MODE` | `false` | Локальный режим: использовать предустановленные зависимости |

## Директории и файлы

### Новые файлы
- `LOCAL_MODE.md` - документация по локальному режиму
- `cleanup_local_dependencies.sh` - скрипт для очистки зависимостей
- `CHANGES_LOCAL_MODE.md` - этот файл

### Изменённые файлы
- `packaging/build_dev_distribution.sh` - добавлен флаг `--local`
- `run_one_app.sh` - добавлен флаг `--local` и переменная окружения `LOCAL_MODE`
- `.env` - добавлена переменная `LOCAL_MODE`
- `.gitignore` - добавлены исключения для подготовленных зависимостей
- `.dockerignore` - добавлены исключения для подготовленных зависимостей
- `docker/docker-files/all/Dockerfile.one_app.uvicorn` - поддержка локального режима
- `docker/docker-files/mcp/Dockerfile.mcp.peresvet` - поддержка локального режима
- `docker/docker-files/grafana/Dockerfile.grafana` - поддержка локального режима
- `docker/compose/docker-compose.one_app.yml` - передача `LOCAL_MODE`
- `docker/compose/docker-compose.mcp.peresvet.yml` - передача `LOCAL_MODE`
- `docker/compose/docker-compose.grafana.yml` - передача `LOCAL_MODE`
- `README.md` - обновлена документация

## Использование

### Подготовка дистрибутива для ограниченного интернета

```bash
# Установите системные зависимости
sudo apt-get update
sudo apt-get install -y --no-install-recommends libldap2-dev libsasl2-dev
sudo DEBIAN_FRONTEND=noninteractive apt install -y slapd ldap-utils

# Установите Python-зависимости
python3 -m pip install --no-cache-dir -r requirements.txt
python3 -m pip install --no-cache-dir fastmcp aiohttp

# Подготовьте дистрибутив
./packaging/build_dev_distribution.sh --local

# Перенесите дистрибутив на целевой сервер и распакуйте
tar -xzf dist/peresvet-dev-*.tar.gz

# Запустите на целевом сервере
cd peresvet-dev-*
./run_one_app.sh --local
```

### Подготовка дистрибутива с полным доступом к интернету

```bash
# Подготовьте дистрибутив
./packaging/build_dev_distribution.sh

# Перенесите дистрибутив на целевой сервер и распакуйте
tar -xzf dist/peresvet-dev-*.tar.gz

# Запустите на целевом сервере (интернет должен быть доступен)
cd peresvet-dev-*
./run_one_app.sh
```
