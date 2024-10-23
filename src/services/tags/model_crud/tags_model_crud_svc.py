import sys

sys.path.append(".")

from src.common import model_crud_svc
from src.services.tags.model_crud.tags_model_crud_settings import TagsModelCRUDSettings

class TagsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

settings = TagsModelCRUDSettings()

app = TagsModelCRUD(settings=settings, title="TagsModelCRUD")
