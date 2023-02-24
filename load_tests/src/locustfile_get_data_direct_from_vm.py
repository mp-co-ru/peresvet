import json
import random
import string
from uuid import uuid4

from locust import HttpUser, TaskSet, task, between, events

class DataSetUser(HttpUser):
    #wait_time = between(0.5, 1)

    @task
    def set_data_data(self):

        data = {
            "metric": "Ia",
            "tags": {
                "workshop": "Main", "area": "Area_3", "machine": "AC_CLASSIC_V2_13"
            },
            "value": random.uniform(-100, 100)
        }


        self.client.post("http://vm:4242/api/put", json=data)

    '''
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
    '''

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




class DataGetUser(HttpUser):

    def on_start(self):
        with open("/mnt/locust/tags_type_1.json", "r") as f:
            self.int_ids = json.load(f)

        with open("/mnt/locust/tags_type_2.json", "r") as f:
            self.float_ids = json.load(f)

        with open("/mnt/locust/tags_type_3.json", "r") as f:
            self.str_ids = json.load(f)

        with open("/mnt/locust/tags_type_4.json", "r") as f:
            self.json_ids = json.load(f)

    @task
    def get_data(self):
        i = randrange(len(self.int_ids))
        data = {
            "tagId": self.int_ids[i]
        }

        self.client.get("/data/", json=data)
