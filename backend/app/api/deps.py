from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import supabase_client

# Reusable scheme — extracts the Bearer token from the Authorization header.
_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that validates a Supabase JWT.

    Flow:
        1. ``HTTPBearer`` extracts the token from the ``Authorization: Bearer``
           header.  If the header is missing or malformed, FastAPI returns a
           **403** automatically.
        2. The token is forwarded to ``supabase_client.auth.get_user()`` which
           calls Supabase's ``/auth/v1/user`` endpoint to verify the JWT and
           return the full user object.
        3. On success the user dict is returned; on any failure a **401** is
           raised.

    Returns:
        The Supabase user object (dict) for the authenticated user.
    """
    token = credentials.credentials

    try:
        response = supabase_client.auth.get_user(token)
        user = response.user
        if user is None:
            raise ValueError("No user returned")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return user
