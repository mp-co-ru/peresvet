from fastapi import APIRouter
from fastapi import Request
import app.main as main
import app.models.Data as Data

router = APIRouter()

@router.post("/", status_code=200)
async def data_set(payload: Data.PrsReqSetData):
    return await main.app.data_set(payload)

@router.get("/", status_code=200)
async def data_get(payload: Data.PrsReqGetData):
    return await main.app.data_get(payload)
