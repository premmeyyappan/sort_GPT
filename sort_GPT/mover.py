#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import sys

def move_replace(src: Path, dst_dir: Path, dry: bool) -> bool:
    """Move src into dst_dir, overwriting same-named file if present. Returns True if moved."""
    if not src.exists() or not src.is_file():
        print(f"[SKIP] Not found or not a file: {src}")
        return False

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name

    # If source already in destination with same path, skip
    try:
        if src.resolve() == dst.resolve():
            print(f"[SKIP] Already in destination: {src}")
            return False
    except Exception:
        # On platforms where resolve() fails (rare), continue with best effort
        pass

    if dst.exists():
        if dry:
            print(f"[DRY] rm existing {dst}")
        else:
            if dst.is_dir():
                print(f"[ERR ] Destination path is a directory (won't overwrite): {dst}")
                return False
            dst.unlink()

    if dry:
        print(f"[DRY] mv {src} -> {dst}")
    else:
        try:
            shutil.move(str(src), str(dst))
        except Exception as e:
            print(f"[ERR ] Failed to move {src} -> {dst}: {e}")
            return False
    return True

def main():
    ap = argparse.ArgumentParser(
        description="Move specified files into Final_MD (default: dashboard.md, notes.md)."
    )
    ap.add_argument(
        "files", nargs="*", default=["dashboard.md", "notes.md"],
        help="Files to move into Final_MD (default: dashboard.md notes.md)."
    )
    ap.add_argument(
        "--final", default="Final_MD",
        help="Destination folder (default: Final_MD)"
    )
    ap.add_argument(
        "--root", default=".",
        help="Root directory where files and Final_MD live (default: current directory)."
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without changing anything."
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    final_dir = (root / args.final).resolve()
    if not root.is_dir():
        print(f"[ERR ] Root folder not found: {root}")
        sys.exit(1)

    moved = 0
    skipped = 0
    errors = 0

    for f in args.files:
        src_path = (root / f).resolve() if not Path(f).is_absolute() else Path(f)
        ok = move_replace(src_path, final_dir, args.dry_run)
        if ok:
            moved += 1
        else:
            # Distinguish silent skips from errors via message prefix (best-effort)
            # We treat anything that printed [ERR ] as error; others as skipped.
            # Since we can't easily intercept prints, we approximate by checking existence:
            if not src_path.exists():
                skipped += 1
            else:
                # existed but didn't move (e.g., dir conflict)
                errors += 1

    if args.dry_run:
        print("\n[DRY] Done. No changes made.")
    print(f"Summary: moved={moved} skipped={skipped} errors={errors}")
    sys.exit(0 if errors == 0 else 1)

if __name__ == "__main__":
    main()
