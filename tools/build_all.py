"""Build every Profiles family and write BUILD_MANIFEST.json.

All families are built against one profiles-last-updated date, so the set is
consistent. The manifest lists every file written (path, rows, SHA-256, the spec
it was checked against and that spec's hash), each family's inputs and its notes
(rows left out and why). It holds no wall-clock time, so rebuilding from the same
lake on the same date gives a byte-identical manifest as well as identical files.

Run:  python tools/build_all.py [--as-of YYYY-MM-DD] [--only Cables,Demands]
"""

from __future__ import annotations

import argparse
import json

import build_cables
import build_demands
import build_generators
import build_interconnectors
import build_transformers
import profiles_common as pc

BUILDERS = {
    "Cables": build_cables,
    "Transformers": build_transformers,
    "Generator": build_generators,
    "Demands": build_demands,
    "Interconnects": build_interconnectors,
}
MANIFEST = pc.PROFILES_ROOT / "BUILD_MANIFEST.json"


def _plain(value):
    """Make notes JSON-safe (numpy and pandas scalars to Python)."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", help="profiles last-updated date, YYYY-MM-DD (default: latest available)")
    ap.add_argument("--only", help="comma-separated families to build (the manifest keeps the others' entries)")
    args = ap.parse_args(argv)
    families = list(BUILDERS) if not args.only else [f.strip() for f in args.only.split(",")]
    unknown = sorted(set(families) - set(BUILDERS))
    if unknown:
        raise pc.ProfilesError(f"unknown families {unknown}; known: {list(BUILDERS)}")

    lake = pc.lake_root()
    last_updated = pc.resolve_cutoff(args.as_of)
    manifest = {"profiles_last_updated": last_updated.date().isoformat(), "families": {}}
    if args.only and MANIFEST.exists():
        old = json.loads(MANIFEST.read_text(encoding="ascii"))
        if old.get("profiles_last_updated") != manifest["profiles_last_updated"]:
            raise pc.ProfilesError("--only would mix last-updated dates in one manifest "
                                   f"({old.get('profiles_last_updated')} and {manifest['profiles_last_updated']}); "
                                   "build every family instead")
        manifest["families"] = old["families"]

    for name in families:
        print(f"{name}:")
        report = BUILDERS[name].build(lake, last_updated)
        for f in report["files"]:
            print(f"  {f['path']}: {f['rows']} rows")
        manifest["families"][name] = _plain({k: report[k] for k in ("inputs", "files", "notes")})

    manifest["families"] = {k: manifest["families"][k] for k in BUILDERS if k in manifest["families"]}
    text = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
    MANIFEST.write_text(text, encoding="ascii", newline="\n")
    total = sum(f["rows"] for fam in manifest["families"].values() for f in fam["files"])
    print(f"manifest: {MANIFEST.name}, {total} profile rows, last updated {manifest['profiles_last_updated']}")
    return manifest


if __name__ == "__main__":
    main()
