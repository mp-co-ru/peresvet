from src.common.app_svc_settings import AppSvcSettings


class VideoCaptureSettings(AppSvcSettings):
    """Подхват камер.

    ``nodes`` — id коннекторов из конфигурации этого процесса.
    Пустой список значит все камеры. Это не узел каталога.
    ``http_base_url`` — адрес, по которому этот же процесс отдаёт байты
    соседним сервисам. Его процесс сообщает в RPC сам.
    """

    svc_name: str = "video_capture"
    http_base_url: str = "http://video-capture:8091"
    http_port: int = 8091
    hierarchy: dict = {
        "node": "connectors",
        "class": "prsConnector",
    }
