"""Append-only audit notes. Callers commit the surrounding transaction."""
from app import db
from app.operations_models import AuditEvent


def write_audit(*, action, entity_type, message, business_id=None, branch_id=None,
                actor_user_id=None, entity_id=None):
    event = AuditEvent(
        business_id=business_id,
        branch_id=branch_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        message=message[:300],
    )
    db.session.add(event)
    return event
