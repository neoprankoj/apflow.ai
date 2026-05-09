class APFlowError(Exception):
    """Base application exception."""


class SecurityDeniedError(APFlowError):
    """Raised when a tenant or RBAC policy denies access."""


class WorkflowDispatchError(APFlowError):
    """Raised when workflow orchestration cannot determine a next step."""
