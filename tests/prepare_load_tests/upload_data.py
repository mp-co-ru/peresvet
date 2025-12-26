import asyncio
import json
import asyncpg as apg
import random
import string
from times import ts
import time

async def main():
    pool = await apg.create_pool(dsn="postgres://postgres:Peresvet21@localhost/peresvet")

    f = open("tags_in_postgres_100.json", "r")
    all_ids = json.load(f)

    def int_val() -> int:
        return random.randint(-100, 100)

    def float_val() -> float:
        return random.uniform(-100, 100)

    def str_val() -> str:
        return 'qwertyuioplkjhgfdsazxcvbnm'

    def dict_val() -> str:
        return json.dumps({
            "first_field": random.randint(-100, 100),
            "second_field": random.uniform(-100, 100),
            "third_field": 'qwertyuioplkjhgfdsazxcvbnm'
        })

    start = ts("2023-07-01T00:00:00+03:00")
    finish = ts("2023-08-01T00:00:00+03:00")

    async with pool.acquire() as conn:
        for code, ids in all_ids.items():
            func = None
            match code:
                case "0": func = int_val
                case "1": func = float_val
                case "2": func = str_val
                case "4": func = dict_val

            for id in ids:
                print(f"Подготовка данных для тега {id}...", end=" ")
                t1 = time.time()
                data = [(func(), x*1000000) for x in range(int(start/1000000), int(finish/1000000) + 1)]
                print(time.time() - t1)

                t1 = time.time()
                print(f"Запись данных...", end=" ")
                await conn.copy_records_to_table(
                                f"t_{id}",
                                records=data,
                                columns=('y', 'x'))
                print(f"{time.time() - t1}\n")

    print("Всё.")

asyncio.run(main())
