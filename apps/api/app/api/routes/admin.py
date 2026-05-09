from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import get_audit_agent, get_auth_service, get_repository, require_permission
from app.core.auth import AuthService, ROLE_PERMISSIONS
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AdminUserRecord,
    AuditEventInput,
    CreateTenantUserRequest,
    CurrentUserContext,
    Permission,
    TenantRecordSchema,
    UpdateUserRoleRequest,
)

router = APIRouter()


@router.get("/tenants/current", response_model=TenantRecordSchema)
def current_tenant(
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
) -> TenantRecordSchema:
    return context.tenant


@router.get("/users", response_model=list[AdminUserRecord])
def list_tenant_users(
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
) -> list[AdminUserRecord]:
    return [
        AdminUserRecord(user=user, role=membership.role, is_active=user.is_active)
        for user, membership in repository.list_users_for_tenant(context.tenant.id)
    ]


@router.post("/users", response_model=AdminUserRecord)
def create_tenant_user(
    payload: CreateTenantUserRequest,
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    auth_service: AuthService = Depends(get_auth_service),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> AdminUserRecord:
    user = repository.create_user(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=auth_service.hash_password(payload.password),
    )
    membership = repository.create_membership(context.tenant.id, user.id, payload.role)
    audit_agent.record(
        AuditEventInput(
            tenant_id=context.tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.user_created",
            entity_type="user",
            entity_id=user.id,
            metadata={"role": str(membership.role), "email": user.email},
        )
    )
    return AdminUserRecord(user=user, role=membership.role, is_active=user.is_active)


@router.patch("/users/{user_id}/role", response_model=AdminUserRecord)
def update_user_role(
    user_id: UUID,
    payload: UpdateUserRoleRequest,
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> AdminUserRecord:
    try:
        membership = repository.update_membership_role(context.tenant.id, user_id, payload.role)
        user = repository.get_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found for tenant") from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found for tenant")
    audit_agent.record(
        AuditEventInput(
            tenant_id=context.tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.user_role_updated",
            entity_type="user",
            entity_id=user_id,
            metadata={"role": str(membership.role)},
        )
    )
    return AdminUserRecord(user=user, role=membership.role, is_active=user.is_active)


@router.delete("/users/{user_id}", response_model=AdminUserRecord)
def deactivate_user(
    user_id: UUID,
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> AdminUserRecord:
    try:
        user = repository.deactivate_user(context.tenant.id, user_id)
        membership = repository.get_membership(context.tenant.id, user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found for tenant") from exc
    if membership is None:
        raise HTTPException(status_code=404, detail="User not found for tenant")
    audit_agent.record(
        AuditEventInput(
            tenant_id=context.tenant.id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.user_deactivated",
            entity_type="user",
            entity_id=user_id,
            metadata={},
        )
    )
    return AdminUserRecord(user=user, role=membership.role, is_active=user.is_active)


@router.get("/permissions")
def list_permissions(
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
) -> dict:
    return {
        "role": str(context.membership.role),
        "permissions": [str(permission) for permission in context.permissions],
        "roles": {
            str(role): [str(permission) for permission in permissions]
            for role, permissions in ROLE_PERMISSIONS.items()
        },
    }
