from base_svc_settings import BaseSvcSettings

class CRUDSvcSettings(BaseSvcSettings):

    # имя exchange'а, который публикует запросы от API_CRUD
    api_crud_exchange: str = "api_crud"
    # имя очереди, которую будут слушать все экземпляры сервиса model_crud
    api_crud_queue: str = "api_crud"
    # имя узла для хранения сущностей в иерархии
    # если узел не требуется, то пустая строка
    hierarchy_node = ""
    # класс экзмепляров сущности в иерархии
    hierarchy_class = ""
