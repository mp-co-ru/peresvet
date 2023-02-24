# Скрипт записывает данные за месяц 2023-01
# для всех 4000 тегов (файл tags_in_postgres.json)
# с дискретностью 1 с
import json
import asyncio
import random
import string
import asyncpg as apg
import time
import httpx
import requests
import times as t

async def set_data(data):
    t1 = time.time()
    async with httpx.AsyncClient() as client:
        res = await client.post('http://localhost/data/', json=data)
    t2 = time.time()
    print(f"\tSet data: {res.status_code}; {res.text}; {t2-t1}")
    return res.status_code

    #res = requests.post('http://localhost/data/', json=data)
    #return res.status_code

async def main():

    start_date = t.ts("2022-12-01T00:00:00+03:00")
    end_date = t.ts("2022-12-31T24:00:00+03:00")

    int_data = []
    float_data = []
    str_data = []
    json_data = []

    with open("./tags_in_postgres.json") as f:
        ids = json.load(f)

        for type_code, tags in ids.items():
            if type_code == "1":
                data = int_data
            elif type_code == "2":
                data = float_data
            elif type_code == "3":
                data = str_data
            elif type_code == "4":
                data = json_data

            for tagId in tags:
                data.append(
                    {
                        "tagId": tagId,
                        "data": [
                            {
                                "x": None,
                                "y": None
                            }
                        ]
                    }
                )

    letters = string.ascii_lowercase
    for ts in range(start_date, end_date + 1000000, 1000000):

        start_cycle = time.time()

        print(f"Time: {t.int_to_local_timestamp(ts)}")

        print("\tPreparing data...")
        t1 = time.time()
        for tag_item in int_data:
            tag_item["data"][0]["x"] = ts
            tag_item["data"][0]["y"] = random.randint(-100, 100)
        t2 = time.time()
        print(f"\tint:{t2-t1}")

        t1 = time.time()
        for tag_item in float_data:
            tag_item["data"][0]["x"] = ts
            tag_item["data"][0]["y"] = random.uniform(-100, 100)
        t2 = time.time()
        print(f"\tfloat:{t2-t1}")

        t1 = time.time()
        for tag_item in str_data:
            tag_item["data"][0]["x"] = ts
            tag_item["data"][0]["y"] = ''.join(random.choice(letters) for i in range(30))
        t2 = time.time()
        print(f"\tstr:{t2-t1}")

        t1 = time.time()
        for tag_item in json_data:
            tag_item["data"][0]["x"] = ts
            tag_item["data"][0]["y"] = {
                "first_field": random.randint(-100, 100),
                "second_field": random.uniform(-100, 100),
                "third_field": ''.join(random.choice(letters) for i in range(30))
            }
        t2 = time.time()
        print(f"\tdict:{t2-t1}")


        '''
        all_data = {
            "data": int_data
        }
        all_data["data"].extend(float_data)
        all_data["data"].extend(str_data)
        all_data["data"].extend(json_data)


        res = set_data({
            "data": all_data
        })
        t2 = time.time()
        print(f"\tSet int data: {res}; time:{t2-t1}")
        '''

        with open("./float_data.json", "w") as f:
            json.dump(float_data, f, indent=4)
        tasks = [
            asyncio.create_task(set_data({"data": int_data})),
            asyncio.create_task(set_data({"data": float_data})),
            asyncio.create_task(set_data({"data": str_data})),
            asyncio.create_task(set_data({"data": json_data}))
        ]
        await asyncio.wait(tasks)

        '''
        t1 = time.time()
        res = set_data({
            "data": int_data
        })
        t2 = time.time()


        print(f"\tSet int data: {res}; time:{t2-t1}")

        t1 = time.time()
        res = set_data({
            "data": float_data
        })
        t2 = time.time()
        print(f"\tSet float data: {res}; time:{t2-t1}")

        t1 = time.time()
        res = set_data({
            "data": str_data
        })
        t2 = time.time()
        print(f"\tSet str data: {res}; time:{t2-t1}")

        t1 = time.time()
        res = set_data({
            "data": json_data
        })
        t2 = time.time()
        print(f"\tSet json data: {res}; time:{t2-t1}")
        '''

        end_cycle = time.time()

        print(f"Cycle time: {end_cycle - start_cycle}")




asyncio.run(main())
