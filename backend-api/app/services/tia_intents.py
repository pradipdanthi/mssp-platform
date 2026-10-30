"""Turn families for TIA conversation.

This module names what the operator is asking for. It does not grant permission, start jobs,
or choose a tenant. Conversation and tools still validate those.

Families
  assessment      what happened / is this actually critical — read-only evidence
  recommendation  what should we investigate next — advice, no job
  status          what investigation have you done — read job/ticket state
  execution       investigate this — queue a durable job
  other           not one of those families

Product-name speech variants (Wazoo, Shuffel) resolve here so engine questions do not
depend on a growing list of one-off patches in the dispatcher.
"""

from __future__ import annotations

import re
from typing import List

ASSESSMENT = "assessment"
RECOMMENDATION = "recommendation"
STATUS = "status"
EXECUTION = "execution"
OTHER = "other"

ENGINE_ALIASES = {
    "wazuh": "wazuh",
    "wazoo": "wazuh",
    "wazu": "wazuh",
    "wasoo": "wazuh",
    "wahzoo": "wazuh",
    "siem": "wazuh",
    "the hive": "thehive",
    "thehive": "thehive",
    "shuffle": "shuffle",
    "shuffel": "shuffle",
    "shuffler": "shuffle",
    "soar": "shuffle",
    "suricata": "suricata",
    "zeek": "zeek",
    "bro": "zeek",
    "misp": "misp",
    "greenbone": "greenbone",
    "openvas": "greenbone",
    "velociraptor": "velociraptor",
    "secure edge": "secure_edge",
    "soc agent": "soc_agent",
    "control plane": "control_plane",
}

_ALIAS_ORDER = tuple(sorted(ENGINE_ALIASES, key=len, reverse=True))

_STATUS = re.compile(
    r"\b("
    r"what investigation have you (done|run|finished)|"
    r"have you (already )?(done|run|finished) (an |the |this )?investigation|"
    r"investigation status|"
    r"how's the investigation|"
    r"has the investigation (finished|completed|run)|"
    r"what have you (already )?(checked|investigated|looked at) .{0,40}\binvestigation\b|"
    r"status of (the |this |my )?investigation"
    r")\b",
    re.I,
)
_RECOMMEND = re.compile(
    r"\b("
    r"what should we investigat|"
    r"what would you investigat|"
    r"what should (we|i) (look at|check|do) next|"
    r"what would you (look at|check|do) next|"
    r"recommend .{0,40}(next|investigat)|"
    r"which (alert|case) should (we|i) investigat|"
    r"what(?:'s| is) next to investigat|"
    r"investigat(?:e|ion) next"
    r")\b",
    re.I,
)
_EXECUTE = re.compile(
    r"\b("
    r"investigate this|"
    r"investigate the (alert|case|first|second|third|fourth|fifth)|"
    r"please investigate|"
    r"go ahead and investigate|"
    r"start (a )?(deep )?investigation|"
    r"run (a )?(deep )?investigation|"
    r"look deeper into this|"
    r"dig (deeper )?into this|"
    r"queue (a |an )?(deep )?investigation"
    r")\b",
    re.I,
)
# Assessment is "what happened / is this truly critical" — not the dedicated
# criticality-label, known/unknown, or delay questions that have their own tools.
_ASSESS = re.compile(
    r"\b("
    r"what (do you think )?happened( here)?|"
    r"what do you think happened|"
    r"is this (actually |really |truly )?(critical|malicious|an incident)|"
    r"supporting evidence|"
    r"what(?:'s| is) the (supporting )?evidence"
    r")\b",
    re.I,
)


def classify(text: str) -> str:
    t = text or ""
    if _STATUS.search(t):
        return STATUS
    if _RECOMMEND.search(t):
        return RECOMMENDATION
    if _EXECUTE.search(t):
        return EXECUTION
    if _ASSESS.search(t):
        return ASSESSMENT
    return OTHER


def engines_in_text(text: str) -> List[str]:
    low = f" {(text or '').lower()} "
    found: List[str] = []
    for alias in _ALIAS_ORDER:
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low):
            eid = ENGINE_ALIASES[alias]
            if eid not in found:
                found.append(eid)
    return found
