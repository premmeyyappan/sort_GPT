#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    # (human label, argv list builder function)
    ("cleanup",               lambda a: [sys.executable, "cleanup.py"]),
    ("mdscript",              lambda a: [sys.executable, "mdscript.py", "--input", "conversations.json", "--out", "Chats_MD", *a.mdscript_extra]),
    ("yaml_add",              lambda a: [sys.executable, "YAML_add.py", "--final", "Final_MD"]),
    ("dedupe_finalize",       lambda a: [sys.executable, "dedupe_finalize.py", "--staging", "Chats_MD", "--final", "Final_MD"]),
    ("yaml_check",            lambda a: [sys.executable, "YAML_check.py", "--final", "Final_MD", "--yaml", "YAML_content"]),
    ("frontmatter_llm",       lambda a: [sys.executable, "frontmatter_llm.py", "--root", "Final_MD", "--workers", str(a.workers), *( ["--until-done"] if a.until_done else [] ), *a.frontmatter_extra]),
    ("mover",                 lambda a: [sys.executable, "mover.py"]),
]

def run_step(label: str, cmd: list[str], dry: bool):
    print(f"\n=== {label}: {' '.join(cmd)}")
    if dry:
        print("[DRY] Skipping execution")
        return 0
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"[ERROR] Step '{label}' failed with exit code {proc.returncode}. Aborting.")
    return proc.returncode

def main():
    ap = argparse.ArgumentParser(description="Run the Sort_GPT pipeline end-to-end.")
    ap.add_argument("--workers", type=int, default=1, help="Workers for frontmatter_llm.py (default 1).")
    ap.add_argument("--until-done", action="store_true", help="Pass --until-done to frontmatter_llm.py.")
    ap.add_argument("--skip-mover", action="store_true", help="Skip the mover.py step.")
    ap.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    ap.add_argument("--mdscript-extra", nargs=argparse.REMAINDER, default=[], help="Extra args appended to mdscript.py after --out Chats_MD. Prefix with --mdscript-extra -- ... to pass.")
    ap.add_argument("--frontmatter-extra", nargs=argparse.REMAINDER, default=[], help="Extra args appended to frontmatter_llm.py. Prefix with --frontmatter-extra -- ... to pass.")
    args = ap.parse_args()

    # Ensure we’re in the folder with the scripts
    here = Path(__file__).resolve().parent
    scripts_present = ["cleanup.py","mdscript.py","YAML_add.py","dedupe_finalize.py","YAML_check.py","frontmatter_llm.py","mover.py"]
    missing = [s for s in scripts_present if not (here / s).exists()]
    if missing:
        print(f"[WARN] Missing expected scripts in {here}: {', '.join(missing)}")
        # Not fatal—maybe user intentionally removed mover.py, etc.

    # Build command list
    commands = []
    for label, builder in SCRIPTS:
        if label == "mover" and args.skip_mover:
            continue
        commands.append((label, builder(args)))

    # Run in order, stop on first error
    for label, cmd in commands:
        code = run_step(label, cmd, args.dry_run)
        if code != 0:
            sys.exit(code)

    print("\n✅ All steps completed successfully.")

if __name__ == "__main__":
    main()
