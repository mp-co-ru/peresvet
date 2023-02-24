import asyncio
from websockets import connect
from random import randrange, uniform
import time as t
import json

async def main():
    with open("tags_type_1.json", "r") as f:
        int_ids = json.load(f)

    async with connect("ws://localhost/ws/data") as websocket:

        while True:
            full_time = 0
            for _ in range(1000):
                i = randrange(len(int_ids))
                #i = len(int_ids) // 2
                body = json.dumps({
                    "get": {
                        #"tagId": [int_ids[k] for k in range(i - 10)],
                        "tagId": int_ids[i],
                        "start": "2022-12-10T00:00:00+03:00",
                        "finish": "2022-12-10T00:10:00+03:00",
                        #"format": True
                    }
                })

                t1 = t.time()
                await websocket.send(body)
                await websocket.recv()
                full_time += t.time() - t1
            print(f"Time: {full_time / 1000}")

asyncio.run(main())
