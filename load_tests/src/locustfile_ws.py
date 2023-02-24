from websocket import create_connection
import gevent
import ssl
import json
from random import randrange, uniform
from locust import HttpUser, between, task, events
import time

class WebSocketLoadTest(HttpUser):
    wait_time = between(1,5)

    @task
    def my_task(self):
        i = randrange(len(self.int_ids))
        body = json.dumps({
            "get": {
                "tagId": self.int_ids[i]
            }
        })
        self.ws.send(body)

    def on_start(self):
        with open("/mnt/locust/tags_type_1.json", "r") as f:
            self.int_ids = json.load(f)

        self.ws = create_connection(
            "ws://nginx/ws/data",
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )

        def _receive():
            while True:
                res = self.ws.recv()
                events.request_success.fire(
                        request_type='Websocket Receive Message',
                        name='test websocket message receive',
                        response_time=0,
                        response_length=len(res)
                )
                time.sleep(0.001)

        gevent.spawn(_receive)
