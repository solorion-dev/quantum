#!/usr/bin/env python3
"""proof-check — check that proof level matches claim level.

Implements the fleet rules (AGENTS.md, Oct 27, 2026):

> Proof level must match claim level — every check proves exactly
> the level it exercised, and the claim may not outrun it.

> A receipt is not a reading; a negative needs a source — a portal
> status (Received / In Review / submitted / signed-by-X) proves a
> thing arrived, never that its fields are complete; and a factual
> negative about Scotty's own history is never answered from
> plausibility — it gets a source search first or is labelled
> unverified on the spot.

Born from the Oct 26-27, 2026 incidents: an Aflac Employer
Verification called complete off a portal "Received" status, a
Sunshine stream called working off an encoder probe that captured
zero real frames, a copy called complete off rsync progress, Hive
entries claimed from a background delivery under a foreign session
id, a Sweetser "never admitted" negative asserted with no source
search, and a display's GPU identity asserted from its connector
name instead of the driver link.

The tool owns the evidence-level table: a manifest lists claims
and the evidence offered for each, but a manifest cannot inflate
what a kind of evidence proves. Each claim gets exactly one
verdict — SUPPORTED, OVERCLAIMED, or UNSUPPORTED — from the level
of its best countable evidence and, for the claim types that name
one, a required evidence kind. Discounted evidence (reported, but
known-untrustworthy — e.g. a delivery under a foreign session id)
is listed in the report and never counts.

v2 additions:

* Evidence freshness. An evidence entry may carry `observed_at`
  (ISO-8601, timezone required). A naive or unparseable value makes
  that entry INVALID: reported, never counted, never a crash.
  Evidence older than the tool-owned per-claim-type maximum age
  (see CLAIM_MAX_AGE_SECONDS — a manifest cannot override or
  extend it; `max_age*` fields in a manifest are flagged as
  ignored) is STALE: reported separately with its age, never
  counts toward SUPPORTED. Undated evidence counts exactly as in
  v1 and is listed as undated. The reference instant is the
  `--now` CLI flag if given, else the manifest's top-level `now`,
  else the current UTC time.
* Auto-evidence. `--evidence-from <file.json>` (repeatable)
  derives evidence entries from settle-check / merge-verify JSON
  artifacts instead of hand-asserted manifests. A settle-check
  `status` of `verified` derives a `content_read` (level 3)
  entry; `failed` / `unsettled` / `error` derive nothing
  countable (reported as skipped). A merge-verify `verdict` of
  `VERIFIED` derives an `endtoend_run` (level 4) entry;
  `FAILED` / `INCOMPLETE` derive nothing countable. Linkage: an
  artifact's `claim_id` field names the claim it belongs to; with
  no `claim_id`, the artifact applies only when the manifest has
  exactly one claim, otherwise the run is a usage error (exit 2).

Stdlib only, Python 3.10+. Read-only: it reads one manifest file
(plus any --evidence-from artifacts) and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERDICT_SUPPORTED = "SUPPORTED"
VERDICT_OVERCLAIMED = "OVERCLAIMED"
VERDICT_UNSUPPORTED = "UNSUPPORTED"
VERDICT_INCOMPLETE = "INCOMPLETE"

EXIT_SUPPORTED = 0
EXIT_REJECTED = 1
EXIT_INCOMPLETE = 2

# Evidence kinds -> the level of proof they actually provide.
# The tool owns this table; manifests cannot inflate a kind.
EVIDENCE_LEVELS: dict[str, int] = {
    # level 1 — receipt: something arrived / was reported / progressed
    "receipt": 1,
    "status_report": 1,
    "agent_report": 1,
    "progress_output": 1,
    # level 2 — surface: something exists / is up / responded to a probe
    "existence": 2,
    "list_count": 2,
    "port_open": 2,
    "process_up": 2,
    "probe": 2,
    "search_snippet": 2,
    # level 3 — content: the actual contents / delta / source were read
    "content_read": 3,
    "delta_compare": 3,
    "source_search": 3,
    "hard_identifier": 3,
    "output_file_read": 3,
    # level 4 — end-to-end: the real path was exercised for real
    "endtoend_run": 4,
    "public_path": 4,
    "real_session": 4,
}

LEVEL_NAMES: dict[int, str] = {
    0: "none",
    1: "receipt",
    2: "surface",
    3: "content",
    4: "endtoend",
}

# Claim types -> minimum evidence level the claim requires.
CLAIM_REQUIRED_LEVEL: dict[str, int] = {
    "received": 1,
    "exists": 2,
    "complete": 3,
    "copied": 3,
    "absent": 3,
    "identity": 3,
    "works": 4,
    "fixed": 4,
    "healthy": 4,
}

# Claim types where level alone is not enough: at least one piece
# of countable evidence must be of one of these kinds (and, per the
# level check, at the required level — with the fixed table above
# these kinds sit exactly at their claims' required levels).
KIND_REQUIREMENTS: dict[str, frozenset[str]] = {
    "complete": frozenset({"content_read", "delta_compare"}),
    "copied": frozenset({"content_read", "delta_compare"}),
    "absent": frozenset({"source_search"}),
    "identity": frozenset({"hard_identifier"}),
    "works": frozenset({"endtoend_run", "public_path", "real_session"}),
    "fixed": frozenset({"endtoend_run", "public_path", "real_session"}),
    "healthy": frozenset({"endtoend_run", "public_path", "real_session"}),
}

# Evidence freshness (v2). Maximum age, in seconds, for evidence
# attached to a claim of each type. The tool owns this table too:
# a manifest cannot override or extend it (see _find_ignored_fields).
#   works / fixed / healthy  — "it works" decays fast: 24 hours
#   complete / copied        — contents claims: 7 days
#   exists ("present")       — presence claims: 7 days
#   absent / identity        — negatives / identity: 30 days
#   received (and default)   — 7 days
CLAIM_MAX_AGE_SECONDS: dict[str, int] = {
    "works": 24 * 3600,
    "fixed": 24 * 3600,
    "healthy": 24 * 3600,
    "complete": 7 * 24 * 3600,
    "copied": 7 * 24 * 3600,
    "present": 7 * 24 * 3600,
    "exists": 7 * 24 * 3600,
    "absent": 30 * 24 * 3600,
    "identity": 30 * 24 * 3600,
    "received": 7 * 24 * 3600,
}
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600

# Manifest keys that try to set a maximum age. Never honoured;
# every occurrence is reported in `ignored_fields`.
def _is_max_age_key(key: str) -> bool:
    return key.startswith("max_age") or key in {"evidence_max_age", "freshness_max_age"}

# Timestamp field names looked for, in order, on an auto-evidence
# artifact. NOTE: the real settle-check and merge-verify JSON
# outputs carry NONE of these (verified against their sources on
# 2026-11-03 — see BUILD-NOTES.md), so the normal path is the
# fallback to the artifact file's mtime (UTC).
ARTIFACT_TIMESTAMP_FIELDS = (
    "observed_at", "timestamp", "checked_at", "generated_at",
    "finished_at", "started_at", "run_at", "created_at",
)

# Severity ranking for the overall verdict: the manifest's verdict
# is its weakest claim's verdict.
_SEVERITY = {VERDICT_SUPPORTED: 0, VERDICT_OVERCLAIMED: 1, VERDICT_UNSUPPORTED: 2}


def _level_label(level: int) -> str:
    return f"{level} ({LEVEL_NAMES[level]})"


def _validate_manifest(data) -> list[str]:
    """Return a list of validation errors (empty = manifest is usable)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]

    claims = data.get("claims")
    if not isinstance(claims, list) or len(claims) == 0:
        return ["manifest 'claims' list is missing or empty"]

    for idx, claim in enumerate(claims):
        where = f"claim #{idx}"
        if not isinstance(claim, dict):
            errors.append(f"{where} is not an object")
            continue
        cid = claim.get("id")
        if isinstance(cid, str) and cid:
            where = f"claim {cid!r}"
        else:
            errors.append(f"{where} missing non-empty string 'id'")

        ctype = claim.get("type")
        if not isinstance(ctype, str) or not ctype:
            errors.append(f"{where} missing string 'type'")
        elif ctype not in CLAIM_REQUIRED_LEVEL:
            errors.append(f"{where} unknown claim type: {ctype!r}")

        if not isinstance(claim.get("statement"), str):
            errors.append(f"{where} missing string 'statement'")

        evidence = claim.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{where} missing list 'evidence'")
            continue
        for eidx, ev in enumerate(evidence):
            ewhere = f"{where} evidence #{eidx}"
            if not isinstance(ev, dict):
                errors.append(f"{ewhere} is not an object")
                continue
            kind = ev.get("kind")
            if not isinstance(kind, str) or not kind:
                errors.append(f"{ewhere} missing string 'kind'")
            elif kind not in EVIDENCE_LEVELS:
                errors.append(f"{ewhere} unknown evidence kind: {kind!r}")
            if not isinstance(ev.get("detail"), str):
                errors.append(f"{ewhere} missing string 'detail'")
            if "discounted" in ev and not isinstance(ev["discounted"], bool):
                errors.append(f"{ewhere} 'discounted' must be a boolean")
            if "discount_reason" in ev and not isinstance(ev["discount_reason"], str):
                errors.append(f"{ewhere} 'discount_reason' must be a string")
            if "source" in ev and not isinstance(ev["source"], str):
                errors.append(f"{ewhere} 'source' must be a string")
            # NOTE: 'observed_at' is deliberately not a validation
            # error when malformed — a bad timestamp makes that one
            # evidence entry INVALID at evaluation time (reported,
            # never counted), it does not void the whole manifest.

    return errors


def _parse_iso8601(value):
    """Parse an ISO-8601 timestamp that MUST carry a timezone.

    Returns (datetime in UTC, None) on success, (None, reason) on
    failure. Naive and unparseable values are failures, by design.
    """
    if not isinstance(value, str) or not value.strip():
        return None, "observed_at is not a non-empty string"
    txt = value.strip()
    if txt.endswith(("Z", "z")):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None, f"observed_at {value!r} is not parseable ISO-8601"
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None, f"observed_at {value!r} has no timezone (naive timestamps are invalid)"
    return dt.astimezone(timezone.utc), None


def _find_ignored_fields(node, path="$", out=None):
    """Collect manifest locations of max_age* keys (never honoured)."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for key, val in node.items():
            here = f"{path}.{key}"
            if isinstance(key, str) and _is_max_age_key(key):
                out.append(here)
            _find_ignored_fields(val, here, out)
    elif isinstance(node, list):
        for i, val in enumerate(node):
            _find_ignored_fields(val, f"{path}[{i}]", out)
    return out


def _detect_artifact(data):
    """Classify a parsed artifact JSON object.

    Returns (artifact_type, raw_verdict) where artifact_type is
    "settle-check", "merge-verify", or None (unrecognized), based
    on the REAL output shapes:
      settle-check --json: {"claim", "status", "problems", "notes"}
        — verdict word lives in `status`, lowercase.
      merge-verify --json: {"verdict", "exit_code", "repo", "head",
        "checks", ...} — verdict word lives in `verdict`, uppercase.
    """
    if not isinstance(data, dict):
        return None, None
    if "checks" in data or "head" in data or ("verdict" in data and "repo" in data):
        return "merge-verify", data.get("verdict", data.get("status"))
    if "status" in data or "problems" in data or "notes" in data or "claim" in data:
        return "settle-check", data.get("status", data.get("verdict"))
    if "verdict" in data:
        return "merge-verify", data.get("verdict")
    return None, None


def _artifact_timestamp(data, path: Path):
    """observed_at for a derived entry: the artifact's own timestamp
    field if one is present, else the file's mtime in UTC."""
    for field in ARTIFACT_TIMESTAMP_FIELDS:
        if field in data and data[field] is not None:
            return data[field]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _load_derived_evidence(paths, claims):
    """Derive evidence entries from settle-check / merge-verify artifacts.

    Returns (by_claim_id, report, errors):
      by_claim_id: claim id -> list of manifest-shaped evidence dicts
      report:      one entry per artifact file, outcome derived|skipped
      errors:      usage errors (unreadable/unparseable file, claim_id
                   with no matching claim, ambiguous linkage) — the
                   caller turns any error into INCOMPLETE / exit 2.
    """
    by_claim: dict[str, list[dict]] = {}
    report: list[dict] = []
    errors: list[str] = []
    claim_ids = [c.get("id") for c in claims if isinstance(c, dict)]

    for raw_path in paths or []:
        apath = Path(raw_path).expanduser()
        label = str(apath)
        try:
            text = apath.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"evidence artifact cannot be read: {label}: {exc}")
            continue
        try:
            data = json.loads(text)
        except Exception as exc:
            errors.append(f"evidence artifact does not parse: {label}: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"evidence artifact is not a JSON object: {label}")
            continue

        atype, raw_verdict = _detect_artifact(data)
        source = f"{atype}:{label}" if atype else label
        base = {
            "source": source,
            "artifact_type": atype,
            "artifact": label,
            "raw_verdict": raw_verdict,
            "claim_id": data.get("claim_id") if isinstance(data.get("claim_id"), str) else None,
        }
        if atype is None:
            report.append({**base, "outcome": "skipped", "kind": None,
                           "reason": "unrecognized artifact shape: neither settle-check nor merge-verify JSON"})
            continue

        verdict_word = str(raw_verdict).strip().upper() if raw_verdict is not None else ""
        if atype == "settle-check":
            kind = "content_read"
            countable = verdict_word == "VERIFIED"
            what = f"settle-check status {raw_verdict!r}"
        else:
            kind = "endtoend_run"
            countable = verdict_word == "VERIFIED"
            what = f"merge-verify verdict {raw_verdict!r}"
        if not countable:
            report.append({**base, "outcome": "skipped", "kind": None,
                           "reason": f"{what} does not derive countable evidence (only a verified result counts)"})
            continue

        # Linkage: explicit claim_id, else the manifest's single claim.
        target = base["claim_id"]
        if target is not None:
            if claim_ids.count(target) == 0:
                errors.append(
                    f"evidence artifact {label}: claim_id {target!r} matches no claim in the manifest")
                continue
            if claim_ids.count(target) > 1:
                errors.append(
                    f"evidence artifact {label}: claim_id {target!r} matches multiple claims in the manifest")
                continue
        else:
            if len(claim_ids) != 1:
                errors.append(
                    f"evidence artifact {label} carries no claim_id and the manifest has "
                    f"{len(claim_ids)} claims: --evidence-from applies to a claim_id-bearing "
                    f"artifact, or to a manifest with exactly one claim")
                continue
            target = claim_ids[0]

        observed = _artifact_timestamp(data, apath)
        entry = {
            "kind": kind,
            "detail": f"Derived from {atype} artifact {label}: {what}",
            "source": source,
            "observed_at": observed,
        }
        by_claim.setdefault(target, []).append(entry)
        report.append({**base, "outcome": "derived", "kind": kind,
                       "claim_id": target, "observed_at": observed,
                       "reason": f"{what} derives a {kind} evidence entry for claim {target!r}"})
    return by_claim, report, errors



def _evaluate_claim(claim: dict, now_dt: datetime, derived_evidence=None) -> dict:
    ctype = claim["type"]
    required_level = CLAIM_REQUIRED_LEVEL[ctype]
    max_age = CLAIM_MAX_AGE_SECONDS.get(ctype, DEFAULT_MAX_AGE_SECONDS)

    all_evidence = list(claim["evidence"]) + list(derived_evidence or [])

    evidence_out: list[dict] = []
    countable_levels: list[int] = []
    countable_kinds: list[str] = []
    noncount_notes: list[str] = []

    for ev in all_evidence:
        kind = ev["kind"]
        level = EVIDENCE_LEVELS[kind]
        discounted = bool(ev.get("discounted", False))

        # --- freshness (v2) ---
        freshness = "undated"
        age_seconds = None
        invalid_reason = None
        stale = False
        observed_raw = ev.get("observed_at")
        if observed_raw is not None:
            observed_dt, perr = _parse_iso8601(observed_raw)
            if observed_dt is None:
                freshness = "invalid"
                invalid_reason = perr
            else:
                age = (now_dt - observed_dt).total_seconds()
                age_seconds = int(age)
                if age > max_age:
                    freshness = "stale"
                    stale = True
                else:
                    freshness = "fresh"

        counted = not discounted and freshness not in ("stale", "invalid")
        evidence_out.append({
            "kind": kind,
            "level": level,
            "level_name": LEVEL_NAMES[level],
            "detail": ev["detail"],
            "discounted": discounted,
            "discount_reason": ev.get("discount_reason"),
            "counted": counted,
            "source": ev.get("source"),
            "derived": bool(ev.get("_derived", False)),
            "observed_at": observed_raw,
            "freshness": freshness,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age,
            "stale": stale,
            "invalid_reason": invalid_reason,
        })
        if counted:
            countable_levels.append(level)
            countable_kinds.append(kind)
        else:
            if discounted:
                noncount_notes.append("discounted evidence never counts")
            if freshness == "stale":
                noncount_notes.append(
                    f"stale evidence (age {age_seconds}s exceeds the {max_age}s "
                    f"maximum for a '{ctype}' claim) never counts")
            if freshness == "invalid":
                noncount_notes.append(f"invalid evidence ({invalid_reason}) never counts")

    best_level = max(countable_levels) if countable_levels else 0

    reasons: list[str] = []
    if not countable_levels:
        verdict = VERDICT_UNSUPPORTED
        if all_evidence:
            if noncount_notes:
                reasons.append("no countable evidence: " + "; ".join(sorted(set(noncount_notes))))
            else:
                reasons.append(
                    "no countable evidence: every item offered is discounted, "
                    "and discounted evidence never counts"
                )
        else:
            reasons.append("no evidence offered")
    else:
        level_ok = best_level >= required_level
        if not level_ok:
            reasons.append(
                f"best evidence level is {_level_label(best_level)}, below the "
                f"required level {_level_label(required_level)} for a "
                f"'{ctype}' claim"
            )

        kind_ok = True
        required_kinds = KIND_REQUIREMENTS.get(ctype)
        if required_kinds is not None:
            kind_ok = any(
                kind in required_kinds and EVIDENCE_LEVELS[kind] >= required_level
                for kind in countable_kinds
            )
            if not kind_ok:
                kinds_txt = " or ".join(sorted(required_kinds))
                reasons.append(
                    f"a '{ctype}' claim requires evidence of kind {kinds_txt} "
                    f"at level {_level_label(required_level)}; none offered "
                    f"(offered kinds: {', '.join(sorted(set(countable_kinds))) or 'none'})"
                )

        verdict = VERDICT_SUPPORTED if (level_ok and kind_ok) else VERDICT_OVERCLAIMED

    return {
        "id": claim["id"],
        "type": ctype,
        "statement": claim["statement"],
        "verdict": verdict,
        "required_level": required_level,
        "required_level_name": LEVEL_NAMES[required_level],
        "best_level": best_level,
        "best_level_name": LEVEL_NAMES[best_level],
        "max_age_seconds": max_age,
        "reason": "; ".join(reasons),
        "evidence": evidence_out,
    }


def run_check(manifest_arg: str, now_arg: str | None = None, evidence_from=None) -> dict:
    errors: list[str] = []
    manifest_path = Path(manifest_arg).expanduser()
    manifest_label = str(manifest_path)

    data = None
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"manifest not found: {manifest_path}")
        raw = None
    except OSError as exc:
        errors.append(f"manifest cannot be read: {manifest_path}: {exc}")
        raw = None

    if raw is not None:
        try:
            manifest_label = str(manifest_path.resolve())
        except Exception:
            pass
        try:
            data = json.loads(raw)
        except Exception as exc:  # JSON parse error
            errors.append(f"manifest does not parse: {manifest_path}: {exc}")
            data = None

    ignored_fields: list[str] = []
    if data is not None:
        errors.extend(_validate_manifest(data))
        if isinstance(data, dict):
            ignored_fields = _find_ignored_fields(data)

    # Effective "now": --now flag wins, then manifest top-level
    # `now`, then the current UTC time. An unparseable effective
    # `now` is a usage error (INCOMPLETE / exit 2) — freshness
    # judged against a guessed instant would be a lie.
    now_dt = None
    now_source = None
    now_raw = None
    if not errors:
        if now_arg is not None:
            now_raw, now_source = now_arg, "--now flag"
        elif isinstance(data, dict) and data.get("now") is not None:
            now_raw, now_source = data.get("now"), "manifest 'now'"
        if now_raw is not None:
            now_dt, perr = _parse_iso8601(now_raw)
            if now_dt is None:
                errors.append(f"invalid {now_source}: {perr}")
        if now_dt is None and not errors:
            now_dt = datetime.now(timezone.utc)
            now_source = "current UTC time"
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
        now_source = now_source or "current UTC time (fallback; run is INCOMPLETE)"
    now_iso = now_dt.isoformat()

    derived_report: list[dict] = []
    derived_by_claim: dict[str, list[dict]] = {}
    if not errors and evidence_from:
        derived_by_claim, derived_report, derr = _load_derived_evidence(
            evidence_from, data["claims"])
        errors.extend(derr)
        # Mark derived entries so the report can tell them apart
        # from hand-asserted manifest evidence.
        for entries in derived_by_claim.values():
            for entry in entries:
                entry["_derived"] = True
        # Re-check claim evidence outputs' derived flag below.

    if errors:
        # Invalid manifest / usage error: INCOMPLETE, and no
        # per-claim verdict — a verdict computed on a malformed
        # claim set would be a lie.
        return _finish(
            verdict=VERDICT_INCOMPLETE,
            manifest=manifest_label,
            claims=[],
            errors=errors,
            now=now_iso,
            derived_evidence=derived_report,
            ignored_fields=ignored_fields,
        )

    claims_out = [
        _evaluate_claim(claim, now_dt, derived_by_claim.get(claim["id"]))
        for claim in data["claims"]
    ]
    # Positional derived flags (exact): manifest evidence comes
    # first in each claim's list, derived entries were appended.
    for claim, claim_out in zip(data["claims"], claims_out):
        n_manifest = len(claim["evidence"])
        for idx, ev_out in enumerate(claim_out["evidence"]):
            ev_out["derived"] = idx >= n_manifest

    overall = max((c["verdict"] for c in claims_out), key=lambda v: _SEVERITY[v])
    return _finish(
        verdict=overall,
        manifest=manifest_label,
        claims=claims_out,
        errors=[],
        now=now_iso,
        derived_evidence=derived_report,
        ignored_fields=ignored_fields,
    )


def _finish(*, verdict, manifest, claims, errors, now=None,
            derived_evidence=None, ignored_fields=None) -> dict:
    exit_code = {
        VERDICT_SUPPORTED: EXIT_SUPPORTED,
        VERDICT_OVERCLAIMED: EXIT_REJECTED,
        VERDICT_UNSUPPORTED: EXIT_REJECTED,
        VERDICT_INCOMPLETE: EXIT_INCOMPLETE,
    }[verdict]
    return {
        "verdict": verdict,
        "exit_code": exit_code,
        "manifest": manifest,
        "claims": claims,
        "errors": errors,
        "now": now,
        "derived_evidence": list(derived_evidence or []),
        "ignored_fields": list(ignored_fields or []),
    }


def _print_human(result: dict) -> None:
    print(f"proof-check: {result['verdict']}")
    print(f"  manifest: {result['manifest']}")
    if result.get("now"):
        print(f"  now: {result['now']}")
    if result["claims"]:
        print("  claims:")
        for claim in result["claims"]:
            line = (
                f"    - {claim['id']}: {claim['verdict']} "
                f"(type={claim['type']}, "
                f"required level {_level_label(claim['required_level'])}, "
                f"best evidence level {_level_label(claim['best_level'])})"
            )
            if claim["verdict"] != VERDICT_SUPPORTED and claim["reason"]:
                line += f" — {claim['reason']}"
            print(line)
            for ev in claim["evidence"]:
                notes = []
                if ev["discounted"]:
                    note = "discounted, does not count"
                    if ev.get("discount_reason"):
                        note += f": {ev['discount_reason']}"
                    notes.append(note)
                if ev.get("freshness") == "stale":
                    notes.append(
                        f"stale, does not count (age {ev.get('age_seconds')}s > "
                        f"max {ev.get('max_age_seconds')}s)")
                elif ev.get("freshness") == "invalid":
                    notes.append(f"invalid, does not count ({ev.get('invalid_reason')})")
                elif ev.get("freshness") == "undated":
                    notes.append("undated")
                if ev.get("derived"):
                    notes.append(f"derived from {ev.get('source')}")
                if notes:
                    print(
                        f"      evidence: {ev['kind']} "
                        f"(level {_level_label(ev['level'])}) — {'; '.join(notes)}"
                    )
    if result.get("derived_evidence"):
        print("  derived evidence:")
        for d in result["derived_evidence"]:
            if d["outcome"] == "derived":
                print(f"    - {d['source']}: derived {d['kind']} for claim {d['claim_id']!r}")
            else:
                print(f"    - {d['source']}: skipped — {d['reason']}")
    if result.get("ignored_fields"):
        print("  ignored manifest fields (tool-owned limits cannot be overridden):")
        for f in result["ignored_fields"]:
            print(f"    - {f}")
    if result["errors"]:
        print("  errors:")
        for e in result["errors"]:
            print(f"    - {e}")
    print(f"  exit: {result['exit_code']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="proof-check",
        description="Check that each claim's evidence meets the level (and kind) the claim requires.",
    )
    parser.add_argument("manifest", help="Path to the claims manifest JSON")
    parser.add_argument("--json", action="store_true", help="Emit one JSON object")
    parser.add_argument("--now", default=None,
                        help="Reference instant for freshness, ISO-8601 with timezone "
                             "(overrides the manifest's top-level 'now')")
    parser.add_argument("--evidence-from", action="append", default=None,
                        metavar="FILE",
                        help="Derive evidence from a settle-check / merge-verify JSON "
                             "artifact; repeatable")
    args = parser.parse_args(argv)

    result = run_check(manifest_arg=args.manifest, now_arg=args.now,
                       evidence_from=args.evidence_from)

    if args.json:
        print(json.dumps(result))
    else:
        _print_human(result)

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
