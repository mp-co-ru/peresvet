import asyncio
import json
import sys
import os
import aiohttp
from urllib.parse import urlparse
import aio_pika
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
sys.path.append(".")

from src.common import svc
from src.services.retranslator.app.retranslator_app_settings import RetranslatorAppSettings
from src.services.retranslator.app.scheduler_conf import job_defaults, executors

class RetranslatorApp(svc.Svc):
    """Сервис пересылки и дублирования сообщения для правильной визуализации в Grafana.

    Подписывается на очередь ``tags_app_api`` обменника ``tags_app_api``\,
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


    async def get_cur_tag_val(self, tag_id: str):
        # Поиск текущего значения тега
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as sess:
                async with sess.get(self._conf.tags_app_url, json={"tagId": tag_id}) as resp:
                    if not resp.ok:
                        return None
                    response = await resp.json()
                    cur_tag_data = response.get('data')[0].get('data')[0][0]
                    return cur_tag_data
        except asyncio.exceptions.TimeoutError:
            return None

    async def retranslate_job(self, tag_id: str):
        updated_at = self.tag_sub[tag_id].get('updated_at')
        cached_tag_value = self.tag_sub[tag_id].get('last_val')
        if cached_tag_value is None:
            self._logger.info("Cached val is none")
            tag_cur_val = await self.get_cur_tag_val(tag_id)
            self.tag_sub[tag_id]['last_val'] = str(tag_cur_val)
        if updated_at:
            self._logger.info("Updated at is not None")
            timedelta = datetime.now() - updated_at
            if timedelta.total_seconds() < 5:
                return
        self._logger.info("Sending message")
        await self._tags_topic_exchange.publish(
        message=aio_pika.Message(
            body=self.tag_sub[tag_id]['last_val'].encode(),
        ), routing_key=tag_id)
        self._logger.info(f"Send message {self.tag_sub[tag_id]['last_val']} to {tag_id}")
        return


    async def add_tag_task(self, tag_id: str):
        task = self.scheduler.add_job(self.retranslate_job, trigger=IntervalTrigger(seconds=5) ,args=[tag_id])
        return task

    async def _bind_event_callback(self, message: aio_pika.abc.AbstractIncomingMessage):
        async with message.process(ignore_processed=True):
            action = message.routing_key
            routing_key = message.headers.get('routing_key')
            source_name = message.headers.get('source_name')
            destination_name = message.headers.get('destination_name')
            if routing_key and destination_name and source_name=='amq.topic':
                match action:
                    case "binding.created":
                        if self.tag_sub.get(routing_key):
                            self.tag_sub[routing_key]['count'] += 1
                            self.tag_sub[routing_key]['queues'].add(destination_name,)
                        else:
                            self.tag_sub[routing_key] = {"count": 1, 'queues': set()}
                            self.tag_sub[routing_key]["queues"].add(destination_name,)
                            task = await self.add_tag_task(routing_key)
                            self.tag_sub[routing_key]["task"] = task
                            await self.subscribe_to_tag(routing_key)
                    case "binding.deleted":
                        if self.tag_sub.get(routing_key):
                            self.tag_sub[routing_key]['count'] -= 1
                            if self.tag_sub[routing_key]['count'] == 0:
                                self.tag_sub[routing_key]['task'].remove()
                                await self.unsubscribe_from_tag(routing_key)
                                self.tag_sub.pop(routing_key)
            await message.ack()

    async def subscribe_to_tag(self, tag_id):
        await self._amqp_consume_queue["queue"].bind(
                        exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
                        routing_key=tag_id)

    async def unsubscribe_from_tag(self, tag_id):
        await self._amqp_consume_queue["queue"].unbind(
                        exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
                        routing_key=tag_id)

    async def retranslate(self, routing_key: str, data: str):
        if not hasattr(self, "_tags_topic_exchange"):
            return
        await self._tags_topic_exchange.publish(
        message=aio_pika.Message(
            body=data.encode(),
        ), routing_key=routing_key)
        self._logger.info(f"Send message {data} to {routing_key}")
        # Сохранение в кеш последнего значения тега
        self.tag_sub[routing_key]["last_val"] = data
        # Обновление метки времени обновления значения тега
        self.tag_sub[routing_key]['updated_at'] = datetime.now()

    async def _connect_to_topic(self):
        connected = False
        while not connected:
            try:
                self._logger.info("Создание очереди для передачи данных от тегов...")
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
                self._logger.error(f"{self._config.svc_name} :: Ошибка связи с брокером: {ex}")
                await asyncio.sleep(5)
        return

    async def _process_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        routing_key = message.routing_key
        async with message.process(ignore_processed=True):
            mes = message.body.decode()
            try:
                mes = json.loads(mes)
                self._logger.info(mes)
                if mes.get('action') == "tags.uploadData":
                    tag_data = mes.get('data').get('data')[0].get('data')[0][0]
                    # Сохраняем последнее значение тега в кеше tag_sub
                    self.tag_sub
                    # Ретранслируем его с routing_key равным id тега в обменник amq.topic
                    await self.retranslate(routing_key=routing_key, data=str(tag_data))
                await message.ack()
            except json.decoder.JSONDecodeError:
                self._logger.error(f"{self._config.svc_name} :: Сообщение {mes} не в формате json.")
                await message.ack()
                return
        return

    async def init_tag_sub(self):
        rabbitmq_usr = urlparse(self._conf.amqp_url).username
        rabbitmq_pass = urlparse(self._conf.amqp_url).password
        async with aiohttp.ClientSession() as sess:
            async with sess.get(self._conf.rabbitmq_api_url + "/exchanges/%2F/amq.topic/bindings/source",
                                auth=aiohttp.BasicAuth(rabbitmq_usr, rabbitmq_pass)) as resp:
                response = await resp.json()
                for binding in response:
                    routing_key = binding.get('routing_key')
                    destination = binding.get('destination')
                    if self.tag_sub.get(routing_key):
                        self.tag_sub[routing_key]['count'] += 1
                        self.tag_sub[routing_key]['queues'].add(destination,)
                    else:
                        self.tag_sub[routing_key] = {"count": 1, 'queues': set()}
                        self.tag_sub[routing_key]["queues"].add(destination,)
                        task = await self.add_tag_task(routing_key)
                        self.tag_sub[routing_key]["task"] = task
                        await self.subscribe_to_tag(routing_key)
        return

    async def on_startup(self) -> None:
        await super().on_startup()
        self.scheduler.start()
        await self.init_tag_sub()
        await self._connect_to_topic()
        return

    async def on_shutdown(self) -> None:
        await self._bind_event_amqp_channel.close()
        return await super().on_shutdown()

settings = RetranslatorAppSettings()

app = RetranslatorApp(settings=settings, title="ConnectorsApp")
