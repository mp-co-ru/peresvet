from src.common.model_crud_settings import CRUDSvcSettings

class TagsCRUDSettings(CRUDSvcSettings):
    # имя exchange'а, который публикует запросы от API_CRUD
    api_crud_exchange: str = "tags_api_crud"
    # имя очереди, которую будут слушать все экземпляры сервиса model_crud
    api_crud_queue: str = "tags_api_crud"
    # имя узла для хранения сущностей в иерархии
    # если узел не требуется, то пустая строка
    hierarchy_node = "tags"
    # класс экзмепляров сущности в иерархии
    hierarchy_class = "prsTag"
