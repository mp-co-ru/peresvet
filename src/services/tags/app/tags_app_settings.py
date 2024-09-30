from src.common.svc_settings import SvcSettings

class TagsAppSettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "tags_app"
    
    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsTag"
    }

    nodes: list[str] = []