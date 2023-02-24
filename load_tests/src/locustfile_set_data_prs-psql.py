import json
import random
import string

from locust import HttpUser, TaskSet, task, between, events

from websocket import create_connection
import time

from uuid import uuid4

#from locust_plugins.users import SocketIOUser

class DataSetUser(HttpUser):
    #wait_time = between(0.5, 1)

    @task
    def set_int_data(self):

        i = random.randrange(len(self.int_ids))
        data_item = {}
        data_item["y"] = random.randint(-100, 100)

        data = {
            "data": [
                {
                    "tagId": self.int_ids[i],
                    "data": [
                        data_item
                    ]
                }
            ]
        }
        '''
        # случайные числа для всех целочисленных тегов. запись одним пакетом
        data = {
            "data": [
                {
                    "tagId": self.int_ids[i],
                    "data": [
                        {"y": random.randint(-100, 100)}
                    ]
                }
                for i in range(len(self.int_ids))
            ]
        }
        '''

        self.client.post("/data/", json=data)

    @task
    def set_float_data(self):
        i = random.randrange(len(self.float_ids))
        data_item = {}
        data_item["y"] = random.uniform(-100, 100)

        data = {
            "data": [
                {
                    "tagId": self.float_ids[i],
                    "data": [
                        data_item
                    ]
                }
            ]
        }

        self.client.post("/data/", json=data)

    @task
    def set_str_data(self):
        i = random.randrange(len(self.str_ids))
        data_item = {}
        data_item["y"] = ''.join(random.choice(self.letters) for _ in range(30))

        data = {
            "data": [
                {
                    "tagId": self.str_ids[i],
                    "data": [
                        data_item
                    ]
                }
            ]
        }

        self.client.post("/data/", json=data)

    @task
    def set_json_data(self):
        i = random.randrange(len(self.json_ids))
        data_item = {}
        data_item["y"] = {
            "first_field": random.randint(-100, 100),
            "second_field": random.uniform(-100, 100),
            "third_field": ''.join(random.choice(self.letters) for _ in range(30))
        }
        data = {
            "data": [
                {
                    "tagId": self.json_ids[i],
                    "data": [
                        data_item
                    ]
                }
            ]
        }

        self.client.post("/data/", json=data)


    def on_start(self):
        self.letters = string.ascii_lowercase
        with open("/mnt/locust/tags_type_1.json", "r") as f:
            self.int_ids = json.load(f)
        with open("/mnt/locust/tags_type_2.json", "r") as f:
            self.float_ids = json.load(f)
        with open("/mnt/locust/tags_type_3.json", "r") as f:
            self.str_ids = json.load(f)
        with open("/mnt/locust/tags_type_4.json", "r") as f:
            self.json_ids = json.load(f)
