from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from app.core.schemas import DocumentReference


class MockObjectStorage:
    def store(self, tenant_id: str, file_url: str, content: str | bytes | None) -> tuple[str, str]:
        checksum_source = content if content is not None else file_url
        if isinstance(checksum_source, str):
            checksum_bytes = checksum_source.encode("utf-8")
        else:
            checksum_bytes = checksum_source
        checksum = sha256(checksum_bytes).hexdigest()
        return f"mock://object-storage/{tenant_id}/{checksum}", checksum


class InMemoryStorageAdapter:
    provider_name = "memory"

    def __init__(self) -> None:
        self._documents: dict[str, bytes] = {}

    def get_provider_name(self) -> str:
        return self.provider_name

    def save_document(
        self,
        tenant_id: UUID,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentReference:
        document_id = uuid4()
        checksum = sha256(content).hexdigest()
        storage_key = f"{tenant_id}/{document_id}-{checksum}-{Path(file_name).name}"
        self._documents[storage_key] = content
        return DocumentReference(
            document_id=document_id,
            tenant_id=tenant_id,
            storage_provider=self.provider_name,
            storage_key=storage_key,
            content_type=content_type,
        )

    def get_document(self, document_reference: DocumentReference) -> bytes:
        return self._documents[document_reference.storage_key]

    def delete_document(self, document_reference: DocumentReference) -> None:
        self._documents.pop(document_reference.storage_key, None)

    def health_check(self) -> dict:
        return {"provider": self.provider_name, "status": "ok", "configured": True}


class FileSystemStorageAdapter:
    provider_name = "filesystem"

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)

    def get_provider_name(self) -> str:
        return self.provider_name

    def save_document(
        self,
        tenant_id: UUID,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> DocumentReference:
        document_id = uuid4()
        tenant_path = self.root_path / str(tenant_id)
        tenant_path.mkdir(parents=True, exist_ok=True)
        suffix = Path(file_name).suffix.lower()
        storage_key = f"{tenant_id}/{document_id}{suffix}"
        (self.root_path / storage_key).write_bytes(content)
        return DocumentReference(
            document_id=document_id,
            tenant_id=tenant_id,
            storage_provider=self.provider_name,
            storage_key=storage_key,
            content_type=content_type,
        )

    def get_document(self, document_reference: DocumentReference) -> bytes:
        return (self.root_path / document_reference.storage_key).read_bytes()

    def delete_document(self, document_reference: DocumentReference) -> None:
        path = self.root_path / document_reference.storage_key
        if path.exists():
            path.unlink()

    def health_check(self) -> dict:
        return {
            "provider": self.provider_name,
            "status": "ok" if self.root_path.exists() else "missing_path",
            "configured": self.root_path.exists(),
        }
