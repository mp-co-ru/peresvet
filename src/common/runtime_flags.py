"""Флаги времени выполнения процесса (например, фаза остановки composite-приложения)."""

# True с момента входа в lifespan shutdown корневого приложения one_app
# до завершения процесса. Сервисы могут не выполнять побочные действия (LDAP и т.д.),
# которые имеют смысл только при работающей платформе.
platform_shutting_down: bool = False


def set_platform_shutting_down(value: bool) -> None:
    global platform_shutting_down
    platform_shutting_down = value
