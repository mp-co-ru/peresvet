import asyncio
from websockets import connect
from random import randrange, uniform
import time as t
import json

CN_CYCLE_COUNT = 1000
CN_URI = "ws://localhost/ws/data"

CN_CONNECTORS = 100
CN_TAGS_IN_CONNECTOR = 50
CN_SCREENS = 50
CN_CONNECTOR_FREQUENCY = 1000 # ms
CN_SCREEN_FREQUENCY = 1000

class User:
    def __init__(self, int_ids, float_ids, str_ids, json_ids):
        self.ints = int_ids
        self.floats = float_ids
        self.strs = str_ids
        self.jsons = json_ids

class SetUser(User):
    async def as_connector(self, tags_in_source: int, frequency: int):
        # tags_in_source: количество тегов, с которыми работает коннектор
        # frequency: частота записи данных в платформу, в мс

        async with connect(CN_URI) as websocket:
            # один раз выбираем начальный индекс диапазона тегов, с которыми работаем
            i = randrange(len(self.floats) - tags_in_source + 1)

            while True:
                full_time = 0
                status = 204
                for _ in range(CN_CYCLE_COUNT):

                    body = json.dumps({
                        "post": {
                            "data": [
                                {
                                    "tagId": self.floats[k],
                                    "data": [
                                        {
                                            "y": uniform(-100, 100)
                                        }
                                    ]
                                } for k in range(i, i+tags_in_source)
                            ]
                        }
                    })

                    t1 = t.time()
                    await websocket.send(body)
                    res = await websocket.recv()
                    t2 = t.time()
                    full_time += t2 - t1
                    if json.loads(res)["status_code"] != 204:
                        status = 204

                    if (frequency / 1000) > (t2 - t1):
                        await asyncio.sleep((frequency / 1000) - t2 - t1)

                print(f"Connector time: {full_time / CN_CYCLE_COUNT}; status: {status}")

class GetUser(User):

    async def as_screen(self, int_tags_count: int, float_tags_count: int,
        str_tags_count: int, json_tags_count: int, frequency: int):

        async with connect(CN_URI) as websocket:
            i_ind = randrange(len(self.ints) - int_tags_count + 1)
            f_ind = randrange(len(self.floats) - float_tags_count + 1)
            s_ind = randrange(len(self.strs) - str_tags_count + 1)
            j_ind = randrange(len(self.jsons) - json_tags_count + 1)

            while True:
                full_time = 0
                status = 204
                for _ in range(CN_CYCLE_COUNT):
                    tags = [self.ints[k] for k in range(i_ind, i_ind+int_tags_count)]
                    tags.extend(
                        [self.floats[k] for k in range(f_ind, f_ind+float_tags_count)]
                    )
                    tags.extend(
                        [self.strs[k] for k in range(s_ind, s_ind+str_tags_count)]
                    )
                    tags.extend(
                        [self.jsons[k] for k in range(j_ind, j_ind+json_tags_count)]
                    )

                    body = json.dumps({
                        "get": {
                            "tagId": tags
                        }
                    })

                    t1 = t.time()
                    await websocket.send(body)
                    res = await websocket.recv()
                    t2 = t.time()
                    full_time += t2 - t1
                    if not json.loads(res).get("data"):
                        status = 400

                    if (frequency / 1000) > (t2 - t1):
                        await asyncio.sleep((frequency / 1000) - t2 - t1)
                    print(".", end="")

                print(f"Screen time: {full_time / CN_CYCLE_COUNT}; status: {status}")

async def main():
    # создадим реальную картину:
    # 100 коннекторов по 50 тегов,
    # 15 экранов по 20 тегов

    with open("tags_in_postgres.json", "r") as f:
        ids = json.load(f)

    connectors = [SetUser(ids['1'], ids['2'], ids['3'], ids['4']) for _ in range(CN_CONNECTORS)]
    screens = [GetUser(ids['1'], ids['2'], ids['3'], ids['4']) for _ in range(CN_SCREENS)]
    '''
    tasks = [asyncio.create_task(
        connectors[k].as_connector(CN_TAGS_IN_CONNECTOR, CN_CONNECTOR_FREQUENCY)
    ) for k in range(len(connectors))]

    tasks.extend(
        [
            asyncio.create_task(
                screens[k].as_screen(10, 10, 2, 4, 1000)
            ) for k in range(len(screens))
        ]
    )
    '''
    tasks = [asyncio.create_task(
        screens[k].as_screen(10, 10, 2, 4, 1000)
    ) for k in range(len(screens))]
    await asyncio.wait(tasks)

asyncio.run(main())
