# Участие в разработке платформы Пересвет

Спасибо, что рассматриваете возможность внести вклад в проект! Любые улучшения приветствуются: будь то исправление ошибки, новая фича, улучшение документации или пример использования.

---

## Содержание

- [Кодекс поведения](#кодекс-поведения)
- [С чего начать](#с-чего-начать)
- [Как сообщить об ошибке](#как-сообщить-об-ошибке)
- [Как предложить новую функцию](#как-предложить-новую-функцию)
- [Процесс разработки](#процесс-разработки)
- [Стиль кода](#стиль-кода)
- [Документация](#документация)
- [Вопросы и обсуждения](#вопросы-и-обсуждения)

---

## Кодекс поведения

Мы строим открытое и уважительное сообщество. Пожалуйста:

- Будьте уважительны и конструктивны в общении
- Принимайте чужую точку зрения
- Фокусируйтесь на том, что лучше для проекта и его пользователей

---

## С чего начать

1. **Ознакомьтесь с проектом** — прочитайте [README](README.md) и [документацию](https://vovaman.github.io/peresvet/)
2. **Запустите платформу локально** — следуйте [инструкции по установке](https://mp-co-ru.github.io/mpc-peresvet/installation.html)
3. **Изучите открытые задачи** — посмотрите [Issues](https://github.com/Vovaman/peresvet/issues), особенно с метками `good first issue` и `help wanted`
4. **Свяжитесь с нами**, если не знаете с чего начать — откройте Issue или напишите в Discussion

---

## Как сообщить об ошибке

1. Убедитесь, что ошибка ещё не [зарегистрирована](https://github.com/Vovaman/peresvet/issues)
2. Создайте новый Issue, указав:
   - **Версию платформы** (из [releases](https://github.com/Vovaman/peresvet/releases))
   - **Операционную систему** и версию Docker
   - **Шаги для воспроизведения** ошибки
   - **Ожидаемое и фактическое поведение**
   - **Логи** (при наличии)

---

## Как предложить новую функцию

1. Откройте Issue с тегом `enhancement`
2. Опишите:
   - **Задачу, которую решает функция** (не только "что сделать", но и "зачем")
   - **Предлагаемый способ реализации** (если есть идеи)
   - **Альтернативы**, которые вы рассматривали
3. Дождитесь обсуждения с мейнтейнерами — это поможет избежать работы, которая может не войти в проект

---

## Процесс разработки

### Подготовка

```bash
# Форкаем репозиторий и клонируем свой форк
git clone git@github.com:<ВАШ_ЛОГИН>/peresvet.git
cd peresvet

# Добавляем upstream
git remote add upstream git@github.com:Vovaman/peresvet.git

# Устанавливаем зависимости
pipenv install
```

### Ветки

- `main` / `master` — стабильные релизы
- `dev` — текущая разработка; **все PR создаются в `dev`**

```bash
# Синхронизируемся с upstream перед началом работы
git fetch upstream
git checkout dev
git merge upstream/dev

# Создаём ветку для своих изменений
git checkout -b fix/описание-ошибки
# или
git checkout -b feature/название-функции
```

### Pull Request

1. Убедитесь, что тесты проходят: `./run_tests.sh`
2. При изменении поведения — обновите или добавьте тесты в `tests/`
3. При изменении API или конфигурации — обновите документацию в `docs/`
4. Создайте PR в ветку `dev` основного репозитория
5. В описании PR укажите:
   - Что изменено и зачем
   - Ссылку на связанный Issue (если есть): `Closes #123`
   - Как протестировали изменения

---

## Стиль кода

Проект написан на Python 3.12 с использованием FastAPI и Pydantic v2.

- **Форматирование** — следуем PEP 8; при наличии `black` или `ruff` в проекте — используем их
- **Типизация** — используйте аннотации типов для новых функций
- **Именование** — переменные и функции на английском (несмотря на русскоязычную документацию)
- **Комментарии в коде** — объясняйте *почему*, а не *что*; не дублируйте код в комментариях

### Структура сервиса

Каждый домен следует паттерну из четырёх слоёв:

```
*_api_crud.py    — HTTP CRUD роутеры (FastAPI)
*_model_crud.py  — LDAP-персистентность через RabbitMQ
*_app.py         — бизнес-логика, подписки на события
*_app_api.py     — чтение/запись данных (теги, коннекторы)
```

При добавлении нового домена придерживайтесь той же структуры.

---

## Документация

Документация написана на русском языке с использованием [Sphinx](https://www.sphinx-doc.org/).

```bash
# Генерация HTML-документации
cd docs
make html
```

При изменении поведения платформы обновляйте соответствующие `.rst`-файлы в `docs/source/`.

---

## Вопросы и обсуждения

- **Баги и предложения**: [GitHub Issues](https://github.com/Vovaman/peresvet/issues)
- **Общие вопросы**: [GitHub Discussions](https://github.com/Vovaman/peresvet/discussions)

---

*Спасибо за ваш вклад в развитие открытой автоматизации!*

---

# Contributing to Peresvet Platform

*(English version)*

Thank you for considering a contribution! Bug fixes, new features, documentation improvements, and usage examples are all welcome.

## Quick guide

1. **Fork** the repository and clone your fork
2. Create a branch from `dev`: `git checkout -b fix/description` or `git checkout -b feature/name`
3. Make your changes, ensure tests pass: `./run_tests.sh`
4. Open a **Pull Request** targeting the `dev` branch
5. Describe what you changed and why; link any related Issue

## Reporting bugs

Open an [Issue](https://github.com/Vovaman/peresvet/issues) with:
- Platform version
- OS and Docker version
- Steps to reproduce
- Expected vs actual behavior
- Logs (if available)

## Code style

- Python 3.12, FastAPI, Pydantic v2
- Follow PEP 8; use type annotations for new functions
- Variable and function names in English
- Comments explain *why*, not *what*

## Documentation

Docs are written in Russian using Sphinx. Update relevant `.rst` files in `docs/source/` when changing platform behavior.

Build locally:

```bash
cd docs && make html
```
