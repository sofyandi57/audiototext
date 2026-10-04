from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from ..services import Services

COOKIE = "mi_token"


def get_services(request: Request) -> Services:
    return request.app.state.services


def is_authenticated(request: Request) -> bool:
    token = request.app.state.services.settings.access_token
    if not token:
        return True
    supplied = request.cookies.get(COOKIE, "")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    return hmac.compare_digest(supplied.encode(), token.encode())


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Butuh token akses. Buka Settings untuk masuk.")


def not_found(what: str = "Data") -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} tidak ditemukan.")
