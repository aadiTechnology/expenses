import os
import pathlib
import tempfile

_tmp = pathlib.Path(tempfile.mkdtemp())
# Tests run against real PostgreSQL by default (docker compose up -d); set SPENDOS_TEST_DB=sqlite:///... to override
os.environ["SPENDOS_DB"] = os.environ.get("SPENDOS_TEST_DB", "postgresql+psycopg://spendos:spendos_dev@localhost:15433/spendos_test")
os.environ["SPENDOS_ENV"] = "demo"
os.environ["SPENDOS_STORAGE"] = str(_tmp / "files")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.main import app  # noqa: E402

PW = seed.DEMO_PASSWORD


@pytest.fixture(scope="session", autouse=True)
def _seed():
    from app import models
    from app.core import engine
    from sqlalchemy import text
    models.Base.metadata.drop_all(engine)  # clean schema for every run; migrations rebuild it
    with engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS alembic_version'))
    seed.run(do_reset=True)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def login(client):
    def _login(name):
        r = client.post("/api/v1/auth/login", json={"email": name + seed.DOMAIN, "password": PW})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return _login
