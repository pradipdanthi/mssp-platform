"""Phase 3: login rate limiting and TOTP MFA."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.routes import auth as auth_routes
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MfaAuthenticateRequest,
    MfaCompleteSetupRequest,
    TokenResponse,
    UserPublic,
)
from app.services.auth_service import InvalidCredentialsError, to_public_user
from app.services.login_rate_limit import (
    LOGIN_RATE_LIMIT_MAX,
    LoginRateLimitExceeded,
    check_login_rate_limit,
    record_failed_login,
    reset_login_rate_limit,
)
from app.services.mfa_service import (
    _hash_recovery_code,
    _totp_at,
    generate_recovery_codes,
    normalize_recovery_code,
    verify_mfa_code,
    verify_totp_code,
)

USER_ROW = {
    "id": "user-1",
    "tenant_id": None,
    "user_type": "admin",
    "role": "platform_admin",
    "full_name": "Test Admin",
    "email": "admin@example.local",
    "phone": None,
    "status": "active",
    "password_hash": "hash",
    "mfa_secret": None,
    "is_mfa_enabled": False,
    "last_login_at": None,
    "created_at": None,
    "updated_at": None,
    "tenant_short_code": None,
    "tenant_name": None,
}

MFA_USER_ROW = {
    **USER_ROW,
    "mfa_secret": "JBSWY3DPEHPK3PXP",
    "is_mfa_enabled": True,
}

CUSTOMER_USER_ROW = {
    **USER_ROW,
    "id": "cust-1",
    "role": "customer_admin",
    "user_type": "customer",
    "tenant_id": "tenant-1",
    "tenant_short_code": "alpha",
    "tenant_name": "Alpha",
    "tenant_enforce_mfa": True,
    "is_mfa_enabled": False,
    "mfa_secret": None,
}


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, tuple[int, int | None]] = {}

    def get(self, key: str):
        item = self.store.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at < int(time.time()):
            del self.store[key]
            return None
        return str(value)

    def incr(self, key: str) -> int:
        current = int(self.get(key) or 0) + 1
        expires_at = self.store.get(key, (0, None))[1]
        self.store[key] = (current, expires_at)
        return current

    def expire(self, key: str, ttl: int) -> None:
        value = int(self.get(key) or 0)
        self.store[key] = (value, int(time.time()) + ttl)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)

    def pipeline(self):
        client = self

        class _Pipe:
            def incr(self, key: str):
                client.incr(key)
                return self

            def expire(self, key: str, ttl: int):
                client.expire(key, ttl)
                return self

            def execute(self):
                return None

        return _Pipe()


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()

    @patch("app.services.login_rate_limit.redis_client")
    def test_blocks_after_five_failed_attempts(self, mock_redis):
        mock_redis.return_value = self.fake
        for _ in range(LOGIN_RATE_LIMIT_MAX):
            record_failed_login(client_ip="1.2.3.4", email="user@example.local")
        with self.assertRaises(LoginRateLimitExceeded):
            check_login_rate_limit(client_ip="1.2.3.4", email="user@example.local")

    @patch("app.services.login_rate_limit.redis_client")
    def test_resets_after_success(self, mock_redis):
        mock_redis.return_value = self.fake
        record_failed_login(client_ip="1.2.3.4", email="user@example.local")
        reset_login_rate_limit(client_ip="1.2.3.4", email="user@example.local")
        check_login_rate_limit(client_ip="1.2.3.4", email="user@example.local")


class AuthRouteTests(unittest.TestCase):
    def _request(self, ip: str = "10.0.0.1") -> MagicMock:
        request = MagicMock()
        request.client = MagicMock(host=ip)
        request.headers = {}
        return request

    @patch("app.api.routes.auth.reset_login_rate_limit")
    @patch("app.api.routes.auth.record_failed_login")
    @patch("app.api.routes.auth.check_login_rate_limit")
    @patch("app.api.routes.auth.verify_user_credentials")
    def test_login_returns_jwt_when_mfa_disabled(
        self,
        mock_verify,
        _mock_check,
        _mock_record,
        _mock_reset,
    ):
        mock_verify.return_value = USER_ROW.copy()
        with patch("app.api.routes.auth.get_user_by_id", return_value=USER_ROW):
            with patch("app.api.routes.auth._touch_last_login"):
                with patch("app.api.routes.auth.audit_from_user"):
                    response = auth_routes.login(
                        LoginRequest(email="admin@example.local", password="secret"),
                        self._request(),
                    )
        self.assertIsInstance(response, LoginResponse)
        self.assertFalse(response.mfa_required)
        self.assertIsNone(response.mfa_token)
        self.assertTrue(response.access_token)
        self.assertEqual(response.token_type, "bearer")
        self.assertIsNotNone(response.user)
        self.assertIsNone(response.user.get("mfa_secret"))

    @patch("app.api.routes.auth.reset_login_rate_limit")
    @patch("app.api.routes.auth.check_login_rate_limit")
    @patch("app.api.routes.auth.verify_user_credentials")
    @patch("app.api.routes.auth.issue_mfa_pending_token", return_value="pending-token")
    def test_login_returns_mfa_required_when_enabled(
        self,
        _mock_token,
        mock_verify,
        _mock_check,
        _mock_reset,
    ):
        mock_verify.return_value = MFA_USER_ROW.copy()
        response = auth_routes.login(
            LoginRequest(email="admin@example.local", password="secret"),
            self._request(),
        )
        self.assertIsInstance(response, LoginResponse)
        self.assertTrue(response.mfa_required)
        self.assertEqual(response.mfa_token, "pending-token")
        self.assertIsNone(response.access_token)
        self.assertIsNone(response.token_type)
        self.assertIsNone(response.expires_in)
        self.assertIsNone(response.user)

    @patch("app.api.routes.auth.record_failed_login")
    @patch("app.api.routes.auth.check_login_rate_limit", side_effect=LoginRateLimitExceeded)
    def test_login_rate_limited_returns_429(self, _mock_check, _mock_record):
        with self.assertRaises(HTTPException) as ctx:
            auth_routes.login(
                LoginRequest(email="admin@example.local", password="bad"),
                self._request(),
            )
        self.assertEqual(ctx.exception.status_code, 429)

    @patch("app.api.routes.auth.reset_login_rate_limit")
    @patch("app.api.routes.auth.check_login_rate_limit")
    @patch("app.api.routes.auth.verify_user_credentials")
    @patch("app.api.routes.auth.begin_mfa_setup")
    @patch("app.api.routes.auth.issue_mfa_setup_token", return_value="setup-token")
    def test_login_returns_mfa_setup_required_for_enforced_tenant(
        self,
        _mock_setup_token,
        mock_begin,
        mock_verify,
        _mock_check,
        _mock_reset,
    ):
        mock_verify.return_value = CUSTOMER_USER_ROW.copy()
        response = auth_routes.login(
            LoginRequest(
                email="customer@example.local",
                password="secret",
                portal="customer",
            ),
            self._request(),
        )
        self.assertTrue(response.mfa_setup_required)
        self.assertEqual(response.setup_token, "setup-token")
        self.assertFalse(response.mfa_required)
        mock_begin.assert_called_once_with("cust-1")

    @patch("app.api.routes.auth._issue_login_token")
    @patch("app.api.routes.auth._touch_last_login")
    @patch("app.api.routes.auth.get_user_by_id", return_value=MFA_USER_ROW)
    @patch("app.api.routes.auth.resolve_mfa_pending_token", return_value="user-1")
    @patch("app.api.routes.auth.authenticate_mfa_factor", return_value=(True, "totp"))
    def test_mfa_authenticate_issues_jwt(
        self,
        _mock_factor,
        _mock_resolve,
        _mock_get_user,
        _mock_touch,
        mock_issue,
    ):
        mock_issue.return_value = TokenResponse(
            access_token="jwt-token",
            token_type="bearer",
            expires_in=3600,
            user=UserPublic(**to_public_user(MFA_USER_ROW)),
        )
        response = auth_routes.mfa_authenticate(
            MfaAuthenticateRequest(mfa_token="pending-token", code="123456"),
            self._request(),
        )
        self.assertEqual(response.access_token, "jwt-token")

    @patch("app.api.routes.auth.get_user_by_id", return_value=MFA_USER_ROW)
    @patch("app.api.routes.auth.resolve_mfa_pending_token", return_value="user-1")
    @patch("app.api.routes.auth.authenticate_mfa_factor", return_value=(False, "totp"))
    def test_mfa_authenticate_rejects_invalid_totp(
        self,
        _mock_factor,
        _mock_resolve,
        _mock_get_user,
    ):
        with patch("app.api.routes.auth.write_audit_event"):
            with self.assertRaises(HTTPException) as ctx:
                auth_routes.mfa_authenticate(
                    MfaAuthenticateRequest(mfa_token="pending-token", code="000000"),
                    self._request(),
                )
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.api.routes.auth._issue_login_token")
    @patch("app.api.routes.auth._touch_last_login")
    @patch("app.api.routes.auth.get_user_by_id", return_value=MFA_USER_ROW)
    @patch("app.api.routes.auth.resolve_mfa_pending_token", return_value="user-1")
    @patch("app.api.routes.auth.authenticate_mfa_factor", return_value=(True, "recovery"))
    def test_mfa_authenticate_accepts_recovery_code(
        self,
        _mock_factor,
        _mock_resolve,
        _mock_get_user,
        _mock_touch,
        mock_issue,
    ):
        mock_issue.return_value = TokenResponse(
            access_token="jwt-token",
            token_type="bearer",
            expires_in=3600,
            user=UserPublic(**to_public_user(MFA_USER_ROW)),
        )
        response = auth_routes.mfa_authenticate(
            MfaAuthenticateRequest(mfa_token="pending-token", code="ABCD-EFGH"),
            self._request(),
        )
        self.assertEqual(response.access_token, "jwt-token")

    @patch("app.api.routes.auth.complete_mfa_setup_with_recovery")
    @patch("app.api.routes.auth.resolve_mfa_setup_token", return_value="cust-1")
    @patch("app.api.routes.auth._issue_login_token")
    @patch("app.api.routes.auth._touch_last_login")
    @patch("app.api.routes.auth.get_user_by_id", return_value=CUSTOMER_USER_ROW)
    @patch("app.api.routes.auth.audit_from_user")
    def test_complete_setup_returns_recovery_codes_and_jwt(
        self,
        _mock_audit,
        _mock_get_user,
        _mock_touch,
        mock_issue,
        _mock_resolve,
        mock_complete,
    ):
        mock_complete.return_value = ["AAAA-BBBB", "CCCC-DDDD"]
        mock_issue.return_value = TokenResponse(
            access_token="jwt-token",
            token_type="bearer",
            expires_in=3600,
            user=UserPublic(**to_public_user({**CUSTOMER_USER_ROW, "is_mfa_enabled": True})),
        )
        response = auth_routes.mfa_complete_setup(
            MfaCompleteSetupRequest(setup_token="setup-token", code="123456"),
            self._request(),
        )
        self.assertEqual(response.recovery_codes, ["AAAA-BBBB", "CCCC-DDDD"])
        self.assertEqual(response.access_token, "jwt-token")
        mock_complete.assert_called_once_with("cust-1", "123456")


class RecoveryCodeTests(unittest.TestCase):
    def test_generate_recovery_codes_format(self):
        codes = generate_recovery_codes(8)
        self.assertEqual(len(codes), 8)
        for code in codes:
            self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")

    def test_normalize_recovery_code_accepts_dashless(self):
        self.assertEqual(normalize_recovery_code("wxyz 2345"), "WXYZ-2345")

    @patch("app.services.mfa_service.fetch_one")
    @patch("app.services.mfa_service.execute")
    def test_recovery_code_consumed_after_use(self, mock_execute, mock_fetch):
        from app.services.mfa_service import verify_and_consume_recovery_code

        code = "WXYZ-2345"
        stored = [{"hash": _hash_recovery_code(code), "used_at": None}]
        mock_fetch.return_value = {"mfa_recovery_codes": stored}
        self.assertTrue(verify_and_consume_recovery_code("user-1", code))
        mock_execute.assert_called_once()


class TotpHelperTests(unittest.TestCase):
    def test_verify_totp_accepts_current_code(self):
        secret = "JBSWY3DPEHPK3PXP"
        counter = int(time.time()) // 30
        code = _totp_at(secret, counter)
        self.assertTrue(verify_totp_code(secret, code))

    def test_verify_totp_rejects_wrong_code(self):
        self.assertFalse(verify_totp_code("JBSWY3DPEHPK3PXP", "000000"))

    def test_verify_totp_accepts_code_with_spaces(self):
        secret = "JBSWY3DPEHPK3PXP"
        counter = int(time.time()) // 30
        code = _totp_at(secret, counter)
        spaced = f"{code[:3]} {code[3:]}"
        self.assertTrue(verify_totp_code(secret, spaced))


class LoginRouteUnitTests(unittest.TestCase):
    @patch("app.api.routes.auth.reset_login_rate_limit")
    @patch("app.api.routes.auth.check_login_rate_limit")
    @patch("app.api.routes.auth.verify_user_credentials", side_effect=InvalidCredentialsError)
    @patch("app.api.routes.auth.record_failed_login")
    @patch("app.api.routes.auth.write_audit_event")
    def test_failed_login_records_rate_limit(
        self,
        _mock_audit,
        mock_record,
        _mock_verify,
        _mock_check,
        _mock_reset,
    ):
        request = MagicMock()
        request.client = MagicMock(host="10.0.0.1")
        request.headers = {}
        with self.assertRaises(HTTPException) as ctx:
            auth_routes.login(
                LoginRequest(email="user@example.local", password="bad"),
                request,
            )
        self.assertEqual(ctx.exception.status_code, 401)
        mock_record.assert_called_once()


class AdminMfaManagementTests(unittest.TestCase):
    USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    @patch("app.api.routes.user_management._fetch_user_detail")
    @patch("app.api.routes.user_management.admin_reset_mfa")
    @patch("app.api.routes.user_management.audit_from_user")
    def test_platform_admin_can_reset_mfa(
        self,
        _mock_audit,
        mock_reset,
        mock_fetch,
    ):
        from uuid import UUID

        from app.api.routes import user_management as um

        mock_fetch.side_effect = [
            {"id": self.USER_ID, "email": "user@example.local", "tenant_id": None},
            {
                "id": self.USER_ID,
                "email": "user@example.local",
                "tenant_id": None,
                "is_mfa_enabled": False,
            },
        ]
        admin = {"id": "admin-1", "role": "platform_admin", "email": "admin@example.local"}
        result = um.reset_user_mfa(UUID(self.USER_ID), admin)
        mock_reset.assert_called_once_with(self.USER_ID)
        self.assertFalse(result["is_mfa_enabled"])

    @patch("app.api.routes.user_management._fetch_user_detail")
    @patch("app.api.routes.user_management.admin_enforce_mfa")
    @patch("app.api.routes.user_management.audit_from_user")
    def test_platform_admin_can_enforce_mfa(
        self,
        _mock_audit,
        mock_enforce,
        mock_fetch,
    ):
        from uuid import UUID

        from app.api.routes import user_management as um

        mock_fetch.return_value = {
            "id": self.USER_ID,
            "email": "user@example.local",
            "tenant_id": None,
        }
        mock_enforce.return_value = {
            "secret": "JBSWY3DPEHPK3PXP",
            "otpauth_url": "otpauth://totp/test",
        }
        admin = {"id": "admin-1", "role": "platform_admin", "email": "admin@example.local"}
        result = um.enforce_user_mfa(UUID(self.USER_ID), admin)
        self.assertEqual(result["secret"], "JBSWY3DPEHPK3PXP")

    @patch("app.api.routes.user_management.list_mfa_status_rows", return_value=[])
    def test_platform_admin_can_list_mfa_status(self, mock_list):
        from app.api.routes import user_management as um

        admin = {"id": "admin-1", "role": "platform_admin", "email": "admin@example.local"}
        result = um.get_users_mfa_status(admin)
        mock_list.assert_called_once()
        self.assertEqual(result, {"users": []})

    def test_non_platform_admin_forbidden_on_admin_mfa_routes(self):
        from app.api.dependencies import require_roles
        from fastapi import HTTPException

        dep = require_roles("platform_admin")
        with self.assertRaises(HTTPException) as ctx:
            dep({"id": "soc-1", "role": "soc_manager", "status": "active"})
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
