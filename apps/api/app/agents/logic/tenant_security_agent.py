from uuid import UUID

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ResourceAction,
    SecurityDecisionInput,
    SecurityDecisionOutput,
)


class TenantSecurityAgent(BaseAgent[SecurityDecisionInput, SecurityDecisionOutput]):
    name = "TenantSecurityAgent"
    responsibility = "Enforce tenant isolation, RBAC, permissions, and sensitive data access."

    def __init__(
        self,
        audit_agent: AuditLoggingAgent | None = None,
        tenant_memberships: dict[str, set[UUID]] | None = None,
        role_permissions: dict[str, set[ResourceAction]] | None = None,
    ) -> None:
        self.audit_agent = audit_agent
        self.tenant_memberships = tenant_memberships or {}
        self.role_permissions = role_permissions or {
            "ap_admin": {
                ResourceAction.READ,
                ResourceAction.WRITE,
                ResourceAction.APPROVE,
                ResourceAction.EXPORT,
                ResourceAction.ADMIN,
            },
            "ap_manager": {
                ResourceAction.READ,
                ResourceAction.WRITE,
                ResourceAction.APPROVE,
                ResourceAction.EXPORT,
            },
            "approver": {ResourceAction.READ, ResourceAction.APPROVE},
            "vendor": {ResourceAction.READ},
            "agent": {ResourceAction.READ, ResourceAction.WRITE},
            "system": {
                ResourceAction.READ,
                ResourceAction.WRITE,
                ResourceAction.APPROVE,
                ResourceAction.EXPORT,
                ResourceAction.ADMIN,
            },
        }

    def authorize(self, request: SecurityDecisionInput) -> SecurityDecisionOutput:
        roles = set(request.context.get("roles", []))

        if request.actor_type == ActorType.SYSTEM:
            return self._decision(request, True, "System actor permitted.", "system-full-access")

        if request.actor_type == ActorType.AGENT:
            roles.add("agent")

        if request.actor_type == ActorType.VENDOR:
            roles.add("vendor")

        allowed_tenants = self.tenant_memberships.get(request.actor_id)
        if allowed_tenants is not None and request.tenant_id not in allowed_tenants:
            return self._decision(request, False, "Actor is not assigned to tenant.", "tenant-scope")

        if not roles:
            return self._decision(request, False, "No role grants were supplied.", "deny-by-default")

        if any(request.action in self.role_permissions.get(role, set()) for role in roles):
            return self._decision(request, True, "Role grants action.", "rbac-role-grant")

        return self._decision(request, False, "No role grants requested action.", "rbac-deny")

    def _decision(
        self,
        request: SecurityDecisionInput,
        allowed: bool,
        reason: str,
        policy_id: str,
    ) -> SecurityDecisionOutput:
        if self.audit_agent is not None:
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=request.actor_type,
                    actor_id=request.actor_id,
                    action=f"security.{request.action}",
                    entity_type=request.resource,
                    entity_id=request.tenant_id,
                    metadata={"allowed": allowed, "reason": reason, "policy_id": policy_id},
                )
            )
        return SecurityDecisionOutput(allowed=allowed, reason=reason, policy_id=policy_id)
