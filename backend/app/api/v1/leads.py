from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_permissions
from backend.app.models.leads import Lead
from backend.app.models.users import User
from backend.app.schemas.leads import LeadCreate, LeadResponse, LeadUpdate

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=List[LeadResponse])
async def list_leads(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    """Lists leads belonging strictly to the caller's organization."""
    stmt = select(Lead).where(Lead.organization_id == current_user.organization_id)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    stmt = stmt.offset(skip).limit(limit).order_by(Lead.created_at.desc())

    result = await db.execute(stmt)
    leads = result.scalars().all()
    return leads


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Creates a new lead within the caller's organization."""
    # Check for existing phone number under this tenant
    existing_stmt = select(Lead).where(
        Lead.organization_id == current_user.organization_id,
        Lead.phone_number == payload.phone_number,
    )
    existing_lead = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_lead:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A lead with this phone number already exists in your organization",
        )

    lead_data = payload.model_dump()
    lead = Lead(
        organization_id=current_user.organization_id,
        assigned_user_id=current_user.id,
        status="new",
        **lead_data,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieves lead details scoped to user's organization."""
    stmt = select(Lead).where(
        Lead.id == lead_id,
        Lead.organization_id == current_user.organization_id,
    )
    lead = (await db.execute(stmt)).scalar_one_or_none()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Updates lead attributes with tenant scoping."""
    stmt = select(Lead).where(
        Lead.id == lead_id,
        Lead.organization_id == current_user.organization_id,
    )
    lead = (await db.execute(stmt)).scalar_one_or_none()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)

    await db.commit()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/opt-out", response_model=LeadResponse)
async def opt_out_lead(
    lead_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Instantly marks lead as Do Not Call (DNC) for TCPA compliance."""
    stmt = select(Lead).where(
        Lead.id == lead_id,
        Lead.organization_id == current_user.organization_id,
    )
    lead = (await db.execute(stmt)).scalar_one_or_none()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    lead.status = "dnc"
    await db.commit()
    await db.refresh(lead)
    return lead
