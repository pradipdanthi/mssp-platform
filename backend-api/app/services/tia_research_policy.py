"""Who may disclose what to whom, for research and for the investigation model.

Two independent gates must both pass before anything derived from a customer's data
leaves the platform:

  1. platform: the provider's domain is on TIA_RESEARCH_ALLOWED_DOMAINS (tia_research), and
  2. tenant:   that customer has a live grant for this provider AND this query class
               (tia_research_grants: who approved it, the customer's reference, a validity window).

The global allow-list says which sites the platform can reach. It never implies that a
customer approved sending anything about their environment there.

Query classes:
  public_identifier    CVE / ATT&CK ids. Public facts, nothing customer-derived: platform gate only.
  ip_reputation        a public address seen in the customer's telemetry.
  hash_reputation      a file hash seen in the customer's telemetry.
  behavioural_query    a sanitised description of behaviour (known public binary names only).
  investigation_context  the full evidence dossier to the investigation model.

Every attempt, sent or refused, is written to tia_research_disclosures.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

QUERY_CLASSES = ("public_identifier", "ip_reputation", "hash_reputation", "behavioural_query", "investigation_context")
CUSTOMER_DERIVED = frozenset(QUERY_CLASSES) - {"public_identifier"}

# Behavioural research: provider -> (host, candidate paths). The query is a binary name from
# _PUBLIC_BINARIES, never free text.
BEHAVIOUR_PROVIDERS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "lolbas": ("lolbas-project.github.io", ("/lolbas/Binaries/{name}/", "/lolbas/Libraries/{name}/", "/lolbas/Scripts/{name}/")),
}

# Binaries whose names are public knowledge and say nothing about a customer. A name that is
# not on this list (for example "acme_payroll_sync.exe") is never sent anywhere.
_PUBLIC_BINARIES = frozenset(
    """
    at.exe atbroker.exe bash.exe bitsadmin.exe certoc.exe certreq.exe certutil.exe cmd.exe cmdkey.exe cmstp.exe
    control.exe csc.exe cscript.exe desktopimgdownldr.exe diskshadow.exe dnscmd.exe esentutl.exe eventvwr.exe
    expand.exe explorer.exe extrac32.exe findstr.exe forfiles.exe ftp.exe gpscript.exe hh.exe ieexec.exe
    infdefaultinstall.exe installutil.exe jsc.exe makecab.exe mavinject.exe microsoft.workflow.compiler.exe
    mmc.exe msbuild.exe msconfig.exe msdt.exe mshta.exe msiexec.exe netsh.exe odbcconf.exe pcalua.exe pcwrun.exe
    pktmon.exe powershell.exe pwsh.exe presentationhost.exe print.exe psr.exe rasautou.exe reg.exe regasm.exe
    regedit.exe regini.exe register-cimprovider.exe regsvcs.exe regsvr32.exe replace.exe rpcping.exe rundll32.exe
    runonce.exe runscripthelper.exe sc.exe schtasks.exe scriptrunner.exe syncappvpublishingserver.exe
    ttdinject.exe tttracer.exe vbc.exe verclsid.exe wab.exe wmic.exe wscript.exe wsreset.exe xwizard.exe
    winword.exe excel.exe powerpnt.exe outlook.exe msedge.exe chrome.exe firefox.exe
    advpack.dll ieadvpack.dll ieframe.dll mshtml.dll pcwutl.dll setupapi.dll shdocvw.dll shell32.dll
    syssetup.dll url.dll zipfldr.dll comsvcs.dll
    """.split()
)
_FLAG = re.compile(r"(?<![\w/])(-{1,2}|/)([A-Za-z][A-Za-z-]{1,24})\b")


class Refused(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def granted(tenant_id: Optional[str], provider: str, query_class: str) -> bool:
    if query_class not in QUERY_CLASSES:
        return False
    if query_class == "public_identifier":
        return True
    if not tenant_id:
        return False
    try:
        row = fetch_one(
            "SELECT 1 AS ok FROM tia_research_grants WHERE tenant_id = %s::uuid AND provider = %s AND query_class = %s "
            "AND revoked_at IS NULL AND valid_from <= now() AND valid_to > now();",
            (tenant_id, provider, query_class),
        )
    except Exception as exc:  # noqa: BLE001  - no table, no grant
        logger.warning("research grant check failed: %s", type(exc).__name__)
        return False
    return bool(row)


def grants_for(tenant_id: str) -> List[Dict[str, Any]]:
    try:
        return fetch_all(
            "SELECT provider, query_class, approved_by, customer_reference, (valid_to AT TIME ZONE 'utc')::text AS valid_to "
            "FROM tia_research_grants WHERE tenant_id = %s::uuid AND revoked_at IS NULL AND valid_from <= now() AND valid_to > now() "
            "ORDER BY provider, query_class;",
            (tenant_id,),
        )
    except Exception:  # noqa: BLE001
        return []


def agent_research_policy(tenant_id: str) -> Dict[str, Any]:
    """Sent with every investigation. The agent performs no lookup that is not listed here."""
    ip = [g["provider"] for g in grants_for(tenant_id) if g["query_class"] == "ip_reputation"]
    return {"version": 1, "ip_reputation": sorted(set(ip)), "public_addresses_only": True}


def _record(tenant_id: str, alert_id: Optional[str], provider: str, query_class: str, query_text: str, requested_by: str, *, outcome: str, refusal: Optional[str] = None) -> str:
    try:
        row = fetch_one_write(
            "INSERT INTO tia_research_disclosures (tenant_id, alert_id, provider, query_class, query_text, outcome, refusal_reason, requested_by) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id::text AS id;",
            (tenant_id, alert_id, provider, query_class, query_text[:500], outcome, refusal, requested_by[:200]),
        )
        return str(row["id"])
    except Exception as exc:  # noqa: BLE001
        # A disclosure that cannot be recorded must not be sent: callers record before fetching.
        raise Refused("disclosure_log_unavailable", type(exc).__name__) from exc


def _complete(disclosure_id: str, result: Optional[Dict[str, Any]], *, failed: Optional[str] = None) -> None:
    try:
        execute(
            "UPDATE tia_research_disclosures SET http_status = %s, source_url = %s, fetched_at = %s::timestamptz, excerpt = %s, "
            "outcome = CASE WHEN %s::text IS NULL THEN outcome ELSE 'failed' END, refusal_reason = coalesce(%s::text, refusal_reason) WHERE id = %s::uuid;",
            (
                (result or {}).get("status"), (result or {}).get("source_url"), (result or {}).get("fetched_at"),
                ((result or {}).get("excerpt") or "")[:2000] or None, failed, failed, disclosure_id,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("research disclosure result not stored: %s", type(exc).__name__)


def sanitise_behaviour(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce an alert to public binary names and command-line flag tokens. Everything else is dropped."""
    text_fields = [alert.get(k) or "" for k in ("parent_process", "parent_command_line", "alert_title", "alert_description")]
    raw = alert.get("raw_event")
    if isinstance(raw, dict):
        win = (raw.get("data") or {}).get("win", {}).get("eventdata", {}) if isinstance(raw.get("data"), dict) else {}
        text_fields += [str(win.get(k) or "") for k in ("image", "commandLine", "parentImage", "parentCommandLine")]
    names: List[str] = []
    dropped = 0
    for field in text_fields:
        for token in re.split(r"[\s\"'\\/|,;()]+", str(field)):
            t = token.strip().lower()
            if not t or "." not in t:
                continue
            if re.fullmatch(r"[a-z0-9_.-]+\.(exe|dll)", t):
                if t in _PUBLIC_BINARIES:
                    if t not in names:
                        names.append(t)
                else:
                    dropped += 1
    flags = sorted({("-" if m.group(1).startswith("-") else "/") + m.group(2).lower() for f in text_fields[:2] for m in _FLAG.finditer(str(f))})
    return {"binaries": names[:4], "flags": flags[:12], "dropped_names": dropped}


def behavioural_lookup(
    *, tenant_id: str, alert: Dict[str, Any], provider: str, requested_by: str,
    fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Research the public binaries in one alert. Records every request; refuses without a grant."""
    from app.services import tia_research as r

    spec = BEHAVIOUR_PROVIDERS.get(provider)
    if not spec:
        raise Refused("unknown_provider")
    s = sanitise_behaviour(alert)
    alert_id = alert.get("id")
    query = " ".join(s["binaries"]) or "(nothing sendable)"
    if not s["binaries"]:
        _record(tenant_id, alert_id, provider, "behavioural_query", query, requested_by, outcome="refused", refusal="nothing_sendable")
        raise Refused("nothing_sendable", "the alert names no publicly known binary")
    if not granted(tenant_id, provider, "behavioural_query"):
        _record(tenant_id, alert_id, provider, "behavioural_query", query, requested_by, outcome="refused", refusal="tenant_not_authorised")
        raise Refused("tenant_not_authorised", "this customer has not authorised behavioural research with that provider")
    if not r.host_allowed(spec[0]):
        _record(tenant_id, alert_id, provider, "behavioural_query", query, requested_by, outcome="refused", refusal="host_not_allowed")
        raise Refused("host_not_allowed", "the provider is not on the platform research allow-list")
    fetch = fetcher or r.fetch
    findings = []
    for name in s["binaries"]:
        stem = name.rsplit(".", 1)[0]
        page = stem[:1].upper() + stem[1:]
        result = None
        for path in spec[1]:
            url = f"https://{spec[0]}{path.format(name=urllib.parse.quote(page))}"
            did = _record(tenant_id, alert_id, provider, "behavioural_query", name, requested_by, outcome="sent")
            try:
                result = fetch(url)
            except r.ResearchRefused as exc:
                _complete(did, None, failed=exc.code)
                raise Refused(exc.code) from exc
            except Exception as exc:  # noqa: BLE001
                _complete(did, None, failed=type(exc).__name__)
                result = None
                break
            _complete(did, result)
            if result.get("ok"):
                break
        if not result or not result.get("ok"):
            findings.append({"binary": name, "found": False, "status": (result or {}).get("status")})
            continue
        findings.append({"binary": name, "found": True, **_applies(result, s["flags"]), "source_url": result["source_url"], "fetched_at": result["fetched_at"], "trust": result["trust"]})
    return {"provider": provider, "query_class": "behavioural_query", "sent": s["binaries"], "withheld_names": s["dropped_names"], "flags_compared_locally": s["flags"], "findings": findings}


def _applies(result: Dict[str, Any], flags: List[str]) -> Dict[str, Any]:
    """How the reference bears on the alert, computed here, not by the model. Flags never leave the platform."""
    text = (result.get("excerpt") or "").lower()
    matched = [f for f in flags if f.lower() in text]
    techniques = sorted(set(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", result.get("excerpt") or "")))[:8]
    return {
        "documented_techniques": techniques,
        "alert_flags_documented_as_abuse": matched,
        "applies": (
            f"The reference documents {', '.join(matched)} as a known abuse pattern for this binary."
            if matched
            else "The binary is documented as abusable, but none of this alert's flags appear in the reference."
        ),
    }


def ip_is_public(addr: Optional[str]) -> bool:
    try:
        ip = ipaddress.ip_address(str(addr))
    except ValueError:
        return False
    return ip.is_global
