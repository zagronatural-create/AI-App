CREATE INDEX IF NOT EXISTS idx_audit_event_time ON audit_logs(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_logs(actor_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_logs(action_type, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity_lookup ON audit_logs(entity_type, entity_id, event_time DESC);
