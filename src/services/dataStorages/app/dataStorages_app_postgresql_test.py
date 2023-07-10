import sys
from fastapi import FastAPI

sys.path.append(".")

import asyncpg as apg
from asyncpg.exceptions import PostgresError

class MyApp(FastAPI):

    def __init__(self,  *args, **kwargs):
        if kwargs.get("on_startup"):
            kwargs.append(self.on_startup)
        else:
            kwargs["on_startup"] = [self.on_startup]

        super().__init__(*args, **kwargs)

    async def on_startup(self) -> None:
        try:
            await apg.create_pool(
                dsn="postgres://postgres:Peresvet21@localhost:5432/peresvet"
            )
            print("connected")
        except Exception as ex:
            print(f"error: {ex}")


app = MyApp(title="MyApp")
