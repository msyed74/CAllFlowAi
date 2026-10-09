from datetime import datetime, timezone
import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.config import settings
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.app.models.organizations import Organization
from backend.app.models.roles import Role
from backend.app.models.users import User
from backend.app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Registers a new organization, default admin role, and initial user."""
    # Check if user already exists
    existing_user_stmt = select(User).where(User.email == payload.email)
    existing_user = (await db.execute(existing_user_stmt)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    # Slug generation
    slug = re.sub(r"[^a-z0-9]+", "-", payload.organization_name.lower()).strip("-")
    slug_stmt = select(Organization).where(Organization.slug == slug)
    existing_slug = (await db.execute(slug_stmt)).scalar_one_or_none()
    if existing_slug:
        import uuid
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # 1. Create Organization
    org = Organization(
        name=payload.organization_name,
        slug=slug,
        status="active",
    )
    db.add(org)
    await db.flush()

    # 2. Create Default Admin Role
    admin_role = Role(
        organization_id=org.id,
        name="OrgAdmin",
        description="Full organizational administrator with complete privileges",
        permissions=["*"],
        is_system_role=True,
    )
    db.add(admin_role)
    await db.flush()

    # 3. Create Initial Admin User
    user = User(
        organization_id=org.id,
        role_id=admin_role.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_number=payload.phone_number,
        status="active",
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()

    # 4. Generate Tokens
    access_token = create_access_token(
        subject=user.id,
        org_id=org.id,
        role=admin_role.name,
        permissions=admin_role.permissions,
    )
    refresh_token = create_refresh_token(
        subject=user.id,
        org_id=org.id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Authenticates user credentials and issues token pair."""
    stmt = select(User).where(User.email == payload.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated or suspended",
        )

    # Refresh user's role
    await db.refresh(user, ["role"])
    role_name = user.role.name if user.role else "User"
    permissions = user.role.permissions if user.role else []

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    access_token = create_access_token(
        subject=user.id,
        org_id=user.organization_id,
        role=role_name,
        permissions=permissions,
    )
    refresh_token = create_refresh_token(
        subject=user.id,
        org_id=user.organization_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(payload: RefreshTokenRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Exchanges a valid refresh token for a fresh access token."""
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = decoded.get("sub")
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found",
        )

    await db.refresh(user, ["role"])
    role_name = user.role.name if user.role else "User"
    permissions = user.role.permissions if user.role else []

    new_access_token = create_access_token(
        subject=user.id,
        org_id=user.organization_id,
        role=role_name,
        permissions=permissions,
    )
    new_refresh_token = create_refresh_token(
        subject=user.id,
        org_id=user.organization_id,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="Bearer",
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieves profile of the authenticated user."""
    await db.refresh(current_user, ["role"])
    return UserResponse(
        id=current_user.id,
        organization_id=current_user.organization_id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone_number=current_user.phone_number,
        role=current_user.role.name if current_user.role else "User",
        permissions=current_user.role.permissions if current_user.role else [],
        status=current_user.status,
    )


@router.post("/logout")
async def logout(current_user: Annotated[User, Depends(get_current_user)]):
    """Logs out user and invalidates session."""
    return {"message": "Successfully logged out"}
