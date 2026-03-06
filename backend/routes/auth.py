"""Google OAuth + JWT authentication routes."""
from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
import jwt
from jwt.exceptions import PyJWTError
from pydantic import BaseModel

from backend.services.turso_db import User, Wishlist, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Config ────────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET           = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    import warnings
    warnings.warn("JWT_SECRET 환경변수가 설정되지 않았습니다. 프로덕션에서는 반드시 설정하세요.", stacklevel=1)
    import secrets
    JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM        = "HS256"
JWT_EXPIRE_DAYS      = 30
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:8000")
REDIRECT_URI         = os.getenv("REDIRECT_URI", "http://localhost:8000/api/auth/callback")

# ── JWT 블랙리스트 (인메모리 LRU, 최대 10000 토큰) ──────────────────────────
_BLACKLIST_MAX = 10_000
_jwt_blacklist: OrderedDict[str, bool] = OrderedDict()


def _blacklist_jti(jti: str) -> None:
    _jwt_blacklist[jti] = True
    _jwt_blacklist.move_to_end(jti)
    if len(_jwt_blacklist) > _BLACKLIST_MAX:
        _jwt_blacklist.popitem(last=False)


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_jwt(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire, "jti": uuid.uuid4().hex},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("jti") in _jwt_blacklist:
        raise HTTPException(status_code=401, detail="Token has been revoked")
    return payload


# ── Auth dependency ───────────────────────────────────────────────────────────
def get_current_user(
    authorization: str | None = Header(default=None),
    db=Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_jwt(authorization.split(" ", 1)[1])
    user = User.get_by_id(db, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Request/response models ───────────────────────────────────────────────────
class WishlistAddBody(BaseModel):
    product_id: str


class SyncBody(BaseModel):
    wishlist_ids: list[str]


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/google")
def google_login_url() -> dict:
    """Return the Google OAuth URL for the frontend to redirect to."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"url": url}


@router.get("/callback")
def google_callback(code: str, db=Depends(get_db)):
    """Handle Google OAuth callback, issue JWT, redirect to frontend."""
    # Exchange code for access token
    with httpx.Client(timeout=10) as http:
        token_res = http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            import logging
            logging.error(f"[OAuth] token exchange failed: {token_data}")
            raise HTTPException(status_code=400, detail=f"Google OAuth failed: {token_data}")

        # Fetch user profile
        user_res = http.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = user_res.json()

    # Find or create user
    user = User.get_by_google_id(db, user_info["sub"])
    if not user:
        user = User.create(
            db, user_info["sub"], user_info.get("email", ""),
            user_info.get("name", ""), user_info.get("picture", ""),
        )
    else:
        db.execute(
            "UPDATE users SET name=?, picture=? WHERE google_id=?",
            (user_info.get("name", ""), user_info.get("picture", ""), user_info["sub"]),
        )
        db.commit()
        user = User.get_by_google_id(db, user_info["sub"])

    token = create_jwt(user.id, user.email)
    # fragment(#)는 서버 로그·Referer 헤더에 포함되지 않아 토큰 노출 방지
    return RedirectResponse(url=f"{FRONTEND_URL}/my.html#token={token}")


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict:
    """Return current user info."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


@router.get("/wishlist")
def get_wishlist(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    items = Wishlist.get_by_user(db, current_user.id)
    return {
        "wishlist": [
            {"product_id": i.product_id, "added_at": i.added_at}
            for i in items
        ]
    }


@router.post("/wishlist")
def add_wishlist(
    body: WishlistAddBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    if not Wishlist.exists(db, current_user.id, body.product_id):
        Wishlist.create(db, current_user.id, body.product_id)
    return {"ok": True}


@router.delete("/wishlist/{product_id}")
def remove_wishlist(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    Wishlist.delete(db, current_user.id, product_id)
    return {"ok": True}


@router.post("/sync")
def sync_wishlist(
    body: SyncBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """Sync localStorage wishlist IDs to the backend DB."""
    synced = 0
    for product_id in body.wishlist_ids:
        if not Wishlist.exists(db, current_user.id, product_id):
            Wishlist.create(db, current_user.id, product_id)
            synced += 1
    return {"ok": True, "synced": synced}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    """로그아웃 — 토큰을 블랙리스트에 추가하여 서버사이드에서도 무효화."""
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(
                authorization.split(" ", 1)[1],
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM],
            )
            jti = payload.get("jti")
            if jti:
                _blacklist_jti(jti)
        except PyJWTError:
            pass  # 이미 만료된 토큰이면 무시
    return {"ok": True, "message": "Logged out"}
