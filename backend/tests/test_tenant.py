import io

from httpx import AsyncClient

from tests.test_auth import _create_user


async def test_tenant_config_unauthenticated_returns_401(client: AsyncClient):
    response = await client.get("/api/tenant/config")
    assert response.status_code == 401


async def _login(client: AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code in (200, 204)


async def test_tenant_config_authenticated_returns_default(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    response = await client.get("/api/tenant/config")
    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "My Company"
    assert body["primary_color"] == "#6dd5fa"
    assert body["logo_filename"] is None


async def test_tenant_config_put_requires_superuser(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    response = await client.put(
        "/api/tenant/config",
        json={"company_name": "Hacker Inc."},
    )
    assert response.status_code == 403


async def test_tenant_config_put_updates_fields(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    response = await client.put(
        "/api/tenant/config",
        json={
            "company_name": "Acme Co",
            "primary_color": "#7ad27a",
            "welcome_message": "Welcome aboard.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "Acme Co"
    assert body["primary_color"] == "#7ad27a"
    assert body["welcome_message"] == "Welcome aboard."


async def test_tenant_config_put_validates_color(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    response = await client.put(
        "/api/tenant/config",
        json={"primary_color": "not-a-hex"},
    )
    assert response.status_code == 422


# 1x1 transparent PNG bytes
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"
)


async def test_logo_upload_requires_superuser(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    files = {"file": ("logo.png", io.BytesIO(_TINY_PNG), "image/png")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 403


async def test_logo_upload_succeeds_for_superuser(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    files = {"file": ("logo.png", io.BytesIO(_TINY_PNG), "image/png")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["logo_filename"] is not None
    assert body["logo_filename"].startswith("logo-")
    assert body["logo_filename"].endswith(".png")


async def test_logo_upload_rejects_non_image(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    files = {"file": ("not-an-image.png", io.BytesIO(b"plain text not png"), "image/png")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 400


_SAFE_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="4" fill="blue"/></svg>'
_MALICIOUS_SVG_SCRIPT = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
_MALICIOUS_SVG_ONLOAD = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'


async def test_logo_upload_accepts_safe_svg(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    files = {"file": ("logo.svg", io.BytesIO(_SAFE_SVG), "image/svg+xml")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 200
    assert response.json()["logo_filename"].endswith(".svg")


async def test_logo_upload_rejects_svg_with_script(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    files = {"file": ("logo.svg", io.BytesIO(_MALICIOUS_SVG_SCRIPT), "image/svg+xml")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 400


async def test_logo_upload_rejects_svg_with_onload(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    files = {"file": ("logo.svg", io.BytesIO(_MALICIOUS_SVG_ONLOAD), "image/svg+xml")}
    response = await client.post("/api/tenant/logo", files=files)
    assert response.status_code == 400
