import src.common.svc as svc
from .tags_api_crud_settings import TagsAPICRUDSettings

class TagsAPICRUD(svc.Svc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
