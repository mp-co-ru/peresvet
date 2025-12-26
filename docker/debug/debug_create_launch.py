# скрипт создаёт конфигурацию для запуска отладки для определённого сервиса
# на вход принимает три параметра: id контейнера, имя сервиса и IP контейнера
import os
import sys
import os.path
import json

cont_id = sys.argv[1]
svc_name = sys.argv[2]
cont_ip = sys.argv[3]
launch_conf_name = f"MPC_DEBUG: {cont_id} {svc_name}"

launch_conf = {
    "name": launch_conf_name,
    "type": "python",
    "request": "attach",
    "connect": {
        "host": cont_ip,
        "port": 5678
    },
    "pathMappings": [
        {
            "localRoot": "${workspaceFolder}",
            "remoteRoot": "."
        }
    ],
    "justMyCode": True
}

cwd = os.getcwd()
launch_path = f"{cwd}/.vscode/launch.json"
if os.path.isfile(launch_path):
    with open(launch_path, mode="r", encoding="utf-8") as f:
        launch = json.load(f)
else:
    launch = {
        "version": "0.2.0",
        "configurations": []
    }

changed = False
for conf in launch["configurations"]:
    if conf["name"] == launch_conf_name:
        changed = True
        break

if changed:
    launch["configurations"].remove(conf)
launch["configurations"].append(launch_conf)

with open(launch_path, "w") as f:
    json.dump(launch, f, indent=4, ensure_ascii=False)
