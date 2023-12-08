# Скрипт используется в процессе отладки сервисов.
# Он копируется в контейнер и запускается с одним параметром - именем
# сервиса для отладки.
import json
import sys
import asyncio
import subprocess
import signal
import time

async def main():

    config_endpoint = "http://localhost/config/"
    full_config = await unix_req(config_endpoint)

    listener_endpoint = "http://localhost/config/listeners"
    app_endpoint = "http://localhost/config/applications"
    debug_svc = sys.argv[1]
    if debug_svc is None:
        print("Не указан сервис для отладки.")
        return
    # Get all applications in json
    app_response = await unix_req(app_endpoint)
    apps = app_response.keys()
    if debug_svc not in list(apps):
        print("Указанный сервис для отладки не в списке запущенных приложений.")
        return
    # Get all listeners in json
    listener_response = await unix_req(listener_endpoint)
    listener = None
    for k, l in listener_response.items():
        if l.get('pass') == 'applications/' + debug_svc:
            listener = k

    # Save all settings for debug svc
    if listener:
        debug_svc_port = listener.split(':')[-1]
    else:
        debug_svc_port = 8888
    debug_svc_python_home = app_response[debug_svc]['home']
    debug_svc_path = app_response[debug_svc]['path']
    debug_svc_working_dir = app_response[debug_svc]['working_directory']
    debug_svc_module = app_response[debug_svc]['module']
    debug_svc_callable = app_response[debug_svc]['callable']

    # Remove listener in debug mode
    if listener:
        await unix_req(f"{listener_endpoint}/{listener}", "DELETE")
    # Remove application in debug mode
    await unix_req(f"{app_endpoint}/{debug_svc}", "DELETE")

    print("Устанавливаем необходимые пакеты...")
    subprocess.run('pipenv install debugpy uvicorn', cwd=debug_svc_working_dir, shell=True)
    print("Запускаем процесс uvicorn. Для остановки процесса нажмите Ctrl+C...")
    subprocess.call(f"{debug_svc_python_home}bin/python -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m uvicorn {debug_svc_path.replace(debug_svc_working_dir, '').replace('/', '.')[1:]}{debug_svc_module}:{debug_svc_callable} --reload --host 0.0.0.0 --port {debug_svc_port}", stdout=subprocess.DEVNULL, cwd=debug_svc_working_dir, shell=True)

    print("Процесс отладки остановлен. Восстанавливаем конфигурацию...")
    res = await unix_req(f"{config_endpoint}", "PUT", full_config)
    #res = await unix_req(f"{app_endpoint}", "PUT", app_response[debug_svc])
    print(f"{json.dumps(res, indent=4)}")

async def unix_req(endpoint: str, req_type: str = "GET", data: dict = None):
    cmd = f"curl -X {req_type}"
    if data:
        cmd = f"{cmd} -d'{json.dumps(data)}'"
    cmd = f"{cmd} --unix-socket /var/run/control.unit.sock {endpoint}"

    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        json_response = json.loads(res.stdout)
    except:
        json_response = {}
    return json_response

if __name__ == "__main__":
    #asyncio.run(main())

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(main())
    for signal in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        print("Прерывание Ctrl+C")

    finally:
        loop.close()
