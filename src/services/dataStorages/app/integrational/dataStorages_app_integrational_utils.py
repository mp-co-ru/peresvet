import re
from enum import IntEnum
from typing import Iterable


class OperationKind(IntEnum):
    GET = 0
    SET = 1


_RE_NAMED_PARAM = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def validate_sql(sql: str, kind: OperationKind) -> None:
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Пустой query.")

    # минимальные проверки безопасности
    if ";" in sql:
        raise ValueError("Запрещён multi-statement (символ ';').")

    head = sql.lstrip().lower()
    if kind == OperationKind.GET:
        if not head.startswith("select") and not head.startswith("with"):
            raise ValueError("Для GET разрешены только SELECT/CTE запросы.")
    elif kind == OperationKind.SET:
        if not (
            head.startswith("insert")
            or head.startswith("update")
            or head.startswith("with")
        ):
            raise ValueError("Для SET разрешены только INSERT/UPDATE/CTE запросы.")
    else:
        raise ValueError(f"Неизвестный kind операции: {kind}.")


def rewrite_named_params(sql: str) -> tuple[str, list[str]]:
    """Переписывает параметры вида :name в $1, $2... (для asyncpg).

    Важно: `::type` (PostgreSQL cast) не трактуется как параметр из-за (?<!:) в regex.
    """
    params: list[str] = []
    index_by_name: dict[str, int] = {}

    def repl(match: re.Match) -> str:
        name = match.group(1)
        idx = index_by_name.get(name)
        if idx is None:
            idx = len(params) + 1
            index_by_name[name] = idx
            params.append(name)
        return f"${idx}"

    rewritten = _RE_NAMED_PARAM.sub(repl, sql)
    return rewritten, params


def ensure_columns_yxq(columns: Iterable[str]) -> None:
    cols = {c.lower() for c in columns}
    missing = [c for c in ("y", "x", "q") if c not in cols]
    if missing:
        raise ValueError(f"Результат запроса должен содержать колонки y, x, q. Нет: {missing}")

