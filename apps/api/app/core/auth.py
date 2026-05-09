from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import os
from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.schemas import (
    CurrentUserContext,
    Permission,
    TenantMembershipSchema,
    TenantRecordSchema,
    UserRecordSchema,
    UserRole,
)


ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.OWNER: set(Permission),
    UserRole.ADMIN: set(Permission),
    UserRole.CONTROLLER: {
        Permission.INVOICE_READ,
        Permission.INVOICE_PROCESS,
        Permission.INVOICE_APPROVE,
        Permission.INVOICE_EXPORT_ERP,
        Permission.REVIEW_READ,
        Permission.REVIEW_CORRECT,
        Permission.ERP_READ,
        Permission.ERP_SYNC,
        Permission.AUDIT_READ,
        Permission.NOTIFICATION_READ,
    },
    UserRole.AP_MANAGER: {
        Permission.INVOICE_READ,
        Permission.INVOICE_PROCESS,
        Permission.INVOICE_APPROVE,
        Permission.REVIEW_READ,
        Permission.REVIEW_CORRECT,
        Permission.ERP_READ,
        Permission.ERP_SYNC,
        Permission.NOTIFICATION_READ,
    },
    UserRole.APPROVER: {
        Permission.INVOICE_READ,
        Permission.INVOICE_APPROVE,
        Permission.REVIEW_READ,
        Permission.NOTIFICATION_READ,
    },
    UserRole.VIEWER: {
        Permission.INVOICE_READ,
        Permission.REVIEW_READ,
        Permission.ERP_READ,
        Permission.NOTIFICATION_READ,
    },
}


class AuthService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def hash_password(self, password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
        return "pbkdf2_sha256$260000$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()

    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(digest_b64)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def permissions_for_role(self, role: UserRole) -> list[Permission]:
        return sorted(ROLE_PERMISSIONS[role], key=str)

    def create_access_token(
        self,
        user: UserRecordSchema,
        tenant: TenantRecordSchema,
        membership: TenantMembershipSchema,
    ) -> str:
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
        payload: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": str(tenant.id),
            "role": str(membership.role),
            "permissions": [str(permission) for permission in self.permissions_for_role(membership.role)],
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])

    def build_context(self, user_id: UUID, tenant_id: UUID) -> CurrentUserContext | None:
        user = self.repository.get_user(user_id)
        tenant = self.repository.get_tenant(tenant_id)
        membership = self.repository.get_membership(tenant_id, user_id)
        if user is None or tenant is None or membership is None or not user.is_active:
            return None
        return CurrentUserContext(
            user=user,
            tenant=tenant,
            membership=membership,
            permissions=self.permissions_for_role(membership.role),
            auth_enabled=settings.auth_enabled,
            demo_mode=settings.demo_mode,
        )

    def demo_context(self) -> CurrentUserContext:
        tenant_id = UUID(settings.demo_tenant_id)
        tenant = self.repository.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.repository.create_tenant(
                tenant_id=tenant_id,
                name="Demo Tenant",
                slug="demo",
            )
        user = self.repository.get_user_by_email("demo@apflow.local")
        if user is None:
            user = self.repository.create_user(
                email="demo@apflow.local",
                full_name="Demo Admin",
                hashed_password=self.hash_password("demo-password"),
            )
        membership = self.repository.get_membership(tenant.id, user.id)
        if membership is None:
            membership = self.repository.create_membership(tenant.id, user.id, UserRole.OWNER)
        return CurrentUserContext(
            user=user,
            tenant=tenant,
            membership=membership,
            permissions=self.permissions_for_role(membership.role),
            auth_enabled=settings.auth_enabled,
            demo_mode=True,
        )

    def user_has_permission(self, context: CurrentUserContext, permission: Permission) -> bool:
        return permission in set(context.permissions)
