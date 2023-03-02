import json
import random
import string
import time
from uuid import uuid4

from locust import FastHttpUser, task, events, constant_throughput
from locust.runners import MasterRunner

import times

CN_INT_TAGS_IN_CONNECTOR = 25
CN_FLOAT_TAGS_IN_CONNECTOR = 25
CN_CONN_FREQUENCY = 1000 # ms
CN_CONNECTORS = 100

CN_SCREENS = 50
CN_SCREEN_FREQUENCY = 1000 # ms
CN_INT_TAGS_IN_SCREEN = 10
CN_FLOAT_TAGS_IN_SCREEN = 10
CN_STR_TAGS_IN_SCREEN = 4
CN_JSON_TAGS_IN_SCREEN = 4

class Data:
    int_ids = None
    float_ids = None
    str_ids = None
    json_ids = None

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        return

    with open("/mnt/locust/tags_in_postgres.json", "r") as f:
        js = json.load(f)
        Data.int_ids = js["1"]
        Data.float_ids = js["2"]
        Data.str_ids = js["3"]
        Data.json_ids = js["4"]

class Connector(FastHttpUser):

    fixed_count = CN_CONNECTORS
    wait_time = constant_throughput(1)

    def on_start(self):
        self.int_ids = random.sample(Data.int_ids, k=CN_INT_TAGS_IN_CONNECTOR)
        self.float_ids = random.sample(Data.float_ids, k=CN_FLOAT_TAGS_IN_CONNECTOR)

    '''
    def wait_time(self):
        if (CN_CONN_FREQUENCY / 1000) > self.ts_delta:
            return (CN_CONN_FREQUENCY / 1000) - self.ts_delta
    '''

    @task
    def set_data(self):
        #t1 = time.time()
        data = {
            "data": [
                {
                    "tagId": tag,
                    "data": [
                        {
                            "y": random.randrange(-100, 100),
                            "x": times.ts()
                        }
                    ]
                } for tag in self.int_ids
            ]
        }
        data["data"].extend(
            [
                {
                    "tagId": tag,
                    "data": [
                        {
                            "y": random.uniform(-100, 100),
                            "x": times.ts()
                        }
                    ]
                } for tag in self.float_ids
            ]
        )
        self.client.post("/data/", json=data)

        #self.ts_delta = time.time() - t1

class Screen(FastHttpUser):

    fixed_count = CN_SCREENS
    wait_time = constant_throughput(1)

    def on_start(self):

        ids = random.sample(Data.int_ids, k=CN_INT_TAGS_IN_SCREEN)
        ids.extend (
            random.sample(Data.float_ids, k=CN_FLOAT_TAGS_IN_SCREEN)
        )
        ids.extend (
            random.sample(Data.str_ids, k=CN_STR_TAGS_IN_SCREEN)
        )
        ids.extend(
            random.sample(Data.json_ids, k=CN_JSON_TAGS_IN_SCREEN)
        )
        self.payload = {
            "tagId": ids
        }

    @task
    def get_data(self):
        self.client.get("/data/", json=self.payload)
