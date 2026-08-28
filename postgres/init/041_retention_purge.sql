-- KB-111 Phase 2: Batched retention purge for high-volume tenant tables.

BEGIN;

CREATE OR REPLACE FUNCTION purge_expired_tenant_data(retention_days integer DEFAULT 90)
RETURNS TABLE(table_name text, rows_deleted bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    cutoff timestamptz := now() - make_interval(days => GREATEST(retention_days, 1));
    batch_size constant integer := 5000;
    deleted bigint;
    total bigint;
BEGIN
    -- security_alerts
    total := 0;
    LOOP
        DELETE FROM security_alerts
        WHERE id IN (
            SELECT id
            FROM security_alerts
            WHERE created_at < cutoff
            ORDER BY created_at
            LIMIT batch_size
        );
        GET DIAGNOSTICS deleted = ROW_COUNT;
        total := total + deleted;
        EXIT WHEN deleted = 0;
        PERFORM pg_sleep(0.01);
    END LOOP;
    table_name := 'security_alerts';
    rows_deleted := total;
    RETURN NEXT;

    -- audit_logs
    total := 0;
    LOOP
        DELETE FROM audit_logs
        WHERE id IN (
            SELECT id
            FROM audit_logs
            WHERE created_at < cutoff
            ORDER BY created_at
            LIMIT batch_size
        );
        GET DIAGNOSTICS deleted = ROW_COUNT;
        total := total + deleted;
        EXIT WHEN deleted = 0;
        PERFORM pg_sleep(0.01);
    END LOOP;
    table_name := 'audit_logs';
    rows_deleted := total;
    RETURN NEXT;

    -- tenant_ndr_events (anchor on detected_at)
    total := 0;
    LOOP
        DELETE FROM tenant_ndr_events
        WHERE id IN (
            SELECT id
            FROM tenant_ndr_events
            WHERE detected_at < cutoff
            ORDER BY detected_at
            LIMIT batch_size
        );
        GET DIAGNOSTICS deleted = ROW_COUNT;
        total := total + deleted;
        EXIT WHEN deleted = 0;
        PERFORM pg_sleep(0.01);
    END LOOP;
    table_name := 'tenant_ndr_events';
    rows_deleted := total;
    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION purge_expired_tenant_data(integer) IS
    'Delete rows older than retention_days in 5k batches (security_alerts, audit_logs, tenant_ndr_events).';

COMMIT;
