import json
import random
import string
from datetime import datetime, timedelta

from locust import HttpUser, TaskSet, task, between, events

import time

from uuid import uuid4

#from locust_plugins.users import SocketIOUser

class DataGetHistoryUserVM(HttpUser):

    def on_start(self):
        with open("/mnt/locust/tags_in_vm.json", "r") as f:
            js = json.load(f)
            self.ids = js["0"]
            self.ids += js["1"]
            self.ids += js["2"]
            self.ids += js["4"]

        self.pack_size = self.environment.parsed_options.tags_in_pack
        self.start_date = datetime.utcfromtimestamp(1690454451).date()
        self.end_date = datetime.utcfromtimestamp(1690971801).date() - timedelta(days=1)

    @task
    def get_data(self):
        tags = random.sample(self.ids, self.pack_size)
        delta = self.end_date - self.start_date
        random_date = self.start_date + timedelta(days=random.randint(0, delta.days))
        start = random_date.isoformat()
        end = (random_date + timedelta(days=1)).isoformat()

        data = {
        "tagId": tags,
        "start": start,
        "finish": end 
        }

        self.client.get("", json=data)
