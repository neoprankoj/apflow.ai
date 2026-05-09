from fastapi import APIRouter, Depends, HTTPException

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import get_audit_agent, get_auth_service, get_current_user, get_repository
from app.core.auth import AuthService
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    LoginRequest,
    RegisterDemoTenantRequest,
    TokenResponse,
    UserRole,
)

router = APIRouter()


@router.post("/register-demo-tenant", response_model=TokenResponse)
def register_demo_tenant(
    payload: RegisterDemoTenantRequest,
    repository: InMemoryAPRepository = Depends(get_repository),
    auth_service: AuthService = Depends(get_auth_service),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> TokenResponse:
    tenant = repository.create_tenant(
        name=payload.tenant_name,
        slug=payload.tenant_slug,
    )
    user = repository.create_user(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=auth_service.hash_password(payload.password),
    )
    membership = repository.create_membership(tenant.id, user.id, UserRole.OWNER)
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(user.id),
            action="auth.register_demo_tenant",
            entity_type="tenant",
            entity_id=tenant.id,
            metadata={"role": str(membership.role), "email": user.email},
        )
    )
    return TokenResponse(
        access_token=auth_service.create_access_token(user, tenant, membership),
        expires_in_minutes=settings.access_token_expire_minutes,
        user=user,
        tenant=tenant,
        role=membership.role,
        permissions=auth_service.permissions_for_role(membership.role),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    repository: InMemoryAPRepository = Depends(get_repository),
    auth_service: AuthService = Depends(get_auth_service),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> TokenResponse:
    user = repository.get_user_by_email(payload.email)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    password_hash = repository.get_user_password_hash(user.id)
    if password_hash is None or not auth_service.verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    memberships = repository.list_memberships_for_user(user.id)
    if payload.tenant_id is not None:
        memberships = [membership for membership in memberships if membership.tenant_id == payload.tenant_id]
    if not memberships:
        raise HTTPException(status_code=403, detail="No tenant membership")
    membership = memberships[0]
    tenant = repository.get_tenant(membership.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=403, detail="Tenant access denied")
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(user.id),
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            metadata={"email": user.email},
        )
    )
    return TokenResponse(
        access_token=auth_service.create_access_token(user, tenant, membership),
        expires_in_minutes=settings.access_token_expire_minutes,
        user=user,
        tenant=tenant,
        role=membership.role,
        permissions=auth_service.permissions_for_role(membership.role),
    )


@router.get("/me", response_model=CurrentUserContext)
def me(context: CurrentUserContext = Depends(get_current_user)) -> CurrentUserContext:
    return context


@router.post("/logout")
def logout(
    context: CurrentUserContext = Depends(get_current_user),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> dict[str, str]:
    audit_agent.record(
        AuditEventInput(
            tenant_id=context.tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="auth.logout",
            entity_type="user",
            entity_id=context.user.id,
            metadata={},
        )
    )
    return {"status": "logged_out"}
