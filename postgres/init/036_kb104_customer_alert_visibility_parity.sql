-- KB-104: Customer portal alert counts match Admin for the same tenant.
-- False positives stay hidden. Normalized SOC/Wazuh alerts are customer-visible.
-- Customer APIs still return only customer-safe fields.

UPDATE security_alerts
SET customer_visible = true
WHERE customer_visible = false
  AND status <> 'false_positive';
