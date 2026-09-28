"""Fail if any installed distribution declares a strong-copyleft license (GPL/AGPL).

LGPL and unknown licenses are reported for review but do not fail the gate.
"""
import importlib.metadata as md
import sys

ALLOW_EXCEPTIONS: set[str] = set()  # distribution names the founder has explicitly cleared


def license_of(dist: md.Distribution) -> str:
    meta = dist.metadata
    parts = [meta.get("License-Expression") or "", meta.get("License") or ""]
    parts += [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return " | ".join(p for p in parts if p)[:300]


def main() -> int:
    bad, review = [], []
    for dist in md.distributions():
        name = (dist.metadata.get("Name") or "").lower()
        lic = license_of(dist)
        up = lic.upper()
        if name in ALLOW_EXCEPTIONS:
            continue
        if ("GPL" in up and "LGPL" not in up and "LESSER" not in up) or "AFFERO" in up:
            bad.append(f"{name}: {lic}")
        elif not lic or "LGPL" in up or "LESSER" in up:
            review.append(f"{name}: {lic or 'unknown'}")
    for r in review:
        print("REVIEW", r)
    for b in bad:
        print("BLOCKED", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
