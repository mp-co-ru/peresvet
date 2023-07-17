import asyncio
import aiohttp
import requests
import time
import json

import sys
from loguru import logger

logger.remove()
logger.add(sys.stdout, colorize= True, format="<green>{time}</green> | <level>{level} :: {message}</level>")


url_ds = "http://localhost:82/v1/dataStorages"
url_tags = "http://localhost:80/v1/tags"

async def main():

    tag_templates = {
        0: "i",
        1: "f",
        2: "s",
        4: "j"
    }

    tag_count_for_every_type = 1250

    tasks = []

    tags = {
        0: [],
        1: [],
        2: [],
        4: []
    }

    def chunk(lst, n):
        for x in range(0, len(lst), n):
            e_c = lst[x : n + x]

            yield e_c

    async def create(session: aiohttp.ClientSession, data: dict, ds_id: str):
        t1 = time.time()
        async with session.post(url_tags, json=data) as res:
            t2 = time.time()
            tag_id = None
            if res.status == 201:
                res_j = await res.json()
                tag_id = res_j["id"]
                tags[data['attributes']["prsValueTypeCode"]].append(tag_id)

                async with session.put(url_ds, json={
                    "id": ds_id,
                    "linkTags": [{"tagId": tag_id}]
                }) as _:
                    t3 = time.time()

                    logger.info(f"Тег {tag_id}. Создание: {t2 - t1}; привязка: {t3 - t2}")
            else:
                logger.error(f"Ошибка создания тега {data['attributes']['cn']}: {res}")

        return res

    """
    logger.info("Create database...")
    payload = {
        "attributes": {
            "cn": "psql",
            "prsJsonConfigString": '{"dsn": "postgres://postgres:Peresvet21@psql_load_tests/peresvet"}'
        }
    }
    t1 = time.time()
    res = requests.post(url_ds, json=payload)
    if res.status_code != 201:
        logger.error(f"Ошибка создания базы данных. {res}")
        return
    else:
        logger.info(f"Database created. {time.time() - t1}")
    """
    #ds_id = res.json()["id"]
    ds_id = "ac258e2a-b8f7-103d-9a07-6fcde61b9a51"

    async with aiohttp.ClientSession() as session:
        for tag_type, name_temp in tag_templates.items():

            for i in range(tag_count_for_every_type):
                name = f"{name_temp}_tag_{i+1}"
                body = {
                    "attributes": {
                        "cn": name,
                        "prsValueTypeCode": tag_type
                    }
                }
                await create(session, body, ds_id)

    with open('tags_in_postgres.json', 'w', encoding="utf-8") as f:
        f.write(json.dumps(tags, indent=4))

asyncio.run(main())
