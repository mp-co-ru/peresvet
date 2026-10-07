from src.common.app_svc_settings import AppSvcSettings


class VideoAppSettings(AppSvcSettings):
    svc_name: str = "video_app"
    hierarchy: dict = {
        "node": "connectors",
        "class": "prsConnector",
    }
