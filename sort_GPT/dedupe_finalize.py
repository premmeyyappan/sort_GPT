#!/usr/bin/env python3
import argparse
import re
import shutil
import sys
from pathlib import Path

YAML_RE = re.compile(r"^---\n[\s\S]*?\n---\n", re.DOTALL)

def strip_yaml(text: str) -> str:
    """Remove YAML frontmatter from a markdown string."""
    return YAML_RE.sub("", text, count=1)

def normalize_text(text: str) -> str:
    """Normalize CRLF and trim edges for comparison."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()

def bodies_identical_ignoring_yaml(a_path: Path, b_path: Path) -> bool:
    try:
        a = normalize_text(strip_yaml(a_path.read_text(encoding="utf-8", errors="ignore")))
        b = normalize_text(strip_yaml(b_path.read_text(encoding="utf-8", errors="ignore")))
        return a == b
    except Exception:
        return False

def ensure_dir(p: Path, dry: bool):
    if not p.exists():
        if dry:
            print(f"[DRY] mkdir -p {p}")
        else:
            p.mkdir(parents=True, exist_ok=True)

def safe_move(src: Path, dst: Path, dry: bool):
    ensure_dir(dst.parent, dry)
    if dry:
        print(f"[DRY] mv {src} -> {dst}")
    else:
        shutil.move(str(src), str(dst))

def safe_delete(p: Path, dry: bool):
    if dry:
        print(f"[DRY] rm {p}")
    else:
        try:
            p.unlink()
        except IsADirectoryError:
            shutil.rmtree(p, ignore_errors=True)

def dir_empty(p: Path) -> bool:
    return not any(p.iterdir())

def validate_paths(staging: Path, final: Path):
    if staging.resolve() == final.resolve():
        print("ERROR: --staging and --final must be different paths.")
        sys.exit(1)
    # Avoid destructive nested case like final inside staging or vice-versa
    try:
        if staging.resolve() in final.resolve().parents:
            print("ERROR: --final may not be inside --staging.")
            sys.exit(1)
        if final.resolve() in staging.resolve().parents:
            print("ERROR: --staging may not be inside --final.")
            sys.exit(1)
    except Exception:
        pass

def purge_hidden_junk(root: Path, dry: bool):
    """Remove macOS/hidden junk files that block empty-dir deletes."""
    patterns = {".DS_Store"}
    removed = 0
    for p in root.rglob("*"):
        if p.is_file():
            name = p.name
            if name in patterns or name.startswith("._"):
                if dry:
                    print(f"[DRY] rm hidden {p}")
                else:
                    try:
                        p.unlink()
                        removed += 1
                    except Exception:
                        pass
    return removed

def list_residuals(root: Path):
    """Return a small list of what's left inside root (relative paths)."""
    out = []
    for p in root.rglob("*"):
        # skip directories; we care about “any content at all”
        out.append(str(p.relative_to(root)))
        if len(out) >= 30:
            break
    return out

def looks_nontrivial(root: Path) -> bool:
    """True if there are any 'real' files left (e.g., md, images, _assets)."""
    for p in root.rglob("*"):
        if p.is_file():
            # consider anything except hidden junk as nontrivial
            if p.name == ".DS_Store" or p.name.startswith("._"):
                continue
            return True
        elif p.is_dir():
            if p.name == "_assets":
                return True
    return False

def main():
    ap = argparse.ArgumentParser(
        description="Promote markdown files from Chats_MD (staging) into Final_MD (library), "
                    "comparing bodies while ignoring YAML. Also merges _assets. "
                    "If Final_MD doesn't exist, renames Chats_MD to Final_MD and exits."
    )
    ap.add_argument("--staging", required=True, help="Path to staging folder (e.g., Chats_MD)")
    ap.add_argument("--final", required=True, help="Path to final folder (e.g., Final_MD)")
    ap.add_argument("--dry-run", action="store_true", help="Show actions without making changes")
    args = ap.parse_args()

    staging = Path(args.staging)
    final = Path(args.final)
    dry = args.dry_run

    if not staging.is_dir():
        print(f"ERROR: Staging folder not found: {staging}")
        sys.exit(1)

    validate_paths(staging, final)

    # First-run behavior: if Final_MD does not exist, rename staging -> final and exit.
    if not final.exists():
        if dry:
            print(f"[DRY] mv {staging} -> {final}")
        else:
            staging.rename(final)
        print("Final folder did not exist; staging was promoted. Done.")
        return

    # Process markdown files in staging (top-level and subfolders)
    # We will mirror relative paths into final.
    staged_md = sorted(staging.rglob("*.md"))
    moved = replaced = deleted_dupes = created = 0

    for src in staged_md:
        # Ignore anything inside _assets
        if any(part == "_assets" for part in src.parts):
            continue

        rel = src.relative_to(staging)
        dst = final / rel

        if not dst.exists():
            # New file → move to final
            safe_move(src, dst, dry)
            created += 1
            continue

        # Exists in both → compare bodies ignoring YAML
        if bodies_identical_ignoring_yaml(src, dst):
            # Duplicate → remove staging copy
            if dry:
                print(f"[DRY] duplicate (ignoring YAML), removing staging copy: {src}")
            else:
                src.unlink()
            deleted_dupes += 1
        else:
            # Different → replace final with staging (YAML-free)
            if dry:
                print(f"[DRY] replace {dst} with {src}")
            else:
                dst.unlink()  # remove old final version
                shutil.move(str(src), str(dst))
            replaced += 1

    # Merge _assets: move missing files; delete duplicates from staging assets to empty the folder.
    staging_assets = staging / "_assets"
    final_assets = final / "_assets"

    assets_moved = assets_dupe_removed = 0
    if staging_assets.is_dir():
        ensure_dir(final_assets, dry)
        for apath in sorted(staging_assets.rglob("*")):
            if apath.is_dir():
                continue
            rel = apath.relative_to(staging_assets)
            bpath = final_assets / rel
            if not bpath.exists():
                # move missing
                safe_move(apath, bpath, dry)
                assets_moved += 1
            else:
                # duplicate → remove from staging to empty it
                if dry:
                    print(f"[DRY] duplicate asset, removing staging copy: {apath}")
                else:
                    apath.unlink()
                assets_dupe_removed += 1

        # Clean up any now-empty dirs inside staging/_assets
        if not dry:
            for d in sorted(staging_assets.rglob("*"), reverse=True):
                try:
                    if d.is_dir() and dir_empty(d):
                        d.rmdir()
                except Exception:
                    pass

    # ---------- Robust final cleanup of staging ----------
    try:
        if not dry:
            # Remove any hidden junk files that keep folders "non-empty"
            purge_hidden_junk(staging, dry=False)

            # Remove any empty dirs under staging
            for d in sorted(staging.rglob("*"), reverse=True):
                if d.is_dir() and dir_empty(d):
                    try:
                        d.rmdir()
                    except Exception:
                        pass

        # If root is empty now, remove it
        if dir_empty(staging):
            if dry:
                print(f"[DRY] rmdir {staging}")
            else:
                staging.rmdir()
            print("Staging folder is now empty and has been removed.")
        else:
            # If not empty, check whether only trivial leftovers remain; if so, force-remove
            if not dry:
                if not looks_nontrivial(staging):
                    # Only trivial junk remains; force remove everything
                    shutil.rmtree(staging, ignore_errors=False)
                    print("Staging folder had only hidden/trivial leftovers and was removed.")
                else:
                    # Real content remains; show a short listing
                    rem = list_residuals(staging)
                    print("Note: Staging folder not empty; inspect remaining files, e.g.:")
                    for r in rem:
                        print("  -", r)
            else:
                print("Note: Staging folder not empty (dry-run).")
    except Exception as e:
        print(f"Warning: Could not fully remove staging folder: {e}")

    # Summary
    print("\nSummary:")
    print(f"  New files moved:        {created}")
    print(f"  Replaced updated files: {replaced}")
    print(f"  Staging dupes deleted:  {deleted_dupes}")
    print(f"  Assets moved:           {assets_moved}")
    print(f"  Assets dupes deleted:   {assets_dupe_removed}")
    if dry:
        print("\n(Dry-run: no changes were made.)")

if __name__ == "__main__":
    main()