import asyncio
import json
import logging
import sys
import copy
import aio_pika
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
sys.path.append(".")

from src.services.retranslator.app.retranslator_app_settings import RetranslatorAppSettings
from src.services.retranslator.app.scheduler_conf import job_defaults, executors
from src.common import hierarchy
from src.common import svc

class RetranslatorApp(svc.Svc):
    """Сервис пересылки и дублирования сообщения для правильной визуализации в Grafana.

    Подписывается на очередь ``tags_app_api`` обменника ``tags_app_api``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    """

    def __init__(self, settings: RetranslatorAppSettings, *args, **kwargs):
        self.scheduler = AsyncIOScheduler(
            job_defaults=job_defaults,
            job_executors=executors
        )
        self.tag_sub = {}
        super().__init__(settings, *args, **kwargs)
        
    def get_cur_tag_val(self, tag_id: str) -> int:
        # Поиск текущего значения тега
        cache = {
        "86224f28-e283-103d-9f68-a15ac671071b": 10,
        "86271044-e283-103d-9f6b-a15ac671071b": 20,
        "862e04d0-e283-103d-9f70-a15ac671071b": 100,
        "863374b0-e283-103d-9f75-a15ac671071b": 1,
        "8637ef2c-e283-103d-9f78-a15ac671071b": 2,
        "863dfec6-e283-103d-9f7d-a15ac671071b": 3,
        "8643d648-e283-103d-9f82-a15ac671071b": 4,
        "86492602-e283-103d-9f87-a15ac671071b": 5
        }
        return cache.get(tag_id)

    async def _bind_event_callback(self, message: aio_pika.abc.AbstractIncomingMessage):
        async with message.process(ignore_processed=True):
            action = message.routing_key
            routing_key = message.headers.get('routing_key')
            source_name = message.headers.get('source_name')
            destination_name = message.headers.get('destination_name')
            self._logger.info(message)
            if routing_key and destination_name and source_name=='amq.topic':
                match action:
                    case "binding.created":
                        if self.tag_sub.get(routing_key):
                            self.tag_sub[routing_key]['count'] += 1
                            self.tag_sub[routing_key]['queues'].add(destination_name,)
                        else:
                            self.tag_sub[routing_key] = {"count": 1, 'queues': set()}
                            self.tag_sub[routing_key]["queues"].add(destination_name,)
                    case "binding.deleted":
                        if self.tag_sub.get(routing_key):
                            self.tag_sub[routing_key]['count'] -= 1
                            if self.tag_sub[routing_key]['count'] == 0:
                                self.tag_sub.pop(routing_key)
            self._logger.error(self.tag_sub)
            await message.ack()

    async def retranslate(self):
        for routing_key in self.tag_sub.keys():
            cur_tag_val = self.get_cur_tag_val(routing_key)
            await self._tags_topic_exchange.publish(
            message=aio_pika.Message(
                body=str(cur_tag_val).encode(),
            ), routing_key=routing_key)
            self._logger.info(f"Send message {cur_tag_val} to {routing_key}")

    async def _connect_to_topic(self):
        connected = False
        while not connected:
            try:
                self._logger.debug("Создание очереди для передачи данных от тегов...")
                self._bind_event_amqp_channel = await self._amqp_connection.channel()
                await self._bind_event_amqp_channel.set_qos(1)

                self._bind_event_amqp_queue = await self._bind_event_amqp_channel.declare_queue("bind_event_topic_queue", durable=False)
                await self._bind_event_amqp_queue.bind(
                    exchange="amq.rabbitmq.event",
                    routing_key="binding.*"
                )
                await self._bind_event_amqp_queue.consume(self._bind_event_callback)

                self._tags_amqp_channel = await self._amqp_connection.channel()
                self._tags_topic_exchange = await self._tags_amqp_channel.declare_exchange("amq.topic", aio_pika.ExchangeType.TOPIC, durable=True)

                connected = True

                self._logger.info("Создание очереди и топиков для передачи данных тегов завершено.")

            except aio_pika.AMQPException as ex:
                self._logger.error(f"Ошибка связи с брокером: {ex}")
                await asyncio.sleep(5)
        
    async def on_startup(self) -> None:
        await super().on_startup()
        self.scheduler.add_job(self.retranslate, 'interval', seconds=2)
        self.scheduler.start()
        return await self._connect_to_topic()

    async def on_shutdown(self) -> None:
        await self._bind_event_amqp_channel.close()
        return await super().on_shutdown()
        
settings = RetranslatorAppSettings()

app = RetranslatorApp(settings=settings, title="ConnectorsApp")

