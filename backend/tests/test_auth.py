def test_signup_login_me(client):
    r = client.post("/api/auth/signup", json={"name": "A", "email": "a@x.com", "password": "password123"})
    assert r.status_code == 201
    token = r.json()["access_token"]

    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "password123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "nope"}).status_code == 401

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["plan"] == "starter"


def test_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"name": "A", "email": "dup@x.com", "password": "password123"})
    r = client.post("/api/auth/signup", json={"name": "B", "email": "dup@x.com", "password": "password123"})
    assert r.status_code == 409


def test_protected_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/leads").status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/auth/signup", json={"name": "A", "email": "s@x.com", "password": "short"})
    assert r.status_code == 422
