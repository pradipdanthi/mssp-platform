-- KB-116: bounded retries for SOC notifier delivery.
ALTER TABLE notification_events
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN notification_events.attempts IS
    'Delivery attempts by soc_notifier; failed after SOC_NOTIFIER_MAX_ATTEMPTS.';
