import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.contracts import ProbeInput, ProjectInput, RevisionInput
from app.domain import Base
from app.services import Business
from app.settings import Settings
from app.storage import Storage


@pytest.fixture(params=["sqlite", "postgres"] if os.getenv("BID_TEST_POSTGRES") else ["sqlite"])
def business(tmp_path, request):
    schema = "test_" + uuid.uuid4().hex
    if request.param == "postgres":
        url = os.environ["BID_TEST_POSTGRES"]
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url += ("&" if "?" in url else "?") + f"options=-csearch_path%3D{schema}"
    else:
        url = f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(url, tmp_path)
    store = Storage(settings)
    Base.metadata.create_all(store.engine)
    yield Business(store)
    store.engine.dispose()
    if request.param == "postgres":
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def prepared(business):
    p = business.create_project(ProjectInput(name="合成项目", customer="合成客户", enterprise="合成企业"))
    rev = business.save_revision(p["id"], RevisionInput(request_id="source", logical_id="source-1", kind="source",
            actor="tester", reason="fixture", payload={"synthetic": True,
            "text": '服务期三年；仅含已确认范围。\n未经批准，不得增加“自动”保证。', "locator": "fixture/1"}))
    run = business.create_probe(p["id"], ProbeInput(request_id="run", expected_generation=rev["generation"],
                                                   source_ids=[rev["id"]]))
    return business, p, rev, run
