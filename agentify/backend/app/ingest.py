"""Process inventory ingest.

Client inventories are messy. Columns are named differently at every account,
sheets have title rows above the header, codes arrive as floats, booleans
arrive as "Y". This module is deliberately forgiving: it never raises on a
recoverable problem, it records what it had to guess, and it always returns
a usable task list or a precise reason why it could not.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import pandas as pd

from .schemas import Task

# Every alias we have seen in the wild, lowercased and stripped of punctuation.
ALIASES: dict[str, list[str]] = {
    "l1_code": ["l1", "l1code", "category", "categorycode", "categoryid", "pcfl1"],
    "l1_name": ["l1name", "categoryname", "l1description", "categorydesc"],
    "l2_code": ["l2", "l2code", "processgroup", "processgroupcode", "pcfl2"],
    "l2_name": ["l2name", "processgroupname", "l2description"],
    "l3_code": ["l3", "l3code", "process", "processcode", "pcfl3"],
    "l3_name": ["l3name", "processname", "l3description"],
    "l4_code": ["l4", "l4code", "activity", "activitycode", "taskcode", "pcfl4", "pcfid", "elementid"],
    "l4_name": ["l4name", "activityname", "taskname", "activitydescription", "task", "l4description", "elementname"],
    "volume_per_month": ["volume", "volumepermonth", "monthlyvolume", "txnpermonth", "transactions", "vol"],
    "avg_handle_minutes": ["aht", "avghandletime", "handleminutes", "avgminutes", "minutespertask", "handlingtime"],
    "fte": ["fte", "ftecount", "headcount", "hc", "ftes"],
    "rule_based": ["rulebased", "rulebasedscore", "standardisation", "standardization", "ruleboundpct"],
    "pii": ["pii", "personaldata", "containspii", "gdpr", "sensitivedata"],
    "safety_critical": ["safetycritical", "safety", "criticality"],
    "executive_judgement": ["executive", "strategic", "executivejudgement", "executivejudgment"],
    "systems": ["systems", "system", "applications", "apps", "tooling", "platform"],
    "exception_rate": ["exceptionrate", "exceptions", "errorrate", "reworkrate"],
    "notes": ["notes", "comment", "comments", "description", "remarks"],
}

TRUE_TOKENS = {"y", "yes", "true", "1", "t", "high", "critical"}
FALSE_TOKENS = {"n", "no", "false", "0", "f", "low", "none", ""}


class IngestError(Exception):
    """Raised only when no task list can be recovered at all."""


def _norm(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _build_column_map(columns: list[Any]) -> dict[str, str]:
    normalised = {_norm(c): c for c in columns}
    mapping: dict[str, str] = {}
    for field, aliases in ALIASES.items():
        if _norm(field) in normalised:
            mapping[field] = normalised[_norm(field)]
            continue
        for alias in aliases:
            if alias in normalised:
                mapping[field] = normalised[alias]
                break
    return mapping


def _find_header_row(df: pd.DataFrame) -> int | None:
    """Some exports carry a title block above the real header. Find it."""
    wanted = {"l4", "l4code", "activity", "activityname", "taskname", "l4name", "pcfid"}
    for idx in range(min(len(df), 12)):
        cells = {_norm(v) for v in df.iloc[idx].tolist() if pd.notna(v)}
        if cells & wanted:
            return idx
    return None


def _to_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE_TOKENS:
        return True
    if text in FALSE_TOKENS:
        return False
    return None


def _to_code(value: Any) -> str:
    """Excel turns 9.2 into 9.2 and 9.0 into 9. Put it back."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)}.0"
    return str(value).strip()


def _frame_from_bytes(raw: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        book = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=object)
        # Prefer the sheet that actually looks like a process list.
        best_name, best_frame, best_score = None, None, -1
        for name, frame in book.items():
            score = len(frame)
            if any("l4" in _norm(v) or "activity" in _norm(v) for v in frame.head(12).values.ravel() if pd.notna(v)):
                score += 10_000
            if score > best_score:
                best_name, best_frame, best_score = name, frame, score
        frame = best_frame if best_frame is not None else pd.DataFrame()
    elif lower.endswith(".json"):
        payload = json.loads(raw.decode("utf-8-sig"))
        rows = payload.get("tasks", payload) if isinstance(payload, dict) else payload
        return pd.DataFrame(rows)
    else:
        # Read with the stdlib reader and pad short rows. pandas infers the field
        # count from the first line, which breaks on exports that carry a title
        # block above the real header -- a very common shape in client extracts.
        text = raw.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        delimiter = max([",", ";", "\t", "|"], key=sample.count)
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            return pd.DataFrame()
        width = max(len(r) for r in rows)
        rows = [r + [None] * (width - len(r)) for r in rows]
        frame = pd.DataFrame(rows, dtype=object)

    header_row = _find_header_row(frame)
    if header_row is None:
        header_row = 0
    frame.columns = frame.iloc[header_row]
    frame = frame.iloc[header_row + 1 :].reset_index(drop=True)
    frame = frame.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return frame


def parse_inventory(raw: bytes, filename: str) -> tuple[list[Task], list[str]]:
    """Return tasks plus a list of human-readable warnings. Never partially fails."""
    warnings: list[str] = []

    if not raw:
        raise IngestError("The uploaded file is empty.")

    try:
        frame = _frame_from_bytes(raw, filename)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        raise IngestError(f"Could not read {filename}: {exc}") from exc

    if frame.empty:
        raise IngestError(f"{filename} parsed but contained no rows.")

    colmap = _build_column_map(list(frame.columns))
    if "l4_name" not in colmap:
        # Last resort: the widest text column is almost always the activity name.
        text_cols = [c for c in frame.columns if frame[c].astype(str).str.len().mean() > 12]
        if not text_cols:
            raise IngestError(
                "No activity name column found. Expected a column like 'L4 Name', "
                "'Activity', or 'Task name'."
            )
        colmap["l4_name"] = text_cols[0]
        warnings.append(f"No L4 name column matched, using '{text_cols[0]}'.")

    for required in ("l1_code", "l2_code", "l3_code", "l4_code"):
        if required not in colmap:
            warnings.append(f"{required} not supplied, codes will be generated.")

    def cell(row: pd.Series, field: str) -> Any:
        col = colmap.get(field)
        return row[col] if col is not None and col in row else None

    tasks: list[Task] = []
    skipped = 0
    for idx, row in frame.iterrows():
        name = cell(row, "l4_name")
        if name is None or (isinstance(name, float) and pd.isna(name)) or not str(name).strip():
            skipped += 1
            continue

        l1c = _to_code(cell(row, "l1_code")) or "0.0"
        l3c = _to_code(cell(row, "l3_code")) or f"{l1c}.{idx}"
        l4c = _to_code(cell(row, "l4_code")) or f"{l3c}.{idx}"

        exception = _to_float(cell(row, "exception_rate"))
        if exception is not None and exception > 1:
            exception = exception / 100.0

        rule = _to_float(cell(row, "rule_based"))
        if rule is not None and rule <= 1:
            rule = rule * 100.0

        tasks.append(
            Task(
                id=f"T{idx:04d}",
                l1_code=l1c,
                l1_name=str(cell(row, "l1_name") or "Uncategorised").strip(),
                l2_code=_to_code(cell(row, "l2_code")) or l1c,
                l2_name=str(cell(row, "l2_name") or "").strip(),
                l3_code=l3c,
                l3_name=str(cell(row, "l3_name") or "").strip(),
                l4_code=l4c,
                l4_name=str(name).strip(),
                volume_per_month=_to_float(cell(row, "volume_per_month")),
                avg_handle_minutes=_to_float(cell(row, "avg_handle_minutes")),
                fte=_to_float(cell(row, "fte")),
                rule_based=rule,
                pii=_to_bool(cell(row, "pii")),
                safety_critical=_to_bool(cell(row, "safety_critical")),
                executive_judgement=_to_bool(cell(row, "executive_judgement")),
                systems=(str(cell(row, "systems")).strip() if cell(row, "systems") is not None and pd.notna(cell(row, "systems")) else None),
                exception_rate=exception,
                notes=(str(cell(row, "notes")).strip() if cell(row, "notes") is not None and pd.notna(cell(row, "notes")) else None),
            )
        )

    if not tasks:
        raise IngestError(f"{filename} had {len(frame)} rows but none carried an activity name.")

    if skipped:
        warnings.append(f"{skipped} row(s) skipped: no activity name.")

    missing_effort = sum(1 for t in tasks if t.annual_hours == 0)
    if missing_effort:
        warnings.append(
            f"{missing_effort} of {len(tasks)} tasks have no volume or FTE data. "
            "Effort estimates for those tasks are shown as a range, not a point."
        )

    return tasks, warnings


def summarise(tasks: list[Task]) -> dict[str, Any]:
    return {
        "l1": len({t.l1_code for t in tasks}),
        "l2": len({t.l2_code for t in tasks}),
        "l3": len({t.l3_code for t in tasks}),
        "l4": len(tasks),
        "with_effort": sum(1 for t in tasks if t.annual_hours > 0),
        "total_fte": round(sum(t.annual_hours for t in tasks) / 1720.0, 1),
    }
