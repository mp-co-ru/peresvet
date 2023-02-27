# Модуль записи данных для нагрузочного тестирования.
# Класс DataSetUser имеет 4 функции для записи значений
# тегов каждого из 4 типов.
# В каждом методе генерируется случайное значение нужного типа
# и передаётся для записи в платформу с текущей меткой времени/

import json
import random
import string

from locust import HttpUser, task

class DataSetUser(HttpUser):

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

        # записываем значение тега на текущую метку времени
        self.client.post("/data/", json=data)

    @task
    def set_int_data(self):
        '''
        Запись случайного целого числа в случайно выбранный
        тег из диапазона целочисленных тегов
        '''

        # выбираем случайный индекс тега
        i = random.randrange(len(self.int_ids))
        self.send_data(self.int_ids[i], random.randint(-100, 100))

    @task
    def set_float_data(self):
        i = random.randrange(len(self.float_ids))
        self.send_data(self.str_ids[i], random.uniform(-100, 100))

    @task
    def set_str_data(self):
        i = random.randrange(len(self.str_ids))
        self.send_data(
            self.str_ids[i],
            ''.join(random.choice(self.letters) for _ in range(30))
        )

    @task
    def set_json_data(self):
        i = random.randrange(len(self.json_ids))
        data_item = {
            "first_field": random.randint(-100, 100),
            "second_field": random.uniform(-100, 100),
            "third_field": ''.join(random.choice(self.letters) for _ in range(30))
        }
        self.send_data(self.json_ids[i], data_item)


    def on_start(self):
        # создадим массив символов для генерации случайных строковых значений
        self.letters = string.ascii_lowercase

        # прочитаем из файлов коды тегов каждого типа
        with open("/mnt/locust/tags_type_1.json", "r") as f:
            self.int_ids = json.load(f)
        with open("/mnt/locust/tags_type_2.json", "r") as f:
            self.float_ids = json.load(f)
        with open("/mnt/locust/tags_type_3.json", "r") as f:
            self.str_ids = json.load(f)
        with open("/mnt/locust/tags_type_4.json", "r") as f:
            self.json_ids = json.load(f)
