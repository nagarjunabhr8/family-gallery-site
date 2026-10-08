"""Prove a photo folder was not modified by the app.

    python scripts/verify_readonly.py snapshot "D:\\Photos\\Sample"
    ... run scans in the app ...
    python scripts/verify_readonly.py compare "D:\\Photos\\Sample"

Records every file's size, modified time and SHA-256. The snapshot is stored in
the app data folder (never inside the photo folder).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import safety  # noqa: E402
from app.config import default_data_dir  # noqa: E402


def take(root: Path) -> dict[str, list]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h = hashlib.sha256()
            with safety.open_source(p) as f:
                while block := f.read(1 << 20):
                    h.update(block)
            st = p.stat()
            out[p.relative_to(root).as_posix()] = [st.st_size, st.st_mtime_ns, h.hexdigest()]
    return out


def snapshot_file(root: Path) -> Path:
    key = hashlib.sha256(str(root).lower().encode()).hexdigest()[:16]
    return safety.data_dir() / "readonly-snapshots" / f"{key}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["snapshot", "compare"])
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    root = args.folder.resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 2
    safety.set_data_dir(default_data_dir())
    target = snapshot_file(root)

    current = take(root)
    if args.action == "snapshot":
        safety.safe_write_bytes(target, json.dumps({"folder": str(root), "files": current}).encode())
        print(f"Snapshot of {len(current)} files saved to {target}")
        return 0

    if not target.is_file():
        print("No snapshot yet. Run 'snapshot' first.")
        return 2
    before = json.loads(target.read_text())["files"]
    added = sorted(set(current) - set(before))
    removed = sorted(set(before) - set(current))
    changed = sorted(k for k in set(before) & set(current) if before[k] != current[k])
    for label, names in (("ADDED", added), ("REMOVED", removed), ("CHANGED", changed)):
        for n in names:
            print(f"{label}: {n}")
    if added or removed or changed:
        print(f"FAIL: {len(added)} added, {len(removed)} removed, {len(changed)} changed")
        return 1
    print(f"OK: all {len(current)} files unchanged (size, modified time, SHA-256)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
