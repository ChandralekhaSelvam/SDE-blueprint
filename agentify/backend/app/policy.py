"""Policy packs.

Hard overrides are deterministic rules held in version-controlled YAML. No
model decides a risk tier. When someone asks "what if the LLM is wrong about
risk", the answer is that the LLM was never consulted: the cap came from
policy/<industry>.yaml at a named line.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from .config import settings

BASE_PACK: dict[str, Any] = {
    "name": "cross-industry",
    "bands": {"full_agent": 75, "hitl": 40},
    "overrides": [
        {
            "rule": "pii",
            "cap": 60,
            "reason": "Task handles personal data. Autonomous execution requires a review gate.",
            "when": "pii",
        },
        {
            "rule": "safety_critical",
            "cap": 45,
            "reason": "Safety-critical outcome. Human accountability cannot be delegated.",
            "when": "safety_critical",
        },
        {
            "rule": "judgement_dominant",
            "cap": 35,
            "reason": "Neither rule-bound nor low-complexity. Volume does not make judgement work automatable.",
            "computed": "judgement_dominant",
        },
        {
            "rule": "executive_judgement",
            "cap": 30,
            "reason": "Executive or strategic judgement. AI supports with insight only.",
            "when": "executive_judgement",
        },
    ],
    "residuals": {"full_agent": 0.04, "hitl": 0.15, "human_only": 0.80},
    "reviewer_role": "Process owner",
}

INDUSTRY_PACKS: dict[str, dict[str, Any]] = {
    "consumer_products": {
        "name": "Consumer products",
        "reviewer_role": "Counsel or category lead",
        "extra_overrides": [
            {
                "rule": "contract_commitment",
                "cap": 55,
                "reason": "Creates or alters a binding commitment to a counterparty.",
                "keywords": ["negotiat", "indemnit", "settlement", "waive", "binding"],
            }
        ],
    },
    "life_sciences": {
        "name": "Life sciences",
        "reviewer_role": "QA or regulatory affairs",
        "extra_overrides": [
            {
                "rule": "gxp",
                "cap": 40,
                "reason": "GxP-regulated activity. Requires qualified person review and validation evidence.",
                "keywords": ["batch release", "gxp", "root cause", "capa", "causality", "adverse event"],
            }
        ],
    },
    "industrial": {
        "name": "Industrial",
        "reviewer_role": "Category manager",
        "extra_overrides": [
            {
                "rule": "supplier_payment",
                "cap": 65,
                "reason": "Releases funds to a third party. Segregation of duties applies.",
                "keywords": ["payment", "disburse", "release funds", "remit"],
            }
        ],
    },
    "telecom": {
        "name": "Telecom and media",
        "reviewer_role": "Care operations lead",
        "extra_overrides": [
            {
                "rule": "cpni",
                "cap": 55,
                "reason": "Customer proprietary network information. Access is regulated.",
                "keywords": ["cpni", "credit above", "regulator", "systemic billing"],
            }
        ],
    },
}


@lru_cache(maxsize=8)
def load_pack(industry: str) -> dict[str, Any]:
    """Merge the base pack with the industry pack, preferring an on-disk YAML."""
    pack = {k: v for k, v in BASE_PACK.items()}
    pack["overrides"] = list(BASE_PACK["overrides"])

    path = os.path.join(settings.policy_dir, f"{industry}.yaml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            disk = yaml.safe_load(fh) or {}
        pack.update({k: v for k, v in disk.items() if k != "overrides"})
        for extra in disk.get("overrides", []):
            extra["source"] = f"policy/{industry}.yaml"
            pack["overrides"].append(extra)
        pack["source"] = f"policy/{industry}.yaml"
        return pack

    ind = INDUSTRY_PACKS.get(industry, {})
    pack["name"] = ind.get("name", pack["name"])
    pack["reviewer_role"] = ind.get("reviewer_role", pack["reviewer_role"])
    for extra in ind.get("extra_overrides", []):
        item = dict(extra)
        item["source"] = f"policy/{industry} (built in)"
        pack["overrides"].append(item)

    for item in pack["overrides"]:
        item.setdefault("source", "policy/base.yaml")
    return pack


def applicable_overrides(task_flags: dict[str, Any], text: str, pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every override that fires for this task, cheapest check first.

    `text` must be the activity name and its notes only. Matching against the
    whole L1-L4 path would fire a contract rule on every activity in a process
    group merely called "Contract Management", which is not what the rule means.
    """
    hits: list[dict[str, Any]] = []
    lowered = text.lower()
    for rule in pack["overrides"]:
        when = rule.get("when")
        if when and task_flags.get(when):
            hits.append(rule)
            continue
        computed = rule.get("computed")
        if computed and task_flags.get(computed):
            hits.append(rule)
            continue
        for kw in rule.get("keywords", []):
            if kw in lowered:
                hits.append(rule)
                break
    return hits
