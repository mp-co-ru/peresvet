import json
import os
import urllib
import urllib.request
import asyncio
import subprocess

async def main():

    # await wait_for_unit()

    listener_endpoint = "/config/listeners"
    app_endpoint = "/config/applications"
    debug_svc = os.environ['DEBUG_SVC']
    if debug_svc is None:
        return
    # Get all applications in json
    app_response = await unix_req(app_endpoint)
    apps = app_response.keys()
    if debug_svc not in list(apps):
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
    await unix_req(f"{listener_endpoint}/{listener}", "DELETE")
    # Remove application in debug mode
    await unix_req(f"{app_endpoint}/{debug_svc}", "DELETE")
    subprocess.run('pipenv install debugpy uvicorn', cwd=debug_svc_working_dir, shell=True)
    subprocess.call(f"{debug_svc_python_home}bin/python -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m uvicorn {debug_svc_path.replace(debug_svc_working_dir, '').replace('/', '.')[1:]}{debug_svc_module}:{debug_svc_callable} --reload --host 0.0.0.0 --port {debug_svc_port}", stdout=subprocess.DEVNULL, cwd=debug_svc_working_dir, shell=True)

async def unix_req(endpoint: str, req_type: str = "GET"):
    reader, writer = await asyncio.open_unix_connection("/var/run/control.unit.sock")
    query = (
        f"{req_type} {endpoint} HTTP/1.0\r\n"
        f"\r\n"
    )
    writer.write(query.encode('utf-8'))
    await writer.drain()
    writer.write_eof()
    headers = True
    while headers:
        line = await reader.readline()
        if line == b"\r\n":
            headers = False
        elif not line:
            break
    if not headers:
        data = await reader.read()
        json_response = json.loads(data.decode("utf-8"))
    writer.close()
    await writer.wait_closed()
    return json_response

# async def wait_for_unit():
    # while True:
    #     try:
    #         await unix_req('/config')
    #     except FileNotFoundError:
    #         print("Trying again")

if __name__ == "__main__":
    asyncio.run(main())
