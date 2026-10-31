-- Gate3: allow provider-independent local file sink + telegram adapter
-- (telegram adapter already existed in soc_notifier.py but was blocked by CHECK).

ALTER TABLE notification_events
  DROP CONSTRAINT IF EXISTS notification_events_notification_type_check;

ALTER TABLE notification_events
  ADD CONSTRAINT notification_events_notification_type_check
  CHECK (
    notification_type = ANY (
      ARRAY[
        'whatsapp'::text,
        'email'::text,
        'sms'::text,
        'webhook'::text,
        'telegram'::text,
        'file'::text
      ]
    )
  );
