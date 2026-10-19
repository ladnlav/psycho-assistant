import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(
    db: Session,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: Any = None,
    data: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            data=data or {},
        )
    )
