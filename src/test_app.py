import pytest
import requests

from app import app, DOG_FACTS


@pytest.fixture
def client():
    return app.test_client()


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data": ["Cats sleep a lot."]}


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_random_dog_fact(client):
    res = client.get("/dog")
    assert res.status_code == 200
    assert res.get_json()["fact"] in DOG_FACTS


def test_dog_fact_by_id(client):
    res = client.get("/dog/1")
    assert res.status_code == 200
    assert res.get_json() == {"id": 1, "fact": DOG_FACTS[1]}


def test_dog_fact_not_found(client):
    res = client.get("/dog/9999")
    assert res.status_code == 404


def test_random_cat_fact(client, monkeypatch):
    monkeypatch.setattr("app.requests.get", lambda *a, **k: FakeResponse())
    res = client.get("/cat")
    assert res.status_code == 200
    assert res.get_json() == {"fact": "Cats sleep a lot."}


def test_cat_fact_upstream_down(client, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError()

    monkeypatch.setattr("app.requests.get", boom)
    res = client.get("/cat")
    assert res.status_code == 502