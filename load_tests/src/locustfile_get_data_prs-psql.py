import json
import random
import string

from locust import HttpUser, TaskSet, task, between, events

from websocket import create_connection
import time

from uuid import uuid4

#from locust_plugins.users import SocketIOUser

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
        i = random.randrange(len(self.int_ids))
        data = {
            "tagId": self.int_ids[i]
        }

        self.client.get("/data/", json=data)
