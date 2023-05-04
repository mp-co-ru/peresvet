from src.common.settings import Settings

class ModelCRUDSettings(Settings):

    # имя exchange'а, который публикует запросы от API_CRUD
    api_crud_exchange: str = "api_crud"
    # имя очереди, которую будут слушать все экземпляры сервиса model_crud
    api_crud_queue: str = "api_crud"
    # имя узла для хранения сущностей в иерархии
    # если узел не требуется, то пустая строка
    hierarchy_node = ""
    # класс экзмепляров сущности в иерархии
    hierarchy_class = ""
    # список через запятую родительских классов
    hierarchy_parent_classes = ""
