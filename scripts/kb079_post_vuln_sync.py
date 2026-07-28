#!/usr/bin/env python3
"""KB-079: POST vuln sync batches to control plane (shared by Nuclei/Vuls pullers)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def post_batches(doc: dict, base_url: str, sync_key: str) -> int:
    batches = doc.get("batches") or []
    source = doc.get("source_platform") or "nuclei"
    if not batches:
        print("No findings to sync.")
        return 0
    total = 0
    for batch in batches:
        findings = batch["findings"]
        tenant = batch["tenant_short_code"]
        for i in range(0, len(findings), 100):
            chunk = findings[i : i + 100]
            body = {
                "tenant_short_code": tenant,
                "source_platform": source,
                "findings": chunk,
            }
            req = urllib.request.Request(
                base_url.rstrip("/") + "/integrations/vuln/sync",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Vuln-Sync-Key": sync_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                raise SystemExit(f"sync HTTP {e.code} for {tenant}: {detail}") from None
            results = data.get("results") or []
            created = sum(1 for r in results if r.get("action") == "created")
            updated = sum(1 for r in results if r.get("action") == "updated")
            recs = sum(1 for r in results if r.get("recommendation_action") == "created")
            total += len(results)
            print(
                f"tenant={data.get('short_code')} synced={len(results)} "
                f"created={created} updated={updated} recommendations_created={recs}"
            )
    return total


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: kb079_post_vuln_sync.py <batches.json> <control_plane_url> <sync_key>", file=sys.stderr)
        raise SystemExit(2)
    doc = json.loads(open(sys.argv[1], encoding="utf-8").read())
    total = post_batches(doc, sys.argv[2], sys.argv[3])
    print(f"KB-079 vuln sync complete — total rows: {total}")


if __name__ == "__main__":
    main()
