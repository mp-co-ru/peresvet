import json
import asyncio
import asyncpg as apg
import time

async def main():

    conn = await apg.connect(user='postgres', password='Peresvet21',
                                 database='peresvet', host='127.0.0.1')

    with open("./tags_in_postgres.json") as f:
        ids = json.load(f)


        for type_code, tags in ids.items():
            if type_code == "1":
                s_type = "bigint"
            elif type_code == "2":
                s_type = "double precision"
            elif type_code == "3":
                s_type = "text"
            elif type_code == "4":
                s_type = "jsonb"

            print("s_type:")

            for tag_id in tags:

                t1 = time.time()
                # Запрос на создание таблицы в РСУБД
                query = (f'CREATE TABLE public."t_{tag_id}" ('
                    f'"id" serial primary key,'
                    f'"x" bigint NOT NULL,'
                    f'"y" {s_type},'
                    f'"q" int);'
                    # Создание индекса на поле "метка времени" ("ts")
                    f'CREATE INDEX "t_{tag_id}_idx" ON public."t_{tag_id}" '
                    f'USING btree ("x");')

                if type_code == 4:
                    query += (f'CREATE INDEX "t_{tag_id}_json__idx" ON public."t_{tag_id}" '
                                'USING gin ("y" jsonb_path_ops);')

                await conn.execute(query)
                t2 = time.time()

                print(f"\ttag: {tag_id}; {t2-t1}")

    await conn.close()


asyncio.run(main())
