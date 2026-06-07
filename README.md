<div align="center">
  <img src="pics/logo.png" alt="Пересвет" width="300"/>

  **Платформа-конструктор для промышленной автоматизации, IoT и умных объектов**

  [![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
  [![Docs](https://img.shields.io/badge/docs-online-brightgreen)](https://vovaman.github.io/peresvet/)
  [![GitHub Releases](https://img.shields.io/github/v/release/Vovaman/peresvet)](https://github.com/Vovaman/peresvet/releases)

  [Документация](https://vovaman.github.io/peresvet/) · [Примеры](https://github.com/Vovaman/peresvet_examples) · [English](README_en.md)
</div>

---

## Что такое Пересвет?

**МПК-Пересвет** — открытая платформа для построения систем автоматизации технических объектов: промышленных предприятий, умных зданий, производственных линий. Вдохновлена идеями PI System (OSIsoft) и GE iHistorian — с той же функциональностью, но на современном стеке и без лицензионных ограничений.

Платформа предоставляет то, чего не хватает обычным базам данных реального времени (Prometheus, VictoriaMetrics): **иерархию объектов**, **расчётные теги**, **тревоги**, **внешние методы**, **двунаправленные коннекторы** — всё необходимое для построения полноценной SCADA или MES-системы.

---

## Для каких задач

| Область | Примеры |
|---|---|
| **Промышленная автоматизация** | SCADA, диспетчеризация, мониторинг, MES |
| **Мониторинг эффективности** | OEE-анализ производственных линий ([пример: Абрау-Дюрсо](https://github.com/ioterra-ru/customer-abraudurso)) |
| **Умный дом / здание** | Интеграция с Zigbee2MQTT, управление устройствами |
| **Программно-аппаратные комплексы** | Встраиваемые системы, Raspberry Pi, ARM64 |

---

## Ключевые возможности

- **Иерархия объектов** — модель предприятия как дерево объектов с тегами, тревогами, расписаниями
- **Расчётные теги** — параметры, вычисляемые из других в реальном времени
- **Внешние методы** — Python-скрипты, запускаемые по событиям (изменение тега, тревога, расписание)
- **Коннекторы** — двунаправленный обмен данными через MQTT, WebSocket и другие протоколы
- **Хранилище истории** — PostgreSQL и/или VictoriaMetrics
- **Grafana UI** — визуализация, мнемосхемы, готовый конфигуратор модели
- **Анимированные SVG-мнемосхемы** — через [prs-inkscape-grafana](https://github.com/ioterra-ru/prs-inkscape-grafana)
- **MCP-интеграция** — управление платформой через AI-инструменты (Claude, Cursor и др.)
- **Docker-развёртывание** — от одного контейнера до микросервисной архитектуры

---

## Версии платформы

| Возможность | Открытая (этот репозиторий) | [Промышленная](https://github.com/mp-co-ru/mpc-peresvet) |
|---|:---:|:---:|
| Лицензия | Apache 2.0 (бесплатно) | Коммерческая |
| Объектная модель (иерархия, теги, тревоги, методы) | ✅ | ✅ |
| Коннекторы MQTT / WebSocket | ✅ | ✅ |
| Grafana UI + конфигуратор | ✅ | ✅ |
| MCP-сервер (AI-интеграция) | ✅ | ✅ |
| Хранилище PostgreSQL / VictoriaMetrics | ✅ (одно) | ✅ (несколько одновременно) |
| Масштабирование и высокая доступность (HA) | — | ✅ |
| Промышленные протоколы (OPC UA, Modbus и др.) | — | ✅ |
| Готовые отраслевые модели | — | ✅ |
| Разделение модели и среды исполнения | — | ✅ |
| Официальная поддержка (SLA) | — | ✅ |

> Если нужна промышленная версия или поддержка — свяжитесь с нами: [mp-co-ru](https://github.com/mp-co-ru).

---

## Быстрый старт

### Требования

- Ubuntu 22.04+ (или любой Linux с Docker)
- [Docker](https://docs.docker.com/engine/install/ubuntu/) + Docker Compose

### Установка

```bash
# Скачиваем последний релиз
wget https://github.com/Vovaman/peresvet/releases/latest/download/peresvet.tar.gz
tar -xzf peresvet.tar.gz
cd peresvet

# Запускаем платформу (все сервисы в одном контейнере — рекомендуется для старта)
./run_one_app.sh
```

Открываем браузер: **http://localhost/grafana**

> Логин/пароль по умолчанию: `admin` / `admin`. При первом входе Grafana предложит сменить пароль.

<div align="center">
  <img src="pics/welcome.png" alt="Главная страница Grafana" width="600"/>
</div>

По умолчанию откроется панель конфигуратора модели:

<div align="center">
  <img src="pics/configurator.png" alt="Конфигуратор" width="600"/>
</div>

### Другие варианты запуска

| Скрипт | Назначение |
|---|---|
| `./run_one_app.sh` | Все сервисы в одном контейнере (рекомендуется для старта и небольших систем) |
| `./run_all_svc_in_one.sh` | Все сервисы платформы в одном контейнере (без внешних зависимостей) |
| `./run.sh` | Каждая группа сущностей в отдельном контейнере (микросервисная архитектура) |
| `sudo ./run_one_app_ssl_letsencrypt_generate_certificates.sh <домен>` | Генерация TLS-сертификата Let's Encrypt для публичного сервера |
| `./run_one_app_ssl_letsencrypt.sh` | Запуск с HTTPS (после получения сертификата) |

Полная инструкция по установке: [документация](https://mp-co-ru.github.io/mpc-peresvet/installation.html).

---

## Архитектура

```
Browser (Grafana / Конфигуратор)
        │
      nginx  ──── MCP-серверы (AI-клиенты: Claude, Cursor...)
        │
    one_app (FastAPI)
    ├── Objects   ── LDAP (иерархия модели)
    ├── Tags      ── Redis (кэш) + PostgreSQL / VictoriaMetrics (история)
    ├── Alerts    ─┐
    ├── Methods   ─┤── RabbitMQ (события и команды)
    ├── Connectors─┘
    └── Schedules
```

Сервисы общаются через RabbitMQ. Модель объектов хранится в OpenLDAP. Платформа поддерживает как монолитный (`one_app`), так и распределённый (микросервисный) режим запуска.

---

## MCP-серверы (AI-интеграция)

Платформа поддерживает протокол MCP (Model Context Protocol), что позволяет управлять ею напрямую из AI-инструментов (Claude Desktop, Cursor, etc.).

| Эндпоинт | URL |
|---|---|
| MCP Peresvet (HTTP) | `http://<сервер>/mcp/peresvet/mcp` |
| MCP Peresvet (SSE) | `http://<сервер>/mcp/peresvet/sse` |
| MCP Grafana (HTTP) | `http://<сервер>/mcp/grafana/mcp` |

Конфигурация транспортов — в файле `docker/compose/.cont_one_app.env`:
- `MCP_PERESVET_TRANSPORT` — `sse` | `http` | `stdio`
- `MCP_GRAFANA_TRANSPORT` — `sse` | `streamable-http`

---

## Примеры и экосистема

- [peresvet_examples](https://github.com/Vovaman/peresvet_examples) — пошаговые примеры работы с платформой
- [customer-abraudurso](https://github.com/ioterra-ru/customer-abraudurso) — OEE-мониторинг конвейерной линии (внедрено на заводе Абрау-Дюрсо)
- [prs-inkscape-grafana](https://github.com/ioterra-ru/prs-inkscape-grafana) — создание анимированных SVG-мнемосхем через Inkscape

---

## Документация

Полная документация (на русском языке): **https://vovaman.github.io/peresvet/**

Разделы:
- [Описание и термины](https://vovaman.github.io/peresvet/description.html)
- [Установка](https://mp-co-ru.github.io/mpc-peresvet/installation.html)
- [Конфигуратор](https://vovaman.github.io/peresvet/configurator/configurator.html)
- [Примеры](https://vovaman.github.io/peresvet/examples/examples.html)
- [API](https://vovaman.github.io/peresvet/api.html)
- [Архитектура](https://vovaman.github.io/peresvet/architecture.html)

---

## Администрирование

### Резервное копирование Docker-контейнеров

```bash
cd /путь/к/peresvet
./admin_scripts/docker/running_containers_backup.sh
```

Восстановление:

```bash
./admin_scripts/docker/running_containers_restore.sh \
  --archive=backups/docker_runtime/ИМЯ_АРХИВА.tar.gz
```

### Резервное копирование OpenLDAP (модель объектов)

```bash
./admin_scripts/ldap/ldap_volume_backup.sh
```

Восстановление:

```bash
./admin_scripts/ldap/ldap_volume_restore.sh \
  --assume_yes=1 \
  --archive=backups/ldap/ИМЯ_АРХИВА.tar.gz
```

Подробности параметров — в [документации по администрированию](https://vovaman.github.io/peresvet/administration.html).

---

## Отладка и разработка

Платформа разрабатывается в VSCode. Для локальной разработки:

```bash
# Устанавливаем виртуальное окружение
pipenv install

# Запускаем инфраструктуру без сервисов платформы
./run_one_app_debug.sh

# Открываем src/services/one_app/one_app.py и запускаем в режиме отладки
```

Для отладки внутри контейнера:

```bash
# Запускаем контейнеры
./run.sh -d

# Запускаем отладку нужного сервиса (пример: app_psql в контейнере f438)
./run_debug.sh f438 app_psql
```

В VSCode выбираем конфигурацию `MPC_DEBUG: f438 app_psql` и нажимаем F5.

Подробнее: требуется плагин `ms-vscode-remote.remote-containers`.

---

## Тесты

```bash
# Unit-тесты с отчётом о покрытии
./run_tests.sh
```

Нагрузочные тесты (Locust) описаны в отдельном разделе [документации](https://vovaman.github.io/peresvet/).

---

## Генерация документации

```bash
cd docs
make html
# Результат: docs/build/html/index.html
```

---

## Участие в проекте

Мы рады вкладу сообщества! Подробности — в [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Лицензия

Apache 2.0 — см. файл [LICENSE](LICENSE).
