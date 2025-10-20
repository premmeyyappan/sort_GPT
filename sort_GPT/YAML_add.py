#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import re

YAML_RE = re.compile(r"^---\n[\s\S]*?\n---\n", re.DOTALL)

def extract_yaml(text: str) -> str | None:
    """Return the YAML block (including --- lines) if present, else None."""
    m = YAML_RE.match(text.replace("\r\n", "\n").replace("\r", "\n"))
    if m:
        block = m.group(0)
        return block if block.endswith("\n") else block + "\n"
    return None

def main():
    ap = argparse.ArgumentParser(
        description="Copy YAML frontmatter from Final_MD notes into YAML_content/ (skip if no YAML)."
    )
    ap.add_argument(
        "--final",
        required=True,
        help="Path to the Final_MD folder."
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Output folder for YAML-only copies (default: <parent_of_final>/YAML_content)."
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without making changes."
    )
    args = ap.parse_args()

    final_dir = Path(args.final).resolve()
    if not final_dir.is_dir():
        # If Final_MD doesn’t exist, silently exit
        sys.exit(0)

    out_dir = Path(args.out).resolve() if args.out else final_dir.parent / "YAML_content"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped_no_yaml = 0
    skipped_assets = 0

    for src in final_dir.rglob("*.md"):
        if any(part == "_assets" for part in src.parts):
            skipped_assets += 1
            continue

        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[WARN] Could not read {src}: {e}")
            continue

        yaml_block = extract_yaml(text)
        if not yaml_block:
            skipped_no_yaml += 1
            continue

        rel = src.relative_to(final_dir)
        dst = out_dir / rel
        if args.dry_run:
            print(f"[DRY] would write YAML for {rel}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(yaml_block, encoding="utf-8")
        written += 1

    print(f"\nYAML_add complete.")
    print(f"  YAML-only files written: {written}")
    print(f"  Skipped (no YAML): {skipped_no_yaml}")
    if skipped_assets:
        print(f"  Skipped inside _assets/: {skipped_assets}")
    print(f"  Output directory: {out_dir}")

if __name__ == "__main__":
    main()