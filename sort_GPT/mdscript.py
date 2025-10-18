#!/usr/bin/env python3
import json, re, os, argparse, zipfile, unicodedata, datetime, shutil, secrets
from pathlib import Path

# ---------------------------
# Helpers
# ---------------------------

def safe_filename(name: str, maxlen=80):
    # ASCII-ish, strip risky chars
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^\w\s\-\.\(\)]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "untitled"
    return name[:maxlen]

def ts_to_iso(ts):
    if not ts:
        return ""
    try:
        if ts > 1e12:
            ts = ts / 1000.0  # ms → s
        return datetime.datetime.fromtimestamp(ts, datetime.UTC).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""

def short_id(s: str, n=8):
    if not s:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(s))[:n]

def coalesce(*vals):
    for v in vals:
        if v:
            return v
    return None

# ---------------------------
# Image indexing & resolve
# ---------------------------

def build_file_index(data, conversations):
    """
    Build {file_id -> filename} from common export shapes.
    Works whether `data` is a dict or a top-level list.
    """
    index = {}

    # A) Top-level arrays if data is a dict
    if isinstance(data, dict):
        for key in ("files", "assets"):
            arr = data.get(key)
            if isinstance(arr, list):
                for obj in arr:
                    fid = obj.get("id") or obj.get("file_id") or obj.get("asset_id")
                    name = obj.get("name") or obj.get("filename")
                    if fid and name:
                        index[fid] = name

    # B) Per-conversation attachments
    for conv in conversations:
        for key in ("files", "assets"):
            arr = conv.get(key)
            if isinstance(arr, list):
                for obj in arr:
                    fid = obj.get("id") or obj.get("file_id") or obj.get("asset_id")
                    name = obj.get("name") or obj.get("filename")
                    if fid and name:
                        index[fid] = name

    return index

def resolve_image_filename(part, file_index):
    """
    Return (file_id, filename_guess_or_none) for an image 'part'.
    Safe on non-dicts and weird shapes; never raises.
    """
    if not isinstance(part, dict):
        return "", None

    def get_d(d, k, default=None):
        return d[k] if (isinstance(d, dict) and k in d) else default

    # Try common id fields
    fid = (
        get_d(part, "file_id")
        or get_d(part, "id")
        or get_d(part, "asset_id")
        or get_d(get_d(part, "asset_pointer", {}), "file_id")
    )

    # Sometimes name/filename is provided directly
    explicit_name = get_d(part, "filename") or get_d(part, "name")

    if fid and fid in file_index:
        return fid, file_index[fid]
    if explicit_name:
        return fid or "", explicit_name

    return fid or "", None

# ---------------------------
# Fallback: find image by file_id in images folder
# ---------------------------

def find_image_by_file_id(src_images: Path, fid: str):
    """
    Fallback: try to locate an image file in src_images by matching file_id tokens.
    Returns a Path or None.
    """
    if not fid or not src_images.is_dir():
        return None
    needle = fid.lower()
    variants = set([
        needle,
        needle.replace("file-", ""),
        needle.replace("file_", ""),
        needle.replace("-", ""),
        needle.replace("_", ""),
    ])
    try:
        for p in src_images.iterdir():
            if not p.is_file():
                continue
            name = p.name.lower()
            raw = name.replace("-", "").replace("_", "")
            if any(v and (v in name or v in raw) for v in variants):
                return p
    except Exception:
        return None
    return None

# ---------------------------
# Attachment collector (outside content.parts)
# ---------------------------

def collect_attachments(obj):
    """
    Collects any attachments that may reference images/files from either:
    - obj['attachments'] (array of dicts)
    - obj['metadata']['attachments'] (array of dicts)
    Returns a list (possibly empty) of dicts.
    """
    imgs = []
    if not isinstance(obj, dict):
        return imgs

    atts = obj.get("attachments") or []
    for a in atts:
        if isinstance(a, dict):
            imgs.append(a)

    meta = obj.get("metadata") or {}
    meta_atts = meta.get("attachments") or []
    for a in meta_atts:
        if isinstance(a, dict):
            imgs.append(a)

    return imgs

# ---------------------------
# Message extraction (text + images)
# ---------------------------

def extract_messages(conv):
    """
    Returns a list of messages:
    [{"role": "user"/"assistant", "text": "...", "ts": 123, "images":[{...}]}]
    Supports "new" format (messages list) and "legacy mapping".
    """
    def parts_to_text_and_images(parts):
        text_chunks = []
        images = []
        for p in (parts or []):
            if isinstance(p, dict):
                typ = p.get("type") or p.get("content_type")
                # Treat as text
                if (typ == "text" and "text" in p) or ("text" in p and isinstance(p.get("text"), str)):
                    text_chunks.append(str(p.get("text") or ""))
                    continue
                # Treat as image-like only if it clearly references a file/asset
                if (
                    typ in ("image_file", "image", "image_asset", "image_url")
                    or "file_id" in p or "asset_id" in p or "asset_pointer" in p
                    or "filename" in p or "name" in p
                ):
                    images.append(p)
                    continue
                # Fallback: unknown dict—stringify to text
                s = str(p)
                if s:
                    text_chunks.append(s)
            elif isinstance(p, str):
                # Plain strings are text, not images
                text_chunks.append(p)
            else:
                # Last resort
                s = str(p)
                if s:
                    text_chunks.append(s)
        return "\n".join([t for t in text_chunks if t]), images

    # Newer format
    if isinstance(conv.get("messages"), list):
        out = []
        for m in conv["messages"]:
            role = (m.get("author") or {}).get("role") or m.get("role") or "assistant"
            c = m.get("content") or {}
            text = ""
            imgs = []
            if isinstance(c, str):
                text = c
            else:
                typ = c.get("content_type")
                if typ == "text":
                    text = "\n".join(c.get("parts") or [])
                elif typ == "multimodal_text":
                    text, imgs = parts_to_text_and_images(c.get("parts") or [])
                elif "text" in c:
                    text = c.get("text", "")
            # Also include any attachments at the message level
            imgs = (imgs or []) + collect_attachments(m)
            out.append({"role": role, "text": text or "", "ts": m.get("create_time"), "images": imgs})
        return out

    # Legacy mapping graph
    mapping = conv.get("mapping") or {}
    if mapping:
        order = []
        roots = [n for n in mapping.values() if not n.get("parent")]
        seen = set()
        def walk(node):
            nid = id(node)
            if nid in seen:
                return
            seen.add(nid)
            msg = node.get("message") or {}
            if msg:
                role = (msg.get("author") or {}).get("role") or "assistant"
                c = msg.get("content") or {}
                text = ""
                imgs = []
                ctype = c.get("content_type")
                if ctype == "text":
                    text = "\n".join(c.get("parts") or [])
                elif ctype == "multimodal_text":
                    text, imgs = parts_to_text_and_images(c.get("parts") or [])
                # Also include attachments on the message itself
                imgs = (imgs or []) + collect_attachments(msg)
                order.append({"role": role, "text": text or "", "ts": msg.get("create_time"), "images": imgs})
            for cid in node.get("children") or []:
                child = mapping.get(cid)
                if child:
                    walk(child)
        if roots:
            for r in roots:
                walk(r)
        else:
            for n in mapping.values():
                walk(n)
        return order

    return []

# ---------------------------
# Markdown rendering (with image embeds)
# ---------------------------

def render_markdown(title, created_iso, conv_id, model, msgs, embed_records):
    """
    embed_records is a list of (message_index, embed_lines) we append after that message's text.
    """
    lines = [f"# {title}", ""]
    meta = []
    if created_iso:
        meta.append(f"**Created:** {created_iso}")
    if conv_id:
        meta.append(f"**ID:** {conv_id}")
    if model:
        meta.append(f"**Model:** {model}")
    if meta:
        lines.append("  • " + "  •  ".join(meta))
        lines.append("")
    for i, m in enumerate(msgs):
        role = (m.get("role") or "assistant").upper()
        text = (m.get("text") or "").strip()
        has_embeds = any(er[0] == i for er in embed_records)
        if not text and not has_embeds:
            continue
        lines.append(f"**{role}**")
        lines.append("")
        if text:
            lines.append(text)
            lines.append("")
        for idx, embeds in embed_records:
            if idx == i and embeds:
                lines.extend(embeds)
                if not embeds[-1].endswith("\n"):
                    lines.append("")
        lines.append("")
    out = "\n".join(lines).rstrip() + "\n"
    return out.replace("\r\n", "\n").replace("\r", "\n")

def maybe_split(text, base_name, limit):
    if limit <= 0 or len(text) <= limit:
        return [(base_name, text)]
    parts = []
    i = 0
    part = 1
    while i < len(text):
        j = min(i + limit, len(text))
        k = text.rfind("\n\n", i, j)
        if k == -1 or k <= i + int(limit * 0.6):
            k = j
        chunk = text[i:k].rstrip() + "\n"
        suffix = f" (part {part})"
        fname = f"{base_name}{suffix}"
        nav_top = f"_This is part {part} of multiple._\n\n"
        parts.append((fname, nav_top + chunk))
        i = k
        part += 1
    for idx in range(len(parts)):
        prev_link = f"_Prev: {parts[idx-1][0]}_" if idx > 0 else ""
        next_link = f"_Next: {parts[idx+1][0]}_" if idx < len(parts) - 1 else ""
        tail = "\n" + "  •  ".join(x for x in [prev_link, next_link] if x) + "\n"
        parts[idx] = (parts[idx][0], parts[idx][1] + tail)
    return parts

# ---------------------------
# Main
# ---------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to conversations.json")
    p.add_argument("--out", required=True, help="Output folder for Markdown files")
    p.add_argument("--split-chars", type=int, default=0, help="Max characters per file (0 = no split).")
    p.add_argument("--zip", action="store_true", help="Zip the generated Markdown files")
    p.add_argument("--assets-src", default=None, help="Override source images folder (defaults to '<input_dir>/images' or '<input_dir>/files')")
    p.add_argument("--assets-subdir", default="_assets", help="Subfolder inside --out for copied images")
    p.add_argument("--verbose", action="store_true", help="Print debug info while processing")
    args = p.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # Load JSON
    raw = Path(args.input).read_text(encoding="utf-8")
    data = json.loads(raw)
    conversations = data if isinstance(data, list) else data.get("conversations") or data.get("items") or []

    # Source images directory
    input_dir = Path(args.input).parent
    if args.assets_src:
        src_images = Path(args.assets_src)
    else:
        # Prefer 'images/', fallback to 'files/' (both are common)
        cand1 = input_dir / "images"
        cand2 = input_dir / "files"
        src_images = cand1 if cand1.is_dir() else cand2
    if args.verbose:
        print(f"[debug] src_images dir: {src_images} (exists={src_images.is_dir()})")
        try:
            count_src = len(list(src_images.glob("*"))) if src_images.is_dir() else 0
        except Exception:
            count_src = 0
        print(f"[debug] src_images file count: {count_src}")

    if not src_images.is_dir():
        print(f"WARNING: Could not find images folder at {src_images}. Image embeds will be placeholders.")

    # Build file_id -> filename index if present
    file_index = build_file_index(data, conversations)
    if args.verbose:
        print(f"[debug] file_index entries: {len(file_index)}")

    # Destination assets folder (single shared folder)
    assets_dir = outdir / args.assets_subdir
    assets_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for idx, conv in enumerate(conversations, 1):
        title = conv.get("title") or f"Chat {idx}"
        created = ts_to_iso(conv.get("create_time"))
        conv_id = conv.get("id", "")
        model = conv.get("model") or ""
        msgs = extract_messages(conv)

        if args.verbose:
            total_imgs = sum(len(m.get("images") or []) for m in msgs)
            print(f"[debug] {title[:50]!r}: messages={len(msgs)}, images_found={total_imgs}")

        # Prepare a readable, unique-ish base filename
        date_prefix = (created[:10] if created else "0000-00-00")
        base = f"{date_prefix} - {safe_filename(title)} - {short_id(conv_id) or idx}"

        # For embedding images: walk messages and copy image files
        embed_records = []  # list of (message_index, [embed_lines])
        for m_i, m in enumerate(msgs):
            img_parts = m.get("images") or []
            if not img_parts:
                continue
            embed_lines = []
            img_counter = 1
            for part in img_parts:
                # Skip weird non-dict "image" entries defensively
                if not isinstance(part, dict):
                    embed_lines.append("> ⚠️ Unrecognized image reference (not a dict)\n")
                    continue

                file_id, resolved_name = resolve_image_filename(part, file_index)

                # Find source file
                src_path = None
                # 1) direct resolved name from manifest
                if resolved_name and src_images.is_dir():
                    cand = src_images / resolved_name
                    if cand.is_file():
                        src_path = cand
                # 2) explicit filename on the part
                if not src_path:
                    explicit = part.get("filename") or part.get("name")
                    if explicit:
                        cand2 = src_images / explicit
                        if cand2.is_file():
                            src_path = cand2
                # 3) fallback: try to locate by file_id
                if not src_path and file_id:
                    guess = find_image_by_file_id(src_images, file_id)
                    if guess and guess.is_file():
                        src_path = guess

                # if still missing, we can't embed the image
                if not src_path or not src_path.is_file():
                    fid_label = file_id or "unknown-file"
                    embed_lines.append(f"> ⚠️ Missing image for {fid_label}\n")
                    if args.verbose:
                        print(f"[debug]   missing: fid={fid_label} name={resolved_name or explicit or 'None'}")
                    continue

                if args.verbose:
                    print(f"[debug]   resolved image: {src_path.name} (fid={file_id or 'n/a'})")

                # Decide destination filename (with collision-safe suffix on demand)
                ext = src_path.suffix.lower() or ".png"
                basename = f"{date_prefix}_{safe_filename(title, 40).replace(' ', '-')}_{short_id(conv_id) or idx}_msg{m_i+1:03d}_img{img_counter:02d}"
                dest_name = f"{basename}{ext}"
                dest_path = assets_dir / dest_name

                # Add short unique suffix if collision
                if dest_path.exists():
                    suffix = short_id(file_id, 5) if file_id else secrets.token_hex(2)
                    dest_name = f"{basename}_{suffix}{ext}"
                    dest_path = assets_dir / dest_name

                # Copy file
                try:
                    shutil.copy2(src_path, dest_path)
                except Exception as e:
                    embed_lines.append(f"> ⚠️ Failed to copy image: {src_path.name} ({e})\n")
                    continue

                # Obsidian embed (relative to the note location)
                rel = f"{args.assets_subdir}/{dest_name}"
                embed_lines.append(f"![[ {rel} ]]\n")
                img_counter += 1

            if embed_lines:
                embed_records.append((m_i, embed_lines))

        # Render full markdown with embeds placed under their messages
        md = render_markdown(title, created, conv_id, model, msgs, embed_records)

        # Write file(s) (with optional split)
        for fname, body in maybe_split(md, base, args.split_chars):
            (outdir / f"{safe_filename(fname)}.md").write_bytes(body.encode("utf-8"))
            count += 1

    # Optional zip of the .md files (images are not zipped; just notes)
    if args.zip:
        zpath = outdir.with_suffix(".zip")
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for pth in outdir.glob("*.md"):
                zf.write(pth, arcname=pth.name)
        print(f"ZIP: {zpath}")

    print(f"Wrote {count} Markdown files to {outdir}")
    print(f"Images (if any) copied into: {assets_dir}")

if __name__ == "__main__":
    main()
