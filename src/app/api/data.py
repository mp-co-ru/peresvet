from fastapi import APIRouter
from fastapi import Request
from fastapi import Response
import app.main as main
import app.models.Data as Data

router = APIRouter()

@router.post("/", status_code=200)
async def data_set(payload: Data.PrsReqSetData):
    return await main.app.data_set(payload)
    #return Response(status_code=204)

@router.get("/", status_code=200)
async def data_get(payload: Data.PrsReqGetData):
#async def data_get(payload = None):
    return await main.app.data_get(payload)
    #return {"data": []}
