#!/usr/bin/env bash
# KB-087: Validate P0 Cloud-Readiness & Multi-Platform EDR Parity
set -uo pipefail
cd /opt/mssp-control

PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=== KB-087 Cloud Readiness Validation ==="
echo ""

# --- 1. Windows Active Response Scripts ---
echo "--- 1. Windows Active Response Parity ---"
for script in mssp-isolate-host.py mssp-kill-process.py mssp-block-hash.py; do
    f="deploy/wazuh-active-response/windows/$script"
    if [[ -f "$f" ]]; then
        # Check valid Python syntax
        if python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
            pass "$script syntax valid"
        else
            fail "$script syntax error"
        fi
    else
        fail "$script missing"
    fi
done

# Check dispatch routing in edr_actions.py
if grep -q "_resolve_ar_command" backend-api/app/services/edr_actions.py; then
    pass "OS-aware AR dispatch routing present"
else
    fail "OS-aware AR dispatch routing missing"
fi

if grep -q "WIN_ISOLATE_AR_COMMAND" backend-api/app/services/edr_actions.py; then
    pass "Windows AR command constants defined"
else
    fail "Windows AR command constants missing"
fi

if grep -q "get_agent_os" backend-api/app/services/wazuh_client.py; then
    pass "get_agent_os helper present in wazuh_client"
else
    fail "get_agent_os helper missing"
fi

echo ""

# --- 2. Connection Pool ---
echo "--- 2. Database Connection Pooling ---"
if grep -q "psycopg_pool" backend-api/app/db/session.py; then
    pass "psycopg_pool imported in session.py"
else
    fail "psycopg_pool not in session.py"
fi

if grep -q "DB_POOL_MIN_SIZE" backend-api/app/db/session.py; then
    pass "Pool min_size env var configured"
else
    fail "Pool min_size env var missing"
fi

if grep -q "DB_POOL_MAX_SIZE" backend-api/app/db/session.py; then
    pass "Pool max_size env var configured"
else
    fail "Pool max_size env var missing"
fi

if grep -q "ConnectionPool" backend-api/app/db/session.py; then
    pass "ConnectionPool class used"
else
    fail "ConnectionPool not used"
fi

if grep -q "psycopg_pool" backend-api/requirements.txt; then
    pass "psycopg_pool in requirements.txt"
else
    fail "psycopg_pool missing from requirements.txt"
fi

echo ""

# --- 3. Streaming Forensic Uploads + S3 ---
echo "--- 3. Streaming Forensics & S3 ---"
if grep -q "write_upload_stream" backend-api/app/services/edr_forensics_storage.py; then
    pass "write_upload_stream function present"
else
    fail "write_upload_stream missing"
fi

if grep -q "request.stream()" backend-api/app/api/routes/edr.py; then
    pass "Upload route uses request.stream()"
else
    fail "Upload route still buffers full body"
fi

if grep -q "FORENSICS_SIGNING_SECRET" backend-api/app/services/edr_forensics_storage.py; then
    pass "Separate FORENSICS_SIGNING_SECRET configured"
else
    fail "FORENSICS_SIGNING_SECRET not separated"
fi

if grep -q "_s3_write" backend-api/app/services/edr_forensics_storage.py; then
    pass "S3 write backend implemented"
else
    fail "S3 write backend missing"
fi

if grep -q "boto3" backend-api/requirements.txt; then
    pass "boto3 in requirements.txt"
else
    fail "boto3 missing from requirements.txt"
fi

echo ""

# --- 4. Async Dispatch + Sweeper ---
echo "--- 4. Async EDR Dispatch & Sweeper ---"
if grep -q "asyncio.to_thread" backend-api/app/api/routes/edr.py; then
    pass "EDR dispatch wrapped in asyncio.to_thread"
else
    fail "EDR dispatch still blocking"
fi

if [[ -f "backend-api/app/services/edr_sweeper.py" ]]; then
    pass "edr_sweeper.py exists"
else
    fail "edr_sweeper.py missing"
fi

if grep -q "edr_sweeper_loop" backend-api/app/main.py; then
    pass "Sweeper registered in main.py startup"
else
    fail "Sweeper not registered in main.py"
fi

if grep -q "EDR_STUCK_TIMEOUT" backend-api/app/services/edr_sweeper.py; then
    pass "Stuck timeout configurable via env"
else
    fail "Stuck timeout not configurable"
fi

echo ""

# --- 5. Environment-Driven Config ---
echo "--- 5. Environment-Driven Configuration ---"
if grep -q "WAZUH_MANAGER_HOST" backend-api/app/core/config.py; then
    pass "WAZUH_MANAGER_HOST in centralized config"
else
    fail "WAZUH_MANAGER_HOST not centralized"
fi

if grep -q "CONTROL_PLANE_URL" backend-api/app/core/config.py; then
    pass "CONTROL_PLANE_URL in centralized config"
else
    fail "CONTROL_PLANE_URL not centralized"
fi

if grep -q "SHUFFLE_WEBHOOK_URL" backend-api/app/core/config.py; then
    pass "SHUFFLE_WEBHOOK_URL in centralized config"
else
    fail "SHUFFLE_WEBHOOK_URL not centralized"
fi

if grep -q "192.168.0.211" backend-api/app/core/config.py; then
    pass "LAN default for Wazuh Manager preserved"
else
    fail "LAN default for Wazuh Manager missing"
fi

if grep -q "192.168.0.201" backend-api/app/core/config.py; then
    pass "LAN default for Control Plane preserved"
else
    fail "LAN default for Control Plane missing"
fi

if grep -q "get_infra_settings" backend-api/app/services/wazuh_client.py; then
    pass "wazuh_client uses centralized infra config"
else
    fail "wazuh_client still uses hardcoded URL"
fi

echo ""
echo "========================================"
echo "PASSED: $PASS   FAILED: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "RESULT: ALL PASS"
else
    echo "RESULT: $FAIL FAILURES — review above"
    exit 1
fi
