import sys
import copy
import json
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from dataStorages_app_postgresql_settings import DataStoragesAppPostgreSQLSettings
from src.common import svc
from src.common import hierarchy

class DataStoragesAppPostgreSQL(svc.Svc):

    def __init__(
            self, settings: DataStoragesAppPostgreSQLSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        self._commands = {
            "tagSet": self._tag_set
        }

    async def _tag_set(self, mes: dict) -> None:
        pass

    async def on_startup(self) -> None:
        await super().on_startup()
