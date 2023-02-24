import json
import asyncio
import asyncpg as apg
import time

async def main():

    with open("./tags_in_postgres.json") as f:
        ids = json.load(f)

    try:
        conn_pool = await apg.create_pool(dsn="postgres://postgres:Peresvet21@localhost:5432/peresvet")
        async with conn_pool.acquire() as conn:

            for tag_type, tags in ids.items():
                #if tag_type in ["4"]:
                #    continue

                q = "truncate "
                sub_q = []

                for tag_id in tags:
                    sub_q.append(f'"t_{tag_id}"')
                q += ','.join(sub_q)
                q += "  RESTART IDENTITY;"

                t1 = time.time()
                print(f"Start delete...")
                await conn.execute(q)
                print(f"... {time.time() - t1} deleted.")

        print ("\nВсё")

    except Exception as ex:
        print(f"Error: {ex}")


asyncio.run(main())
