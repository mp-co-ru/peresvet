# Скрипт записывает данные за месяц 2023-01
# для всех 4000 тегов (файл tags_in_postgres.json)
# с дискретностью 1 с
import json
import asyncio
import random
import string
import asyncpg as apg
from asyncpg.exceptions import PostgresError
import httpx
import requests
import time
import times as t

async def set_data(tag_value_type, data, conn_pool):
    t1 = time.time()
    q = ""
    null = "NULL"
    for tag in data["data"]:
        q += f'insert into "t_{tag["tagId"]}" (x, y, q) values '

        qa = []
        for item in tag["data"]:
            if tag_value_type in ["1", "2"]:
                y = (null, item["y"])[bool(item["y"])]
            elif tag_value_type == "3":
                y = (null, f"'{item['y']}'")[bool(item["y"])]
            elif tag_value_type == "4":
                y = (null, f"'{json.dumps(item['y'])}'")[bool(item["y"])]
            qa.append(f' ({item["x"]}, {y}, 0)')
        q += ",".join(qa) + ';'

    try:
        async with conn_pool.acquire() as conn:
            async with conn.transaction(isolation='read_committed'):
                res = await conn.execute (q)
    except PostgresError as ex:
        print(f"\tSet data error: {ex}")

    t2 = time.time()
    #print(f"\tSet data: {res}; time: {t2 - t1}")
    return res

    #res = requests.post('http://localhost/data/', json=data)
    #return res.status_code

def chunk(lst, n):
    for x in range(0, len(lst), n):
        e_c = lst[x : n + x]

        yield e_c

async def main():

    start_date = t.ts("2022-12-01T00:00:00+03:00")
    end_date = t.ts("2022-12-31T24:00:00+03:00")

    conn_pool = await apg.create_pool(dsn="postgres://postgres:Peresvet21@localhost:5432/peresvet")

    letters = string.ascii_lowercase

    count_for_each_type = 50

    with open("./tags_in_postgres.json") as f:
        ids = json.load(f)

        for type_code, tags in ids.items():

            if type_code in ['4']:
                continue

            current_count = 0
            tags_worked = []
            for tagId in tags:
                if current_count > count_for_each_type - 1:
                    continue
                current_count += 1

                tags_worked.append (tagId)

                start_cycle = time.time()

                data = {
                    "data": [{
                        "tagId": tagId,
                        "data": []
                    }]
                }

                tasks = []
                print(f"Preparing {type_code} data for {tagId}...")

                for day in range(start_date, end_date, 1000000 * 86400):
                    t1 = time.time()

                    if type_code == '1':
                        data["data"][0]["data"] = [
                            {"x": ts, "y": random.randint(-100, 100)} for ts in range(day, day + 86401 * 1000000, 1000000)
                        ]
                    elif type_code == '2':
                        data["data"][0]["data"] = [
                            {"x": ts, "y": random.uniform(-100, 100)} for ts in range(day, day + 86401 * 1000000, 1000000)
                        ]
                    elif type_code == '3':
                        data["data"][0]["data"] = [
                            {"x": ts, "y": ''.join(random.choice(letters) for i in range(30))} for ts in range(day, day + 86401 * 1000000, 1000000)
                        ]
                    elif type_code == '4':
                        data["data"][0]["data"] = [
                            {"x": ts, "y":
                                {
                                    "first_field": random.randint(-100, 100),
                                    "second_field": random.uniform(-100, 100),
                                    "third_field": ''.join(random.choice(letters) for i in range(30))
                                }
                            } for ts in range(day, day + 86401 * 1000000, 1000000)
                        ]
                    t2 = time.time()
                    # json - слишком большие запросы
                    data_chunked = chunk(data["data"][0]['data'], 1000)
                    for data_chunk in data_chunked:
                        tasks.append(asyncio.create_task(set_data(type_code, {"data": [{"tagId": tagId, "data": data_chunk}]}, conn_pool)))

                chuncked = chunk(tasks, 4)
                for task_group in chuncked:
                    await asyncio.wait(task_group)

                #await asyncio.wait(tasks)

                end_cycle= time.time()

                print(f"Cycle {current_count}; time: {end_cycle - start_cycle}\n")

            with open(f"./src/tags_type_{type_code}", "w") as ft:
                json.dump(tags_worked, ft)

# int stops on d517527a-35b5-103d-8c8a-51d2e9d46f12

asyncio.run(main())
