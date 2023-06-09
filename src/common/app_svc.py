import asyncio
import json
from collections.abc import MutableMapping
from uuid import uuid4
from aio_pika import Message
import aio_pika.abc

from src.common.svc import Svc
from src.common.svc_settings import SvcSettings


class AppSvc(Svc):

    _callback_queue: aio_pika.abc.AbstractRobustQueue

    def __init__(self, settings: SvcSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self.api_version = settings.api_version
        self._callback_futures: MutableMapping[str, asyncio.Future] = {}


    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        self._callback_queue = await self._amqp_channel.declare_queue(
            durable=True, exclusive=True
        )
        await self._callback_queue.bind(
            exchange=self._amqp_publish["main"]["exchange"],
            routing_key=self._callback_queue.name
        )

        await self._callback_queue.consume(self._on_rpc_response, no_ack=True)

    async def _on_rpc_response(
            self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        if message.correlation_id is None:
            self._logger.error("У сообщения не выставлен параметр `correlation_id`")
        else:
            future: asyncio.Future = self._callback_futures.pop(message.correlation_id, None)
            future.set_result(json.loads(message.body.decode()))

    async def _post_message(self, mes: dict, reply: bool = False) -> dict | None:
        body = json.dumps(mes, ensure_ascii=False).encode()
        if reply:
            correlation_id = str(uuid4())
            reply_to = self._callback_queue.name
            future = asyncio.get_running_loop().create_future()
            self._callback_futures[correlation_id] = future

        await self._amqp_publish["main"]["exchange"].publish(
            message=Message(
                body=body, correlation_id=correlation_id, reply_to=reply_to
            ), routing_key=self._config.publish["main"]["routing_key"]
        )
        if not reply:
            return

        return await future