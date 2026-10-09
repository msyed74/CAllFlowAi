from typing import Annotated, AsyncGenerator, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.middleware import current_tenant_id
from backend.app.core.security import decode_token
from backend.app.models.users import User

security_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticates the request bearer token and resolves the active user."""
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    org_id = payload.get("org_id")

    if not user_id or not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject or organization context",
        )

    # Fetch user from database
    stmt = select(User).where(User.id == user_id, User.organization_id == org_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
        )

    # Set tenant context variable for isolation
    current_tenant_id.set(org_id)
    return user


def require_permissions(required_permission: str):
    """Dependency factory checking user permissions."""
    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        # Load user role permissions
        await db.refresh(current_user, ["role"])
        role_permissions: List[str] = current_user.role.permissions if current_user.role else []
        
        # SuperAdmin or wildcard bypass
        if "*" in role_permissions or "all" in role_permissions:
            return current_user

        if required_permission not in role_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Missing required permission '{required_permission}'",
            )
        return current_user

    return permission_checker
