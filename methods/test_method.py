import asyncio
from patio import Registry, AsyncExecutor
from patio_rabbitmq import RabbitMQBroker
import aiormq
import json
from time import sleep

rpc = Registry(project="methods_app", auto_naming=False)

i = 0

@rpc("heat")
async def calc_temp(T: dict) -> int:
    cur_T = I["data"][0]["data"][0][0]
    if cur_T >= 60:
        return 1
    else:
        return 0

@rpc("power")
async def calc_power(I: dict, U: dict) -> float:
    """Метод возвращает произведение двух параметров.

    """
    #print(f"I: {json.dumps(I, indent=4)}")
    #print(f"U: {json.dumps(U, indent=4)}")

    global i

    i += 1

    print(i)

    cur_I = I["data"][0]["data"][0][0]
    cur_U = U["data"][0]["data"][0][0]

    if cur_I == None or cur_U == None:
        return 0
    
    return cur_I * cur_U

async def main():
    """Главная функция - запуск программы
    """
    async with AsyncExecutor(rpc, max_workers=16) as executor:
        while True:
            try:
                async with RabbitMQBroker(
                        # измените параметры подключения к RabbitMQ
                        executor, amqp_url="amqp://prs:Peresvet21@localhost/",
                ) as broker:
                    print("Соединение с брокером...")
                    await broker.join()
                    print("Выполнено.")
            except KeyboardInterrupt:
                print("Работа прервана.")
                return
            except (OSError, aiormq.exceptions.AMQPConnectionError) as ex:
                print(f"Ошибка выполнения программы: {ex}")
                sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
