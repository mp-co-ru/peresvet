from src.common.app_svc_settings import AppSvcSettings


class VideoDeliverySettings(AppSvcSettings):
    """Отдача тегов видеопотока.

    ``nodes`` — id тегов из конфигурации этого процесса, не атрибут LDAP
    и не класс иерархии. Пустой список значит все теги типа 6.
    Иерархия ``videoDelivery`` в каталог не пишется: подписка на
    ``prsTag.model`` здесь не вешается, иначе голос отдачи мог бы
    одобрить удаление тега раньше настоящего владельца.
    """

    svc_name: str = "video_delivery"
    http_base_url: str = "http://video-delivery:8092"
    http_port: int = 8092
    hierarchy: dict = {
        "node": "",
        "class": "videoDelivery",
    }
