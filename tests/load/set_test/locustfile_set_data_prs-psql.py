# Модуль записи данных для нагрузочного тестирования.
# Класс DataSetUser имеет 4 функции для записи значений
# тегов каждого из 4 типов.
# В каждом методе генерируется случайное значение нужного типа
# и передаётся для записи в платформу с текущей меткой времени/

import json
import random
import string

from locust import FastHttpUser, task, events

class DataSetUser(FastHttpUser):

    @task
    def set_pack_int(self):
        tags = random.sample(self.ints, self.pack_size)
        payload= {
            "data": []
        }

        for tag in tags:
            payload["data"].append({
                "tagId": tag,
                "data": self.int_pack
            })

        self.client.post("", json=payload)

    @task
    def set_pack_float(self):
        tags = random.sample(self.floats, self.pack_size)
        payload= {
            "data": []
        }

        for tag in tags:
            payload["data"].append({
                "tagId": tag,
                "data": self.float_pack
            })

        self.client.post("", json=payload)

    @task
    def set_pack_str(self):
        tags = random.sample(self.strs, self.pack_size)
        payload= {
            "data": []
        }

        for tag in tags:
            payload["data"].append({
                "tagId": tag,
                "data": self.str_pack
            })

        self.client.post("", json=payload)

    @task
    def set_pack_json(self):
        tags = random.sample(self.jsons, self.pack_size)
        payload = {
            "data": []
        }

        for tag in tags:
            payload["data"].append({
                "tagId": tag,
                "data": self.json_pack
            })

        self.client.post("", json=payload)

    def on_start(self):
        # создадим массив символов для генерации случайных строковых значений
        self.letters = string.ascii_lowercase

        self.rand_int = random.randint(-100, 100)
        self.rand_float = random.uniform(-100, 100)
        self.rand_str = ''.join(random.choice(self.letters) for _ in range(30))
        self.rand_json = {
            "first_field": random.randint(-100, 100),
            "second_field": random.uniform(-100, 100),
            "third_field": ''.join(random.choice(self.letters) for _ in range(30))
        }
        self.pack_size = self.environment.parsed_options.tags_in_pack
        self.vals_in_tag = self.environment.parsed_options.vals_in_tag
        self.int_pack = [[self.rand_int] for _ in range(self.vals_in_tag)]
        self.float_pack = [[self.rand_float] for _ in range(self.vals_in_tag)]
        self.str_pack = [[self.rand_str] for _ in range(self.vals_in_tag)]
        self.json_pack = [[self.rand_json] for _ in range(self.vals_in_tag)]

        # прочитаем из файлов коды тегов каждого типа
        with open("/mnt/locust/tags_in_postgres.json", "r") as f:
            js = json.load(f)
            self.ints = js["0"]
            self.floats = js["1"]
            self.strs = js["2"]
            self.jsons = js["4"]
