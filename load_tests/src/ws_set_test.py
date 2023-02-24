import asyncio
from websockets import connect
from random import randrange, uniform
import time as t
import json

class SetUser:

    def __init__(self):
        with open("./tags_type_1.json", "r") as f:
            self.int_ids = json.load(f)
        with open("./tags_type_2.json", "r") as f:
            self.float_ids = json.load(f)

    async def as_connector(self):
        length = 50
        async with connect("ws://localhost/ws/data") as websocket:

            while True:
                full_time = 0
                for _ in range(1000):
                    #i = randrange(len(self.float_ids))
                    #i = len(int_ids) // 2
                    i = randrange(len(self.float_ids) - length + 1)
                    body = json.dumps({
                        "post": {
                            "data": [
                                {
                                    "tagId": self.float_ids[k],
                                    "data": [
                                        {
                                            "y": uniform(-100, 100)
                                        }
                                    ]
                                } for k in range(i, i+length)
                            ]
                        }
                    })

                    t1 = t.time()
                    await websocket.send(body)
                    await websocket.recv()
                    full_time += t.time() - t1
                print(f"Time: {full_time / 1000}")

    async def many_float(self):
        length = 50
        async with connect("ws://localhost/ws/data") as websocket:

            while True:
                full_time = 0
                status = 204
                for _ in range(1000):
                    i = randrange(len(self.float_ids))
                    #i = len(self.int_ids) // 2
                    #i = randrange(len(self.float_ids) - length + 1)
                    body = json.dumps({
                        "post": {
                            "data": [
                                {
                                    "tagId": self.float_ids[i],
                                    "data": [
                                        {
                                            "y": uniform(-100, 100)
                                        } for _ in range(length)
                                    ]
                                }
                            ]
                        }
                    })

                    t1 = t.time()
                    await websocket.send(body)
                    res = await websocket.recv()
                    full_time += t.time() - t1
                    if json.loads(res)["status_code"] != 204:
                        status = 204
                print(f"Time: {full_time / 1000}; status: {status}")

    async def single_int_set(self):
        async with connect("ws://localhost/ws/data") as websocket:

            while True:
                full_time = 0
                for _ in range(1000):
                    i = randrange(len(self.int_ids))
                    #i = len(int_ids) // 2
                    body = json.dumps({
                        "post": {
                            "data": [
                                {
                                    "tagId": self.int_ids[i],
                                    "data": [
                                        {
                                            "y": randrange(-100, 100)
                                        }
                                    ]
                                }
                            ]
                        }
                    })

                    t1 = t.time()
                    await websocket.send(body)
                    await websocket.recv()
                    full_time += t.time() - t1
                print(f"Time: {full_time / 1000}")


async def main():

    user = SetUser()
    #await user.as_connector()
    await user.many_float()

asyncio.run(main())
