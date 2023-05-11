from src.common.settings import Settings

class ModelCRUDSettings(Settings):

    # имя exchange'а, который публикует запросы от API_CRUD
    api_crud_exchange_name: str = ""
    api_crud_exchange_type: str = "direct"
    # имя очереди, которую будут слушать все экземпляры сервиса model_crud
    api_crud_queue_name: str = ""
    # routing_key для очереди
    api_crud_routing_key: str = ""

    # имя узла для хранения сущностей в иерархии
    # пример: tags, objects, ...
    # если узел не требуется, то пустая строка
    hierarchy_node_name = ""
    # класс экзмепляров сущности в
    # пример: prsTag
    hierarchy_class = ""
    # список через запятую родительских классов
    hierarchy_parent_classes = ""
