import httpx
import asyncio
import requests
import time
import json

async def main():

    tag_templates = {
        #1: "i",
        #2: "f",
        3: "s",
        4: "j"
    }

    tag_count_for_every_type = 1000

    tasks = []

    tags = {
        1: [],
        2: [],
        3: [],
        4: []
    }

    def chunk(lst, n):
        for x in range(0, len(lst), n):
            e_c = lst[x : n + x]

            yield e_c

    async def create(data: dict):
        t1 = time.time()
        #async with httpx.AsyncClient() as client:
        res = requests.post("http://localhost/tags/", json=data)
        t2 = time.time()

        print(f'{data["attributes"]["cn"]:} {res.status_code} time: {t2 - t1}')

        if res.status_code == 201:
            tags[data['attributes']["prsValueTypeCode"]].append(res.json()["id"])

        return res

    print("Creating tasks...")
    t1 = time.time()
    for tag_type, name_temp in tag_templates.items():

        for i in range(tag_count_for_every_type):
            name = f"{name_temp}_tag_{i+1}"
            body = {
                "attributes": {
                    "cn": name,
                    "prsValueTypeCode": tag_type
                }
            }
            tasks.append(asyncio.create_task(create(body)))
    t2 = time.time()
    print(f"Tasks created: {t2 - t1}")
    chuncked = chunk(tasks, 4)
    for task_group in chuncked:
        done, _ = await asyncio.wait(task_group)

    with open('tags_in_postgres.json', 'w', encoding="utf-8") as f:
        f.write(json.dumps(tags, indent=4))

asyncio.run(main())
