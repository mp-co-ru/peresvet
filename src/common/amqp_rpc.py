"""Константы для RPC поверх AMQP (direct reply-to)."""


class _NoAmqpRpcReply:
    """Вернуть из обработчика входящего сообщения с ``reply_to``,
    чтобы **не** публиковать ответ (побочный подписчик; отвечает другой сервис).
    """

    __slots__ = ()


NO_AMQP_RPC_REPLY = _NoAmqpRpcReply()
