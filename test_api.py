"""
test_api.py — автотесты FastAPI приложения.

Запуск:  python -m pytest test_api.py -v
         python -m pytest test_api.py -v --tb=short

Не требует живой БД — все обращения к get_db мокаются через dependency_overrides.
"""
import asyncio
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── env ДО импорта app ─────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL",
                       "postgresql+asyncpg://fake:fake@localhost/fake")
os.environ.setdefault("API_TOKEN", "test-token-api")

from fastapi.testclient import TestClient   # noqa: E402

from app.main import app                    # noqa: E402
from app.database import get_db             # noqa: E402

TOKEN = "test-token-api"
AUTH  = {"Authorization": f"Bearer {TOKEN}"}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _vacancy(**kw):
    obj = MagicMock()
    for k, v in {
        "id": 1, "date": date.today(), "title": "C++ Dev",
        "company": "ACME", "url": "https://hh.kz/vacancy/1",
        "source": "hh.kz", "salary_min": None, "salary_max": None,
        "currency": "KZT", "status": "applied", "template_used": None,
        "skill_gaps": None, "notes": None, "created_at": datetime.utcnow(),
        **kw,
    }.items():
        setattr(obj, k, v)
    return obj


def _project(**kw):
    obj = MagicMock()
    for k, v in {
        "id": 1, "date": date.today(), "platform": "Upwork",
        "project_title": "Fix bug", "client": None,
        "url": "https://upwork.com/jobs/1",
        "budget": None, "our_rate": None, "connects_spent": 6,
        "template_used": None, "comment": None, "status": "sent",
        "created_at": datetime.utcnow(),
        **kw,
    }.items():
        setattr(obj, k, v)
    return obj


def _make_db(*, rows=None, get_obj=None, scalar=1):
    """AsyncMock сессия с предзаданными ответами."""
    session = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = rows or []
    res.scalar_one.return_value = scalar
    res.__iter__ = MagicMock(return_value=iter([]))   # для chart

    # fetchone()[0].id для POST /vacancies upsert
    row = MagicMock()
    row.__getitem__ = lambda self, k: _vacancy(id=scalar)
    res.fetchone.return_value = row

    # .one() для stats
    vac_one = MagicMock(
        total=10, applied=6, interview=2, offer=0, rejected=2, new=0,
    )
    fl_one = MagicMock(total=4, connects_used=24, contracts=1, interviews=1)
    call_n = [0]

    def _one():
        call_n[0] += 1
        return vac_one if call_n[0] == 1 else fl_one

    res.one.side_effect = _one

    session.execute = AsyncMock(return_value=res)
    session.get     = AsyncMock(return_value=get_obj)
    session.commit  = AsyncMock()
    session.delete  = AsyncMock()
    session.add     = MagicMock()

    return session


def _override(session):
    async def _dep():
        yield session
    app.dependency_overrides[get_db] = _dep


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# /health
# ══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def _mock_session(self, monkeypatch, *, fail=False):
        """Мокаем app.database.AsyncSessionLocal (health.py не использует get_db)."""
        session = AsyncMock()
        if fail:
            session.execute = AsyncMock(side_effect=Exception("conn refused"))
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=ctx)
        import app.database as db_mod
        monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)

    def test_ok(self, client, monkeypatch):
        self._mock_session(monkeypatch)
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["db"] == "ok"
        assert "timestamp" in d

    def test_no_auth_required(self, client, monkeypatch):
        self._mock_session(monkeypatch)
        r = client.get("/health")   # без Bearer
        assert r.status_code == 200

    def test_db_error_returns_degraded(self, client, monkeypatch):
        self._mock_session(monkeypatch, fail=True)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "degraded"
        assert "error" in r.json()["db"]


# ══════════════════════════════════════════════════════════════════════════════
# /vacancies — AUTH
# ══════════════════════════════════════════════════════════════════════════════

class TestVacanciesAuth:
    def test_no_token_returns_401(self, client):
        r = client.get("/vacancies")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, client):
        _override(_make_db())
        r = client.get("/vacancies",
                       headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401

    def test_valid_token_passes(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/vacancies", headers=AUTH)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# /vacancies — GET
# ══════════════════════════════════════════════════════════════════════════════

class TestVacanciesList:
    def test_empty_list(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/vacancies", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_items(self, client):
        _override(_make_db(rows=[_vacancy(id=5, title="Qt Dev")]))
        r = client.get("/vacancies", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["id"] == 5
        assert body[0]["title"] == "Qt Dev"

    def test_limit_param(self, client):
        _override(_make_db(rows=[]))
        assert client.get("/vacancies?limit=5", headers=AUTH).status_code == 200

    def test_offset_param(self, client):
        _override(_make_db(rows=[]))
        assert client.get("/vacancies?offset=10", headers=AUTH).status_code == 200

    def test_limit_zero_422(self, client):
        r = client.get("/vacancies?limit=0", headers=AUTH)
        assert r.status_code == 422

    def test_limit_501_422(self, client):
        r = client.get("/vacancies?limit=501", headers=AUTH)
        assert r.status_code == 422

    def test_status_filter(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/vacancies?status=applied", headers=AUTH)
        assert r.status_code == 200

    def test_source_filter(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/vacancies?source=hh.kz", headers=AUTH)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# /vacancies — POST
# ══════════════════════════════════════════════════════════════════════════════

class TestVacanciesCreate:
    def _post(self, client, body):
        vac = _vacancy(**{k: v for k, v in body.items() if k != "salary_max"})
        s = _make_db(get_obj=vac, scalar=vac.id)
        _override(s)
        return client.post("/vacancies", headers=AUTH, json=body)

    def test_create_minimal(self, client):
        r = self._post(client, {
            "title": "C++ Dev", "company": "X",
            "url": "https://hh.kz/1", "source": "hh.kz",
        })
        assert r.status_code == 201

    def test_create_with_salary(self, client):
        r = self._post(client, {
            "title": "Dev", "company": "X",
            "url": "https://hh.kz/2", "source": "hh.kz",
            "salary_min": 400000, "salary_max": 600000, "currency": "KZT",
        })
        assert r.status_code == 201

    def test_missing_required_422(self, client):
        _override(_make_db())
        r = client.post("/vacancies", headers=AUTH,
                        json={"title": "only title"})
        assert r.status_code == 422

    def test_invalid_status_422(self, client):
        _override(_make_db())
        r = client.post("/vacancies", headers=AUTH, json={
            "title": "Dev", "company": "X",
            "url": "https://x.com", "source": "hh",
            "status": "unicorn",
        })
        assert r.status_code == 422

    def test_salary_max_lt_min_422(self, client):
        _override(_make_db())
        r = client.post("/vacancies", headers=AUTH, json={
            "title": "Dev", "company": "X",
            "url": "https://x.com", "source": "hh",
            "salary_min": 500000, "salary_max": 100000,
        })
        assert r.status_code == 422

    def test_no_auth_401(self, client):
        r = client.post("/vacancies", json={})
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# /vacancies — PATCH / DELETE
# ══════════════════════════════════════════════════════════════════════════════

class TestVacanciesMutation:
    def test_patch_not_found(self, client):
        _override(_make_db(get_obj=None))
        r = client.patch("/vacancies/9999", headers=AUTH,
                         json={"status": "rejected"})
        assert r.status_code == 404

    def test_patch_empty_body_400(self, client):
        _override(_make_db(get_obj=_vacancy()))
        r = client.patch("/vacancies/1", headers=AUTH, json={})
        assert r.status_code == 400

    def test_patch_status_ok(self, client):
        vac = _vacancy()
        s = _make_db(get_obj=vac)

        async def _refresh(obj):
            obj.status = "interview"

        s.refresh = _refresh
        _override(s)
        r = client.patch("/vacancies/1", headers=AUTH,
                         json={"status": "interview"})
        assert r.status_code == 200

    def test_delete_not_found(self, client):
        _override(_make_db(get_obj=None))
        r = client.delete("/vacancies/9999", headers=AUTH)
        assert r.status_code == 404

    def test_delete_ok(self, client):
        _override(_make_db(get_obj=_vacancy()))
        r = client.delete("/vacancies/1", headers=AUTH)
        assert r.status_code == 204


# ══════════════════════════════════════════════════════════════════════════════
# /freelance
# ══════════════════════════════════════════════════════════════════════════════

class TestFreelance:
    def test_no_auth_401(self, client):
        r = client.get("/freelance")
        assert r.status_code == 401

    def test_list_empty(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/freelance", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == []

    def test_list_items(self, client):
        _override(_make_db(rows=[_project(id=3, project_title="Python bot")]))
        r = client.get("/freelance", headers=AUTH)
        assert r.status_code == 200
        assert r.json()[0]["project_title"] == "Python bot"

    def test_list_platform_filter(self, client):
        _override(_make_db(rows=[]))
        r = client.get("/freelance?platform=Upwork", headers=AUTH)
        assert r.status_code == 200

    def test_create_with_url(self, client):
        proj = _project(id=7)
        s = _make_db(get_obj=proj, scalar=7)
        _override(s)
        r = client.post("/freelance", headers=AUTH, json={
            "project_title": "API integration",
            "platform": "Upwork",
            "url": "https://upwork.com/jobs/test",
        })
        assert r.status_code == 201

    def test_create_without_url(self, client):
        """url=None → прямой INSERT без upsert."""
        proj = _project(id=8, url=None)
        s = AsyncMock()
        s.add = MagicMock()
        s.commit = AsyncMock()

        async def _refresh(obj):
            # имитируем что БД заполнила id и created_at
            obj.id = 8
            obj.created_at = datetime.utcnow()

        s.refresh = _refresh
        _override(s)
        r = client.post("/freelance", headers=AUTH, json={
            "project_title": "Fix bug",
            "platform": "Kwork",
        })
        assert r.status_code == 201

    def test_create_missing_platform_422(self, client):
        _override(_make_db())
        r = client.post("/freelance", headers=AUTH,
                        json={"project_title": "x"})
        assert r.status_code == 422

    def test_patch_not_found(self, client):
        _override(_make_db(get_obj=None))
        r = client.patch("/freelance/999", headers=AUTH,
                         json={"status": "contract"})
        assert r.status_code == 404

    def test_patch_empty_body_400(self, client):
        _override(_make_db(get_obj=_project()))
        r = client.patch("/freelance/1", headers=AUTH, json={})
        assert r.status_code == 400

    def test_patch_invalid_status_422(self, client):
        _override(_make_db())
        r = client.patch("/freelance/1", headers=AUTH,
                         json={"status": "bad"})
        assert r.status_code == 422

    def test_patch_ok(self, client):
        proj = _project()
        s = _make_db(get_obj=proj)

        async def _refresh(obj):
            obj.status = "contract"

        s.refresh = _refresh
        _override(s)
        r = client.patch("/freelance/1", headers=AUTH,
                         json={"status": "contract"})
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# /stats
# ══════════════════════════════════════════════════════════════════════════════

class TestStats:
    @pytest.fixture()
    def db_stats(self):
        return _make_db()  # .one() уже настроен с счётчиком

    def test_stats_ok(self, client, db_stats):
        _override(db_stats)
        r = client.get("/stats", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["period_days"] == 7
        assert body["vacancies"]["total"] == 10
        assert body["vacancies"]["applied"] == 6
        assert body["freelance"]["connects_used"] == 24
        assert body["freelance"]["contracts"] == 1

    def test_stats_custom_days(self, client, db_stats):
        _override(db_stats)
        r = client.get("/stats?days=30", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["period_days"] == 30

    def test_stats_days_gt_365_422(self, client):
        r = client.get("/stats?days=366", headers=AUTH)
        assert r.status_code == 422

    def test_stats_days_zero_422(self, client):
        r = client.get("/stats?days=0", headers=AUTH)
        assert r.status_code == 422

    def test_stats_no_auth_401(self, client):
        r = client.get("/stats")
        assert r.status_code == 401

    def test_chart_ok(self, client):
        s = AsyncMock()
        res = MagicMock()
        res.__iter__ = MagicMock(return_value=iter([]))  # пустые строки
        s.execute = AsyncMock(return_value=res)
        _override(s)
        r = client.get("/stats/chart?days=14", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert len(body["labels"]) == 14
        assert body["datasets"][0]["label"] == "Вакансии"

    def test_chart_invalid_days(self, client):
        r = client.get("/stats/chart?days=6", headers=AUTH)  # min=7
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# /brief/run
# ══════════════════════════════════════════════════════════════════════════════

class TestBriefRun:
    def test_no_auth_401(self, client):
        r = client.post("/brief/run")
        assert r.status_code == 401

    def test_script_not_found_500(self, client, monkeypatch):
        import app.routers.brief as bm
        monkeypatch.setattr(bm, "_BRIEF_SCRIPT", Path("/no/such/file.py"))
        r = client.post("/brief/run", headers=AUTH)
        assert r.status_code == 500

    def test_run_ok(self, client, tmp_path, monkeypatch):
        script = tmp_path / "morning_brief.py"
        script.write_text("print('brief OK')")

        import app.routers.brief as bm
        monkeypatch.setattr(bm, "_BRIEF_SCRIPT", script)

        async def _fake_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"brief OK\n", b""))
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        r = client.post("/brief/run", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "brief OK" in body["stdout"]
        assert body["returncode"] == 0

    def test_run_nonzero_exit(self, client, tmp_path, monkeypatch):
        script = tmp_path / "morning_brief.py"
        script.write_text("import sys; sys.exit(1)")

        import app.routers.brief as bm
        monkeypatch.setattr(bm, "_BRIEF_SCRIPT", script)

        async def _fake_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"", b"error\n"))
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        r = client.post("/brief/run", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert body["returncode"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Misc / Docs
# ══════════════════════════════════════════════════════════════════════════════

class TestMisc:
    def test_docs_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_json(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert spec["info"]["title"] == "Job Search API"
        paths = spec["paths"]
        for path in ["/health", "/vacancies", "/freelance", "/stats", "/brief/run"]:
            assert path in paths, f"Missing path: {path}"

    def test_404_for_unknown_route(self, client):
        r = client.get("/nonexistent")
        assert r.status_code == 404
