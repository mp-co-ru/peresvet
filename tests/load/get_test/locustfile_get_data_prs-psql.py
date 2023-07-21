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
        with open("/mnt/locust/tags_in_postgres.json", "r") as f:
            js = json.load(f)
            self.ids = js["0"]
            self.ids += js["1"]
            self.ids += js["2"]
            self.ids += js["4"]

    @task
    def get_data(self):
        i = random.randrange(len(self.ids))
        data = {
            "tagId": self.ids[i]
        }

        self.client.get("/v1/data/", json=data)
