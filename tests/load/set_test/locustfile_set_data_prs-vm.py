# Модуль записи данных для нагрузочного тестирования.
# Класс DataSetUser имеет 4 функции для записи значений
# тегов каждого из 4 типов.
# В каждом методе генерируется случайное значение нужного типа
# и передаётся для записи в платформу с текущей меткой времени/

import json
import random
import string

from locust import FastHttpUser, task, events

class DataSetUserVM(FastHttpUser):

    '''
    def send_data(self, tag_id, value):
        # формируем пакет данных для записи
        data = {
            "data": [
                {
                    "tagId": tag_id,
                    "data": [
                        {
                            "y": value
                        }
                    ]
                }
            ]
        }

        #print(f"data: {json.dumps(data)}")

        # записываем значение тега на текущую метку времени
        self.client.post("/v1/data/", json=data)

    @task
    def set_int_data(self):

        # выбираем случайный индекс тега
        i = random.randrange(len(self.ints))
        self.send_data(self.ints[i], self.rand_int)

    @task
    def set_float_data(self):
        i = random.randrange(len(self.floats))
        self.send_data(self.floats[i], self.rand_float)

    @task
    def set_str_data(self):
        i = random.randrange(len(self.strs))
        self.send_data(self.strs[i], self.rand_str)

    @task
    def set_json_data(self):
        i = random.randrange(len(self.jsons))
        self.send_data(self.jsons[i], self.rand_json)
    '''

    @task
    def set_pack_int(self):
        tags = random.sample(self.ints, self.pack_size)
        payload= {
            "action": "set",
            "data": {
                "data": []
            }
        }
        
        for tag in tags:
            data = []
            for _ in range(self.vals_in_tag):
                data.append([self.rand_int])
            tag_item = {
                "tagId": tag,
                "data": data
            }
            payload["data"]["data"].append(tag_item)
        self.client.post("", json=payload)

    @task
    def set_pack_float(self):
        tags = random.sample(self.floats, self.pack_size)
        payload = {
            "action": "set",
            "data": {
                "data": []
            }
        }
        for tag in tags:
            data = []
            for _ in range(self.vals_in_tag):
                data.append([self.rand_float])
            tag_item = {
                "tagId": tag,
                "data": data
            }
            payload["data"]["data"].append(tag_item)
        self.client.post("", json=payload)

    @task
    def set_pack_str(self):
        tags = random.sample(self.strs, self.pack_size)
        payload= {
            "action": "set",
            "data": {
                "data": []
            }
        }
        for tag in tags:
            data = []
            for _ in range(self.vals_in_tag):
                data.append([self.rand_str])
            tag_item = {
                "tagId": tag,
                "data": data
            }
            payload["data"]["data"].append(tag_item)
        self.client.post("", json=payload)

    @task
    def set_pack_json(self):
        tags = random.sample(self.jsons, self.pack_size)
        payload= {
            "action": "set",
            "data": {
                "data": []
            }
        }
        for tag in tags:
            data = []
            for _ in range(self.vals_in_tag):
                data.append([self.rand_json])
            tag_item = {
                "tagId": tag,
                "data": data
            }
            payload["data"]["data"].append(tag_item)
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

        # прочитаем из файлов коды тегов каждого типа
        with open("/mnt/locust/tags_in_vm.json", "r") as f:
            js = json.load(f)
            self.ints = js["0"]
            self.floats = js["1"]
            self.strs = js["2"]
            self.jsons = js["4"]
