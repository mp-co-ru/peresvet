import asyncio
import json
import asyncpg as apg
import random
import string
from times import ts
import time
import hashlib
import os

chars = [
  'q','w','e','r','t','y','u','i','o','p','a','s','d','f','g','h','j','k','l','z','x','c','v','b','n','m'
]
t1 = time.time()
print(hashlib.md5(random.choice(chars).encode()))
print(f"{time.time() - t1}")
'''
async def main():
    pool = await apg.create_pool(dsn="postgres://postgres:Peresvet21@localhost/peresvet")

    f = open("tags_in_postgres_to_clear.json", "r")
    all_ids = json.load(f)

    async with pool.acquire() as conn:
        for _, ids in all_ids.items():
            for id in ids:
                print(f"Удаление данных тега {id}...", end=" ")
                t1 = time.time()
                await conn.execute(f'delete from "t_{id}";')
                print(f"{time.time() - t1}")

    print("Всё.")

asyncio.run(main())
'''
