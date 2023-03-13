import os
import json

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.Tag import PrsTagCreate
from app.models.DataStorage import PrsDataStorageCreate, PrsDataStorageCreateAttrs

@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here

@pytest.fixture(scope='function')
@pytest.mark.asyncio
async def create_vm_default_datastorage(test_app):
    #TODO: передавать в PrsDataStorageCreate уже созданные атрибуты
    data = PrsDataStorageCreate(attributes={
        "prsDefault": True,
        "prsEntityTypeCode": 1,
        "prsJsonConfigString": json.dumps({"putUrl": "http://vm:8428/api/put", "getUrl": "http://vm:8428/api/v1/export"})
    } )
    '''
    data.attributes.prsDefault = True
    data.attributes.prsEntityTypeCode = 1
    data.attributes.prsJsonConfigString = json.dumps({"putUrl": "http://vm:8428/api/put", "getUrl": "http://vm:8428/api/v1/export"})
    '''
    #async with test_app.app.create_dataStorage(data) as ds:
    #    yield ds
    ds = await test_app.app.create_dataStorage(data)
    return ds

@pytest.fixture(scope='function')
@pytest.mark.asyncio
async def create_tag(test_app, create_vm_default_datastorage):
    #await create_vm_default_datastorage
    data = PrsTagCreate(attributes={})
    new_tag = await test_app.app.create_tag(data)
    return new_tag
