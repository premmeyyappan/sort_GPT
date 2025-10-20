#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import zipfile
import shutil
import tempfile
import os

# Image extensions we'll treat as "images"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"}

DELETE_THESE = {
    "users.json",
    "chat.html",
    "message_feedback.json",
    "shared_conversations.json",
}

def find_single_zip(root: Path) -> Path:
    zips = list(root.glob("*.zip"))
    if len(zips) != 1:
        print(f"ERROR: Expected exactly one .zip in {root}, found {len(zips)}.")
        for z in zips:
            print(f" - {z.name}")
        sys.exit(1)
    return zips[0]

def unique_dest(dest_dir: Path, name: str) -> Path:
    """Return a unique destination path under dest_dir if name already exists (for temp staging)."""
    base = Path(name).stem
    ext = Path(name).suffix
    candidate = dest_dir / name
    i = 2
    while candidate.exists():
        candidate = dest_dir / f"{base} ({i}){ext}"
        i += 1
    return candidate

def move_replace(src: Path, dst: Path, dry: bool):
    """Move src to dst, replacing any existing file/folder at dst."""
    if dst.exists():
        if dry:
            print(f"[DRY] rm -rf {dst}")
        else:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
    if dry:
        print(f"[DRY] mv {src} -> {dst}")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

def merge_images_into_root(images_src: Path, root_images: Path, dry: bool):
    """
    Merge files from images_src (flat folder) into root_images:
    - If root_images doesn't exist: just move images_src to root_images.
    - If root_images exists: move each file into it; on conflict, keep existing and delete new.
    """
    if not images_src.exists():
        print("Note: No images/ folder to merge.")
        return

    if not root_images.exists():
        # No existing images folder -> keep old behavior (move)
        if dry:
            print(f"[DRY] mv {images_src} -> {root_images}")
        else:
            root_images.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(images_src), str(root_images))
        return

    # Folder exists -> merge file-by-file
    moved = kept_existing = 0
    for f in images_src.iterdir():
        if not f.is_file():
            continue
        dst = root_images / f.name
        if dst.exists():
            # Conflict: keep existing, delete the new incoming file
            if dry:
                print(f"[DRY] conflict: keep existing {dst.name}; delete incoming {f.name}")
            else:
                try:
                    f.unlink()
                except Exception as e:
                    print(f"[WARN] Could not delete incoming duplicate {f}: {e}")
            kept_existing += 1
        else:
            if dry:
                print(f"[DRY] move image {f.name} -> {root_images / f.name}")
            else:
                try:
                    shutil.move(str(f), str(dst))
                except Exception as e:
                    print(f"[WARN] Could not move {f} -> {dst}: {e}")
                    continue
            moved += 1

    # Remove the now-empty temp images_src directory
    if dry:
        print(f"[DRY] rm -rf {images_src} (after merge)")
    else:
        try:
            shutil.rmtree(images_src, ignore_errors=True)
        except Exception as e:
            print(f"[WARN] Could not remove temp images folder {images_src}: {e}")

    print(f"Merged images: moved={moved}, kept_existing={kept_existing}")

def main():
    ap = argparse.ArgumentParser(
        description="Unzip a ChatGPT export, keep conversations.json + images, move to Sort_GPT root, clean the rest."
    )
    ap.add_argument(
        "--root",
        default=None,
        help="Path to Sort_GPT (default: directory containing this script)."
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions without making changes.")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent
    dry = args.dry_run

    if not root.is_dir():
        print(f"ERROR: Root folder not found: {root}")
        sys.exit(1)

    # 1) Locate the one zip
    zip_path = find_single_zip(root)
    print(f"Found zip: {zip_path.name}")

    # 2) Extract to a temp directory inside root
    extract_dir = root / f"__extract_{zip_path.stem}"
    if extract_dir.exists():
        if dry:
            print(f"[DRY] rm -rf {extract_dir}")
        else:
            shutil.rmtree(extract_dir, ignore_errors=True)
    if dry:
        print(f"[DRY] unzip {zip_path} -> {extract_dir}")
    else:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

    # 3) Delete throwaway files if present
    for name in DELETE_THESE:
        p = extract_dir / name
        if p.exists():
            if dry:
                print(f"[DRY] delete {p.relative_to(root)}")
            else:
                try:
                    p.unlink()
                except Exception as e:
                    print(f"[WARN] Could not delete {p}: {e}")

    # 4) Gather all images recursively into extract_dir / "images" (flat)
    images_out = extract_dir / "images"
    if not dry:
        images_out.mkdir(parents=True, exist_ok=True)

    gathered = 0
    for file in extract_dir.rglob("*"):
        if not file.is_file():
            continue
        if images_out in file.parents:
            continue
        if file.suffix.lower() in IMAGE_EXTS:
            target = images_out / file.name
            if target.exists():
                target = unique_dest(images_out, file.name)  # avoid intra-export collisions
            if dry:
                print(f"[DRY] move image {file.relative_to(extract_dir)} -> images/{target.name}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file), str(target))
            gathered += 1

    if gathered == 0:
        print("Note: No images found to gather.")

    # 5) Move conversations.json up to root (replace if exists)
    conversations_src = extract_dir / "conversations.json"
    if not conversations_src.exists():
        print("ERROR: conversations.json not found in the zip contents.")
        exit_code = 1
    else:
        move_replace(conversations_src, root / "conversations.json", dry)
        exit_code = 0

    # 6) Merge or move images to root
    root_images = root / "images"
    if images_out.exists():
        merge_images_into_root(images_out, root_images, dry)
    else:
        print("Note: No images/ folder to move or merge.")

    # 7) Delete the zip and the extraction folder
    if dry:
        print(f"[DRY] delete zip {zip_path}")
        print(f"[DRY] rm -rf {extract_dir}")
    else:
        try:
            zip_path.unlink()
        except Exception as e:
            print(f"[WARN] Could not delete zip {zip_path}: {e}")
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception as e:
            print(f"[WARN] Could not remove temp folder {extract_dir}: {e}")

    if dry:
        print("Dry run complete. No changes were made.")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()