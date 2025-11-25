import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.services.schedules.model_crud.schedules_model_crud_settings import SchedulesModelCRUDSettings

class SchedulesModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с расписаниями в иерархии.

<<<<<<< HEAD
    Подписывается на очередь ``schedules_api_crud`` обменника ``schedules_api_crud``\,
=======
    Подписывается на очередь ``schedules_api_crud`` обменника ``schedules_api_crud``,
>>>>>>> peresvet/dev
    в которую публикует сообщения сервис ``schedules_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: SchedulesModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
<<<<<<< HEAD
 
=======

>>>>>>> peresvet/dev

settings = SchedulesModelCRUDSettings()

app = SchedulesModelCRUD(settings=settings, title="SchedulesModelCRUD")
