import datetime
from dateutil import tz
import time
import ciso8601

#TODO: попробовать модуль isotoint

# функция преобразовывает пришедшую метку времени в количество микросекунд
microsec = 1000000
start_ts = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)

def ts (field: int | str = None) -> int:
    """ Функция возвращает метку времени как целое число микросекунд,
    прошедших с 1 января 1970 г. UTC

    :param field: Входная метка времени. Если None - возвращается текущее
    время, если целое число - то оно и возвращается, если строка - то
    она интерпретируется как метка времени в формате ISO8601.
    :type field: None | int | str
    """

    if field is None:
        return now_int()
    elif isinstance (field, int):
        return field

    timestampFrom = ciso8601.parse_datetime (field)
    if timestampFrom.tzinfo is None:
        timestampFrom = timestampFrom.replace (tzinfo=datetime.timezone.utc)

    return int ((timestampFrom - start_ts).total_seconds() * microsec)

def int_to_local_timestamp (int_ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int_ts / microsec, tz.tzlocal())

def now_int() -> int:
    """ Количество микросекунд, начиная с 1 января 1970 UTC
    :rtype: int
    """
    return int(time.time() * microsec)
