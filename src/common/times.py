import datetime
from dateutil import tz
import dateutil.parser as p
import time
import ciso8601

#TODO: попробовать модуль isotoint

# функция преобразовывает пришедшую метку времени в количество микросекунд
microsec = 1000000
start_ts = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)


def _int_str_as_microseconds(s: str) -> int | None:
    """Если строка — целое в десятичной записи, вернуть его как микросекунды (как у int).

    Нужно для query-параметров вида ``start=1776438870185000``, где значение приходит строкой.
    """
    s = s.strip()
    if not s:
        return None
    sign = 1
    if s[0] == "+":
        s = s[1:]
    elif s[0] == "-":
        sign = -1
        s = s[1:]
    if s.isdigit():
        return sign * int(s)
    return None


def ts (time_data: int | str | None = None) -> int:
    """Функция возвращает метку времени как целое число микросекунд,
    прошедших с 1 января 1970 г. UTC

    :param time_data: Входящая метка времени. По умолчанию - None.
        Если целое число - будет возвращена она же (микросекунды).
        Если строка из десятичных цифр (часто из query) — трактуется как то же целое.
        Иначе строка разбирается как ISO8601; если даты нет — см. разбор только времени.
    :type time_data: int | str = None
    :returns: Целое число микросекунд с 01.01.1970
    :rtype: int
    """
    if time_data is None:
        return now_int()
    elif isinstance (time_data, int):
        return time_data
    elif isinstance(time_data, str):
        as_int = _int_str_as_microseconds(time_data)
        if as_int is not None:
            return as_int

    def parse_ts(string: str) -> datetime.datetime:
        timestampFrom = ciso8601.parse_datetime (string)
        if timestampFrom.tzinfo is None:
            timestampFrom = timestampFrom.replace (tzinfo=datetime.timezone.utc)

        return timestampFrom

    try:
        timestampFrom = parse_ts(time_data)
    except ValueError as _:
        # предполагаем, что строка не содержит даты, только время
        timestampFrom = parse_ts(str(p.parse(time_data, default=datetime.datetime.now())))

    return int ((timestampFrom - start_ts).total_seconds() * microsec)

def int_to_local_timestamp (int_ts: int) -> datetime.datetime:
    if int_ts is None:
        return None
    return datetime.datetime.fromtimestamp(int_ts / microsec, tz.tzlocal())

def ts_to_local_str (ts: int | str) -> str:
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    return str(datetime.datetime.fromtimestamp(ts / microsec, tz.tzlocal()))

def now_int() -> int:
    """ Количество микросекунд, начиная с 1 января 1970 UTC
    :rtype: int
    """
    return int(time.time() * microsec)
