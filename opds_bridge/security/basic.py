import secrets
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from opds_bridge.config import Settings, get_settings

_security_scheme = HTTPBasic(realm="OPDS", auto_error=False)


def basic_auth_guard(
    credentials: Annotated[Optional[HTTPBasicCredentials], Depends(_security_scheme)],
    settings: Settings = Depends(get_settings),
):
    user = settings.OPDS_BASIC_USER
    pw = settings.OPDS_BASIC_PASS

    if not user and not pw:
        return

    challenge = {"WWW-Authenticate": 'Basic realm="OPDS"'}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth required",
            headers=challenge,
        )

    expected_user = (user or "").encode("utf-8")
    expected_pw = (pw or "").encode("utf-8")
    user_ok = secrets.compare_digest(credentials.username.encode("utf-8"), expected_user)
    pw_ok = secrets.compare_digest(credentials.password.encode("utf-8"), expected_pw)

    if not (user_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=challenge,
        )
