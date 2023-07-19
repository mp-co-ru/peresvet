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

        #print(f"data: {json.dumps(data)}")

        # записываем значение тега на текущую метку времени
        self.client.post("/v1/data/", json=data)

    @task
    def set_int_data(self):
        '''
        Запись случайного целого числа в случайно выбранный
        тег из диапазона целочисленных тегов
        '''

        # выбираем случайный индекс тега
        i = random.randrange(len(self.ints))
        self.send_data(self.ints[i], random.randint(-100, 100))

    '''
    @task
    def set_float_data(self):
        i = random.randrange(len(self.floats))
        self.send_data(self.floats[i], random.uniform(-100, 100))

    @task
    def set_str_data(self):
        i = random.randrange(len(self.strs))
        self.send_data(
            self.strs[i],
            ''.join(random.choice(self.letters) for _ in range(30))
        )

    @task
    def set_json_data(self):
        i = random.randrange(len(self.jsons))
        data_item = {
            "first_field": random.randint(-100, 100),
            "second_field": random.uniform(-100, 100),
            "third_field": ''.join(random.choice(self.letters) for _ in range(30))
        }
        self.send_data(self.jsons[i], data_item)
    '''

    def on_start(self):
        # создадим массив символов для генерации случайных строковых значений
        self.letters = string.ascii_lowercase

        # прочитаем из файлов коды тегов каждого типа
        with open("/mnt/locust/tags_in_postgres.json", "r") as f:
            js = json.load(f)
            self.ints = js["0"]
            self.floats = js["1"]
            self.strs = js["2"]
            self.jsons = js["4"]
