from typing import Protocol
from uuid import UUID

from app.core.schemas import DocumentReference


class StorageAdapterProtocol(Protocol):
    def get_provider_name(self) -> str: ...

    def save_document(
        self,
        tenant_id: UUID,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentReference: ...

    def get_document(self, document_reference: DocumentReference) -> bytes: ...

    def delete_document(self, document_reference: DocumentReference) -> None: ...

    def health_check(self) -> dict: ...
