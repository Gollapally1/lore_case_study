"""
Contract compatibility checker.

The pitch in TALKING_POINTS / ARCHITECTURE: "Schema changes are PR-reviewed
like any other API change. Backward-compatible additions auto-flow through;
breaking changes require a major version bump and a parallel topic during
the migration window."

This script is what the CI check on a contract PR runs. Given an old and a
new version of a contract YAML, it classifies each field-level change as:

  - additive:  new optional field, new allowed_value, new owner tag (safe)
  - breaking:  removed field, narrowed allowed_values, type change,
               nullable -> required (requires major version bump)
  - cosmetic:  description change, owner_email change (no version bump)

Exits 0 if the version bump matches the change class; exits 1 otherwise.

Usage:
    python src/check_schema_compat.py \\
        --old configs/engagement_events.yaml \\
        --new configs/engagement_events_v2_proposed.yaml
"""
import argparse
import sys
from pathlib import Path

import yaml


def _index(schema: list) -> dict:
    return {field["name"]: field for field in schema}


def classify_changes(old: dict, new: dict) -> dict:
    """Return {'additive': [...], 'breaking': [...], 'cosmetic': [...]}."""
    out = {"additive": [], "breaking": [], "cosmetic": []}

    old_fields = _index(old.get("schema", []))
    new_fields = _index(new.get("schema", []))

    # Removed fields are breaking.
    for name in old_fields.keys() - new_fields.keys():
        out["breaking"].append(f"field removed: {name}")

    # Added fields: additive if optional, breaking if required.
    for name in new_fields.keys() - old_fields.keys():
        if new_fields[name].get("nullable", True):
            out["additive"].append(f"field added (optional): {name}")
        else:
            out["breaking"].append(
                f"field added as required (existing producers will fail): {name}"
            )

    # Existing fields — compare type, nullable, allowed_values.
    for name in old_fields.keys() & new_fields.keys():
        o, n = old_fields[name], new_fields[name]
        if o.get("type") != n.get("type"):
            out["breaking"].append(
                f"type changed: {name} ({o.get('type')} -> {n.get('type')})"
            )
        # nullable: true -> false is breaking (existing nulls become invalid).
        if o.get("nullable", True) and not n.get("nullable", True):
            out["breaking"].append(
                f"nullability tightened: {name} (was nullable, now required)"
            )
        # nullable: false -> true is additive (more permissive).
        if not o.get("nullable", True) and n.get("nullable", True):
            out["additive"].append(f"nullability relaxed: {name}")

        # allowed_values changes
        o_vals, n_vals = set(o.get("allowed_values") or []), set(n.get("allowed_values") or [])
        if o_vals and n_vals:
            removed = o_vals - n_vals
            added = n_vals - o_vals
            if removed:
                out["breaking"].append(
                    f"allowed_values narrowed: {name} removed {sorted(removed)}"
                )
            if added:
                out["additive"].append(
                    f"allowed_values widened: {name} added {sorted(added)}"
                )
        elif o_vals and not n_vals:
            out["additive"].append(
                f"allowed_values constraint removed (now unconstrained): {name}"
            )
        elif not o_vals and n_vals:
            out["breaking"].append(
                f"allowed_values constraint added (existing values may not match): {name}"
            )

        # description / metadata: cosmetic
        if o.get("description") != n.get("description") and "description" in (o | n):
            out["cosmetic"].append(f"description changed: {name}")

    return out


def parse_version(v: str) -> tuple:
    try:
        return tuple(int(p) for p in v.split("."))
    except (AttributeError, ValueError):
        raise SystemExit(f"Invalid version string: {v}")


def required_bump(changes: dict) -> str:
    if changes["breaking"]:
        return "major"
    if changes["additive"]:
        return "minor"
    if changes["cosmetic"]:
        return "patch"
    return "none"


def actual_bump(old_v: tuple, new_v: tuple) -> str:
    if new_v == old_v:
        return "none"
    if new_v[0] > old_v[0]:
        return "major"
    if new_v[1] > old_v[1]:
        return "minor"
    if new_v[2] > old_v[2]:
        return "patch"
    return "downgrade"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, type=Path)
    parser.add_argument("--new", required=True, type=Path)
    args = parser.parse_args()

    old = yaml.safe_load(args.old.read_text())
    new = yaml.safe_load(args.new.read_text())

    old_v = parse_version(old["contract"]["version"])
    new_v = parse_version(new["contract"]["version"])

    changes = classify_changes(old, new)
    required = required_bump(changes)
    actual = actual_bump(old_v, new_v)

    print(f"\nContract: {old['contract']['name']}")
    print(f"  old version: {old['contract']['version']}")
    print(f"  new version: {new['contract']['version']}")
    print(f"\nChange classes:")
    for cls in ("breaking", "additive", "cosmetic"):
        if changes[cls]:
            print(f"  {cls}:")
            for c in changes[cls]:
                print(f"    - {c}")
    if not any(changes.values()):
        print("  (no schema changes)")

    print(f"\nRequired version bump: {required}")
    print(f"Actual version bump:   {actual}")

    if required == "major" and actual != "major":
        print("\nFAIL: breaking changes detected but version was not majored.")
        print("      Bump the major version and stand up a parallel topic per ARCHITECTURE.md.")
        return 1
    if required == "minor" and actual not in ("minor", "major"):
        print("\nFAIL: additive changes detected but version was not bumped.")
        return 1
    print("\nOK: version bump is consistent with the change class.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
