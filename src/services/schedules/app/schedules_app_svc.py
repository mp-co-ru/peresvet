import sys
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler

sys.path.append(".")

from src.common import times
from src.common.app_svc import AppSvc
from src.services.schedules.app.schedules_app_settings import SchedulesAppSettings

class SchedulesApp(AppSvc):

    def __init__(self, settings: SchedulesAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._scheduler = AsyncIOScheduler()

    async def _created(self, mes: dict, routing_key: str = None):
        """
        Формат prsJsonConfigString расписания:
        {
            "start": "<дата ISO8601>",
            "end": "<дата ISO8601>",
            "interval_type": "seconds | minutes | hours | days", '
            "interval_value": <int> 
        }
        """

        payload = {
            "id": mes["id"],
            "attributes": ["prsJsonConfigString", "prsActive"]
        }
        schedule = await self._hierarchy.search(payload)
        if not schedule:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по расписанию {payload['id']}")
            return
        
        active = schedule[0][2]["prsActive"][0] == "TRUE"
        if not active:
            self._logger.info(f"{self._config.svc_name} :: Расписание {payload['id']} неактивно.")
            return
        
        try:
            sched_config = json.loads(schedule[0][2]["prsJsonConfigString"][0])            
        except json.JSONDecodeError:
            self._logger.error(f"{self._config.svc_name} :: Конфигурация расписания {payload['id']} не в json-формате.")
            return

        await self.start_schedule(schedule_id=payload["id"], sched_config=sched_config)
        self._logger.info(f"{self._config.svc_name} :: Расписание {payload['id']} запущено.")
        
        return

    async def _updated(self, mes: dict, routing_key: str = None) -> dict:
        try:
            await self.stop_schedule(mes["id"])
        except:
            pass
        return await self._created(mes)
        
    async def _deleted(self, mes: dict, routing_key: str = None) -> dict:
        await self.stop_schedule(mes["id"])
        self._logger.info(f"{self._config.svc_name} :: Расписание {mes['id']} остановлено.")
        return {}

    async def _generate_event(self, sched_id: str):
        body = {
            "id": sched_id,
            "time": times.now_int()
        }
        await self._post_message(
            mes=body, 
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app.fire_event.{sched_id}"
        )
        
        self._logger.info(f"{self._config.svc_name} :: Событие расписания '{sched_id}'")

    async def start_schedule(self, schedule_id: str, sched_config: dict):
        match sched_config["interval_type"]:
            case "seconds":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    seconds=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=times.ts_to_local_str(sched_config["start"]),
                    end_date=times.ts_to_local_str(sched_config.get("end"))
                )
            case "minutes":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    minutes=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=times.ts_to_local_str(sched_config["start"]),
                    end_date=times.ts_to_local_str(sched_config.get("end"))
                )
            case "hours":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    hours=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=times.ts_to_local_str(sched_config["start"]),
                    end_date=times.ts_to_local_str(sched_config.get("end"))
                )
            case "days":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    days=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=times.ts_to_local_str(sched_config["start"]),
                    end_date=times.ts_to_local_str(sched_config.get("end"))
                )

        self._logger.info(f"{self._config.svc_name} :: Расписание {schedule_id} инициировано.")

    async def stop_schedule(self, schedule_id: str):
        if self._scheduler.get_job(schedule_id):
            self._scheduler.remove_job(schedule_id)

    async def on_startup(self) -> None:
        await super().on_startup()

        search_schedules = {
            "filter": {
                "objectClass": [self._config.hierarchy["class"]],
                "prsActive": ['TRUE']
            },
            "attributes": ["prsJsonConfigString"]
        }

        schedules = await self._hierarchy.search(search_schedules)
        for schedule_id, _, attrs in schedules:
            config_str = attrs.get("prsJsonConfigString")[0]
            if config_str is None:
                continue

            try: 
                sched_config = json.loads(config_str)
            except:
                self._logger.error(f"{self._config.svc_name} :: Ошибка чтения конфигурации расписания '{schedule_id}'.")
                continue

            try:
                await self.start_schedule(schedule_id=schedule_id, sched_config=sched_config)
            except Exception as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка запуска расписания '{schedule_id}': {ex}.")
                continue
            

        self._scheduler.start()

settings = SchedulesAppSettings()

app = SchedulesApp(settings=settings, title="`SchedulesApp` service")
