from typing import Optional, Dict, Any
from apps.users.models import TelegramProfile
from apps.audit.models import AuditLog

class AuditService:
    """Service to record administrative actions and diffs."""

    @staticmethod
    def log(
        admin: Optional[TelegramProfile],
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        notes: str = ""
    ) -> AuditLog:
        """Create an immutable audit log entry."""
        return AuditLog.objects.create(
            admin=admin,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before_state=before_state or {},
            after_state=after_state or {},
            notes=notes
        )
