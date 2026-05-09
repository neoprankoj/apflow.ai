from collections.abc import Iterable
from uuid import UUID


def assert_tenant_scope(tenant_id: UUID, allowed_tenant_ids: Iterable[UUID]) -> bool:
    return tenant_id in set(allowed_tenant_ids)
