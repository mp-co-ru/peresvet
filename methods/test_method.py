import asyncio
from patio import Registry, AsyncExecutor
from patio_rabbitmq import RabbitMQBroker
import aiormq
from time import sleep
from times import ts, int_to_local_timestamp

rpc = Registry(project="methods_app", auto_naming=False)

@rpc("power")
async def calc_power(I: dict, U: dict) -> float:
    """Метод возвращает произведение двух параметров.

    """

    print(f"{int_to_local_timestamp(ts())} :: power")

    # data point format: [x, y, q] (or [y] / [x, y] in some cases)
    pI = I["data"][0]["data"][0]
    pU = U["data"][0]["data"][0]
    cur_I = (pI[0], pI[1])[len(pI) >= 2]
    cur_U = (pU[0], pU[1])[len(pU) >= 2]

    if cur_I == None or cur_U == None:
        return 0

    return cur_I * cur_U

@rpc("current")
async def current(I: dict) -> float:
    """Метод увеличивает значение тока.

    """
    print(f"{int_to_local_timestamp(ts())} :: current")
    pI = I["data"][0]["data"][0]
    cur_I = (pI[0], pI[1])[len(pI) >= 2]

    if cur_I == None:
        return 0

    return cur_I + 0.05

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
