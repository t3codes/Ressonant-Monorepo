import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from app.common.exceptions import invalid_credentials
from app.common.security import verify_dummy, verify_password
from app.config.settings import get_settings
from app.modules.auth.usecases.tokens import create_access_token
from app.modules.user.dataproviders.repository import UserRepository


class RateLimitInfo:
    """Estado thread-safe de tentativas de autenticação deste processo."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60) -> None:
        self.attempts: dict[str, tuple[int, float]] = {}
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = threading.Lock()

    def consume(self, key: str) -> tuple[bool, dict[str, int]]:
        now = time.time()
        with self._lock:
            count, started_at = self.attempts.get(key, (0, now))
            if now - started_at >= self.window_seconds:
                count, started_at = 0, now
            count += 1
            self.attempts[key] = (count, started_at)
            reset = int(started_at + self.window_seconds)
            return count <= self.max_attempts, {
                "remaining": max(0, self.max_attempts - count),
                "reset": reset,
                "retry_after": max(0, reset - int(now)),
            }

    def clear(self, key: str) -> None:
        with self._lock:
            self.attempts.pop(key, None)


_rate_limit = RateLimitInfo()
_token_blacklist: dict[str, float] = {}
_token_blacklist_lock = threading.Lock()


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository
        self.attempts = _rate_limit.attempts
        self.max_attempts = _rate_limit.max_attempts
        self.window_seconds = _rate_limit.window_seconds
        self._rate_limit = _rate_limit
        self._redis = None
        redis_url = os.getenv("REDIS_URL", "").strip()
        if redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.25,
                    socket_timeout=0.25,
                )
            except ImportError:
                self._redis = None

    @property
    def _redis_available(self) -> bool:
        return self._redis is not None

    def login(self, email: str, senha: str) -> tuple[str, int]:
        user = self._repo.get_by_email(email.lower())
        if user is None:
            verify_dummy(senha)
            raise invalid_credentials()
        if not verify_password(senha, user.senha_hash) or not user.status_ativo:
            raise invalid_credentials()
        return create_access_token(user.id)

    def check_rate_limit(self, ip: str) -> tuple[bool, dict[str, int]]:
        return self._rate_limit.consume(ip)

    def clear_rate_limit(self, ip: str) -> None:
        self._rate_limit.clear(ip)

    def logout(self, token: str) -> dict[str, str]:
        if token:
            expires_at = time.time() + 1800
            try:
                claims = jwt.decode(
                    token,
                    get_settings().auth_secret,
                    algorithms=[get_settings().jwt_algorithm],
                    options={"verify_exp": False},
                )
                if isinstance(claims.get("exp"), (int, float)):
                    expires_at = max(time.time(), float(claims["exp"]))
            except jwt.InvalidTokenError:
                pass
            ttl = max(1, int(expires_at - time.time()))
            with _token_blacklist_lock:
                _token_blacklist[token] = expires_at
            if self._redis is not None:
                self._redis.setex(f"blk_{token}", ttl, "invalidated")
        return {"message": "Logout successful"}

    def is_token_blacklisted(self, token: str) -> bool:
        if not token:
            return False
        now = time.time()
        with _token_blacklist_lock:
            expired = [key for key, expires_at in _token_blacklist.items() if expires_at <= now]
            for key in expired:
                _token_blacklist.pop(key, None)
            if _token_blacklist.get(token, 0) > now:
                return True
        return bool(self._redis is not None and self._redis.exists(f"blk_{token}"))

    def refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Troca um refresh token de uso único por novos tokens, se Redis estiver configurado."""
        if not refresh_token or self._redis is None:
            return None
        settings = get_settings()
        try:
            claims = jwt.decode(
                refresh_token,
                settings.auth_secret,
                algorithms=[settings.jwt_algorithm],
                options={"require": ["exp", "sub"]},
            )
        except jwt.InvalidTokenError:
            return None
        if claims.get("type") != "refresh":
            return None
        if self._redis.exists(f"blk_{refresh_token}"):
            return None

        user_id = claims.get("sub")
        if not isinstance(user_id, str) or not user_id:
            return None

        self._redis.setex(
            f"blk_{refresh_token}",
            max(1, int(claims["exp"] - time.time())),
            "revoked",
        )
        access_token, access_expires_in = create_access_token(user_id)
        refresh_claims = {
            "sub": user_id,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=30),
        }
        new_refresh_token = jwt.encode(
            refresh_claims,
            settings.auth_secret,
            algorithm=settings.jwt_algorithm,
        )
        return {
            "new_access_token": access_token,
            "new_refresh_token": new_refresh_token,
            "expires_in": access_expires_in,
        }
