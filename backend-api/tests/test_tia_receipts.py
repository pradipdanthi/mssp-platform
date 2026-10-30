"""Authenticated delivery receipts: submitted, delivered and acknowledged stay distinct.

LOCAL tests: real Postgres, the real FastAPI app, a recording transport. No
provider is contacted. Signatures use a synthetic app secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

import test_tia_failure_path as base
import tia_testenv
from app.services import tia_outbox, tia_review, tia_schema
from test_tia_acceptance import AcceptanceBase, OFFICER

SECRET = "synthetic-app-secret"
VERIFY = "synthetic-verify-token"
URL = "/api/v1/notifications/whatsapp/webhook"


def sign(raw: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def receipt_body(message_id: str, status: str, error: dict | None = None) -> bytes:
    st = {"id": message_id, "status": status, "timestamp": "1760000000", "recipient_id": "15550001111"}
    if error:
        st["errors"] = [error]
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {"statuses": [st]}}]}]}).encode()


class ReceiptTests(AcceptanceBase):
    def setUp(self) -> None:
        super().setUp()
        env = patch.dict(os.environ, {"WHATSAPP_APP_SECRET": SECRET, "WHATSAPP_WEBHOOK_VERIFY_TOKEN": VERIFY})
        env.start()
        self.addCleanup(env.stop)
        tia_testenv.require_test_modules()
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def submitted_page(self):
        a = self.alert("critical")
        self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual(row["state"], "submitted")
        return a, row["provider_message_id"]

    def post(self, raw: bytes, signature="auto"):
        headers = {"Content-Type": "application/json"}
        if signature == "auto":
            headers["X-Hub-Signature-256"] = sign(raw)
        elif signature:
            headers["X-Hub-Signature-256"] = signature
        return self.client.post(URL, content=raw, headers=headers)

    # -- authentication --------------------------------------------------
    def test_handshake_requires_the_verify_token(self) -> None:
        ok = self.client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"})
        self.assertEqual((ok.status_code, ok.text), (200, "12345"))
        self.assertEqual(self.client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}).status_code, 403)

    def test_unsigned_or_wrongly_signed_receipts_change_nothing(self) -> None:
        a, mid = self.submitted_page()
        raw = receipt_body(mid, "delivered")
        self.assertEqual(self.post(raw, signature=None).status_code, 401)
        self.assertEqual(self.post(raw, signature=sign(raw, "other-secret")).status_code, 401)
        self.assertEqual(self.post(raw, signature="sha256=" + "0" * 64).status_code, 401)
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    def test_a_tampered_body_fails_its_signature(self) -> None:
        a, mid = self.submitted_page()
        raw = receipt_body(mid, "delivered")
        signature = sign(raw)
        tampered = raw.replace(b"delivered", b"delivered ")
        self.assertEqual(self.post(tampered, signature=signature).status_code, 401)
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    def test_without_a_configured_secret_every_receipt_is_refused(self) -> None:
        a, mid = self.submitted_page()
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": ""}):
            raw = receipt_body(mid, "delivered")
            self.assertEqual(self.post(raw, signature=sign(raw, "")).status_code, 503)
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    # -- states ----------------------------------------------------------
    def test_a_signed_delivered_receipt_moves_submitted_to_delivered_only(self) -> None:
        a, mid = self.submitted_page()
        r = self.post(receipt_body(mid, "delivered"))
        self.assertEqual((r.status_code, r.json()["applied"]), (200, {"delivered": 1}))
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["delivery_evidence"]), ("delivered", "provider_delivery_receipt"))
        self.assertIsNone(row["acknowledged_at"], "delivery is not human acknowledgement")
        self.assertEqual(self.item(a)["status"], "open", "the review item is untouched")
        self.assertEqual(self.item(a)["notification_state"], "page_delivered")

    def test_a_read_receipt_is_still_not_an_acknowledgement(self) -> None:
        a, mid = self.submitted_page()
        self.post(receipt_body(mid, "read"))
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["delivery_evidence"]), ("delivered", "provider_read_receipt"))
        self.assertIsNone(row["acknowledged_by"])
        self.assertEqual(self.item(a)["status"], "open")

    def test_duplicate_and_out_of_order_receipts_are_idempotent(self) -> None:
        a, mid = self.submitted_page()
        self.post(receipt_body(mid, "read"))
        again = self.post(receipt_body(mid, "delivered"))  # arrives after read
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.post(receipt_body(mid, "read")).status_code, 200)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["delivery_evidence"]), ("delivered", "provider_read_receipt"))

    def test_sent_status_changes_nothing(self) -> None:
        a, mid = self.submitted_page()
        self.post(receipt_body(mid, "sent"))
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    def test_unknown_message_id_is_reported_unmatched_not_applied(self) -> None:
        r = self.post(receipt_body("wamid.nobody", "delivered"))
        self.assertEqual((r.status_code, r.json()["applied"]), (200, {"unmatched": 1}))

    def test_a_provider_failure_after_acceptance_retries_then_fails(self) -> None:
        a, mid = self.submitted_page()
        err = {"code": 131026, "title": "Message undeliverable"}
        r = self.post(receipt_body(mid, "failed", err))
        self.assertEqual(r.json()["applied"], {"retry": 1})
        row = self.pages(a)[0]
        self.assertEqual(row["state"], "required")
        self.assertIn("131026", row["last_error"])
        self.assertNotEqual(self.item(a)["notification_state"], "page_submitted")
        # exhaust attempts: the next provider failure is final
        self.execute("UPDATE tia_notifications SET next_attempt_at = now() - interval '1 second', attempts = max_attempts - 1 WHERE alert_id = %s::uuid;", (a,))
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual(row["state"], "submitted")
        r = self.post(receipt_body(row["provider_message_id"], "failed", err))
        self.assertEqual(r.json()["applied"], {"failed": 1})
        self.assertEqual(self.pages(a)[0]["state"], "failed")
        self.assertEqual(self.item(a)["notification_state"], "page_failed")

    def test_acknowledgement_is_a_separate_authenticated_human_action(self) -> None:
        a, mid = self.submitted_page()
        self.post(receipt_body(mid, "delivered"))
        item = self.item(a)
        tia_review.acknowledge(item["id"], OFFICER, "seen")
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["acknowledged_by"]), ("acknowledged", OFFICER["email"]))
        self.post(receipt_body(mid, "read"))  # a late read receipt cannot undo or replace it
        self.assertEqual(self.pages(a)[0]["state"], "acknowledged")

    # -- visibility ------------------------------------------------------
    def test_unconfigured_receipts_are_a_visible_warning_and_delivery_stays_unknown(self) -> None:
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "", "WHATSAPP_WEBHOOK_VERIFY_TOKEN": ""}):
            codes = {f["code"]: f["severity"] for f in tia_schema.notification_config_faults()}
        self.assertEqual(codes.get("delivery_receipts_not_configured"), "warning")
        a = self.alert("critical")
        self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        tia_outbox.deliver_pending(500)
        self.assertEqual(self.pages(a)[0]["state"], "submitted", "without receipts a page never claims delivery")

    def test_unconfigured_paging_is_still_a_fault(self) -> None:
        with patch.dict(os.environ, {"SOC_ONCALL_WHATSAPP": ""}):
            codes = {f["code"]: f["severity"] for f in tia_schema.notification_config_faults()}
        self.assertEqual(codes.get("oncall_roster_not_configured"), "fault")


if __name__ == "__main__":
    unittest.main()
