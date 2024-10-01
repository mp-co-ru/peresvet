import sys
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler

sys.path.append(".")

from src.common import svc, times
from src.services.schedules.app.schedules_app_settings import SchedulesAppSettings
from src.common.hierarchy import CN_SCOPE_ONELEVEL

class SchedulesApp(svc.Svc):

    def __init__(self, settings: SchedulesAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._scheduler = AsyncIOScheduler()

    def _set_handlers(self) -> dict:
        return {
            "schedules_model_crud.created": self._schedule_created,
            "schedules_model_crud.updated": self._schedule_updated,
            "schedules_model_crud.deleted": self._schedule_deleted
        }

    async def _schedule_created(self, mes: dict) -> dict:
        payload = {
            "id": mes["data"]["id"],
            "attributes": ["prsJsonConfigString", "prsActive"]
        }
        schedule = await self._hierarchy.search(payload)
        if not schedule:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по расписанию {payload['id']}")
            return {}
        
        active = schedule[2]["prsActive"][0] == "TRUE"
        if not active:
            self._logger.info(f"{self._config.svc_name} :: Расписание {payload['id']} неактивно.")
            return {}
        
        try:
            sched_config = json.loads(schedule[2]["prsJsonConfigString"][0])
        except json.JSONDecodeError:
            self._logger.error(f"{self._config.svc_name} :: Конфигурация расписания {payload['id']} не в json-формате.")

        self.start_schedule(schedule_id=payload["id"], sched_config=sched_config)
        self._logger.info(f"{self._config.svc_name} :: Расписание {payload['id']} запущено.")
        
        return {}

    async def _schedule_updated(self, mes: dict) -> dict:
        self.stop_schedule(mes["data"]["id"])
        return self._schedule_created(mes)
        
    async def _schedule_deleted(self, mes: dict) -> dict:
        self.stop_schedule(mes["data"]["id"])
        self._logger.info(f"{self._config.svc_name} :: Расписание {mes['data']['id']} остановлено.")
        return {}

    async def _generate_event(self, sched_id: str):
        body = {
            "action": f"{self._config.svc_name}.event",
            "data": {
                "scheduleId": sched_id,
                "time": times.now_int()
            }
        }

        await self._post_message(mes=body)

    async def start_schedule(self, schedule_id: str, sched_config: dict):
        match sched_config["interval_type"]:
            case "seconds":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    seconds=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=sched_config["start"],
                    end_date=sched_config.get("end"))
            case "minutes":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    minutes=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=sched_config["start"],
                    end_date=sched_config.get("end"))
            case "hours":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    hours=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=sched_config["start"],
                    end_date=sched_config.get("end"))
            case "days":
                self._scheduler.add_job(
                    self._generate_event, 'interval',
                    kwargs={'sched_id': schedule_id},
                    days=sched_config["interval_value"],
                    id=schedule_id,
                    start_date=sched_config["start"],
                    end_date=sched_config.get("end"))

        self._logger.info(f"Расписание {schedule_id} инициировано.")

    async def stop_schedule(self, schedule_id: str):
        self._scheduler.remove_job(schedule_id)

    async def on_startup(self) -> None:
        await super().on_startup()

        search_schedules = {
            "filter": {
                "objectClass": [self._config.hierarchy["class"]]
            },
            "attributes": ["prsJsonConfigString"]
        }

        schedules = await self._hierarchy.search(search_schedules)
        for schedule_id, _, attrs in schedules:
            config_str = attrs.get("prsJsonConfigString")
            if config_str is None:
                continue

            if not (config_str is None):
                config_str = config_str[0]            
            try: 
                sched_config = json.loads(config_str)

                self.start_schedule(schedule_id=schedule_id, sched_config=sched_config)
            except ValueError:
                self._logger.error(f"Конфигурация расписания {schedule_id} должна быть в виде строки json.")
                continue

        self._scheduler.start()

settings = SchedulesAppSettings()

app = SchedulesApp(settings=settings, title="`SchedulesApp` service")
