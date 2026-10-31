"""EDR callback must use a dedicated key and reject SOC sync alias / wrong agent."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes import edr as edr_routes


class EdrCallbackAuthTests(unittest.TestCase):
    def test_dedicated_key_from_file_not_soc_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            edr_path = Path(tmp) / "edr.key"
            sync_path = Path(tmp) / "sync.key"
            edr_path.write_text("edr-dedicated-secret-value-001", encoding="utf-8")
            sync_path.write_text("soc-sync-secret-value-should-not-win", encoding="utf-8")
            env = {
                "EDR_CALLBACK_API_KEY": "",
                "EDR_CALLBACK_API_KEY_FILE": str(edr_path),
                "SOC_SYNC_API_KEY": "soc-sync-secret-value-should-not-win",
            }
            with patch.dict(os.environ, env, clear=False):
                with patch.object(
                    edr_routes,
                    "_read_secret_file",
                    side_effect=lambda *paths: (
                        Path(paths[0]).read_text(encoding="utf-8").strip()
                        if paths and Path(paths[0]).is_file()
                        else ""
                    ),
                ):
                    self.assertEqual(
                        edr_routes._edr_callback_key(),
                        "edr-dedicated-secret-value-001",
                    )

    def test_soc_sync_header_alone_rejected(self):
        with patch.object(edr_routes, "_edr_callback_key", return_value="edr-only"):
            with self.assertRaises(HTTPException) as raised:
                edr_routes._require_callback_auth(
                    x_edr_callback_key=None,
                    x_soc_sync_key="edr-only",
                )
            self.assertEqual(raised.exception.status_code, 401)

    def test_edr_header_accepted(self):
        with patch.object(edr_routes, "_edr_callback_key", return_value="edr-only"):
            edr_routes._require_callback_auth(
                x_edr_callback_key="edr-only",
                x_soc_sync_key="anything-else",
            )


class EdrCallbackAgentBindTests(unittest.TestCase):
    def test_wrong_agent_rejected(self):
        from app.services import edr_actions

        with patch.object(
            edr_actions,
            "fetch_one",
            return_value={
                "id": "11111111-1111-1111-1111-111111111111",
                "tenant_id": "22222222-2222-2222-2222-222222222222",
                "action_type": "ISOLATE_HOST",
                "target_agent_id": "010",
                "current_status": "executing",
            },
        ):
            with self.assertRaises(ValueError) as raised:
                edr_actions.apply_action_callback(
                    execution_id="11111111-1111-1111-1111-111111111111",
                    status="success",
                    agent_id="999",
                    payload={"applied": True},
                )
            self.assertIn("does not match", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
