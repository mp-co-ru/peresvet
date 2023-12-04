# Модуль чтения текущих данных.
# Протокол - HTTP.
# Количество тегов в запросе задаётся в окне создания запроса.
# База данных - postgresql или victoriametrics.

import json
import random

from locust import HttpUser, task, between, events

import time

from uuid import uuid4

class DataGetUser(HttpUser):

    def on_start(self):
        with open("/mnt/locust/tags_in_postgres.json", "r") as f:
            js = json.load(f)
            self.ids = js["0"]

            self.ids += js["1"]
            self.ids += js["2"]
            self.ids += js["4"]

        self.pack_size = self.environment.parsed_options.tags_in_pack

    @task
    def get_data(self):
        tags = random.sample(self.ids, self.pack_size)

        data = {
            "tagId": tags
        }

        self.client.get("", json=data)
