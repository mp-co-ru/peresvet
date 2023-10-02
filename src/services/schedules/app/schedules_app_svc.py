import sys
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler

sys.path.append(".")

from src.services.schedules.app.schedules_app_settings import SchedulesAppSettings
from src.common import svc
from src.common.hierarchy import CN_SCOPE_ONELEVEL

class SchedulesApp(svc.Svc):

    def __init__(self, settings: SchedulesAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._scheduler = AsyncIOScheduler()

    def _set_incoming_commands(self) -> dict:
        return {
            "schedules.create": self._schedule_create,
            "schedules.update": self._schedule_update,
            "schedules.delete": self._schedule_delete
        }

    async def _schedule_create(self, mes: dict) -> dict:
        return {}

    async def _schedule_update(self, mes: dict) -> dict:
        return {}

    async def _schedule_delete(self, mes: dict) -> dict:
        return {}

    async def _generate_event(self, sched_id: str):
        body = {
            "action": "schedules.event",
            "data": {
                "scheduleId": sched_id
            }
        }

        await self._post_message(mes=body)

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
            sched_config = json.loads(attrs["prsJsonConfigString"])
            match sched_config["interval_type"]:
                case "seconds":
                    self._scheduler.add_job(
                        self._generate_event, 'interval',
                        kwargs={'sched_id': schedule_id},
                        seconds=sched_config["interval_value"],
                        start_date=sched_config["start"],
                        end_date=sched_config.get("end"))
                case "minutes":
                    self._scheduler.add_job(
                        self._generate_event, 'interval',
                        kwargs={'sched_id': schedule_id},
                        minutes=sched_config["interval_value"],
                        start_date=sched_config["start"],
                        end_date=sched_config.get("end"))
                case "hours":
                    self._scheduler.add_job(
                        self._generate_event, 'interval',
                        kwargs={'sched_id': schedule_id},
                        hours=sched_config["interval_value"],
                        start_date=sched_config["start"],
                        end_date=sched_config.get("end"))
                case "days":
                    self._scheduler.add_job(
                        self._generate_event, 'interval',
                        kwargs={'sched_id': schedule_id},
                        days=sched_config["interval_value"],
                        start_date=sched_config["start"],
                        end_date=sched_config.get("end"))

            self._logger.info(f"Расписание {schedule_id} инициировано.")

        self._scheduler.start()

settings = SchedulesAppSettings()

app = SchedulesApp(settings=settings, title="`SchedulesApp` service")
