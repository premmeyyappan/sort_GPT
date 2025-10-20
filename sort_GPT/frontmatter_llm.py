#!/usr/bin/env python3
# Pure stdlib parallel summarization with gpt-4o-mini (no pip, no venv, no JSON parsing)
import os, re, time, argparse, random, socket
from pathlib import Path
from urllib import request, error
from concurrent.futures import ThreadPoolExecutor, as_completed
import http.client as http_client
import json as _json

API_BASE = "https://api.openai.com/v1"
MODEL = "gpt-4o-mini"
MAX_WORKERS = 3            # parallel requests (safer default)
CHUNK_CHARS = 6000         # smaller chunks -> fewer disconnects
RETRY_LIMIT = 6
RETRY_BACKOFF = 2.0
DEBUG = False

# Skip exact (case-sensitive) basenames only
SKIP_BASENAMES = {"dashboard.md", "notes.md"}

# --------------------------
# Prompts (all plain text)
# --------------------------

MAP_PLAIN_PROMPT = """Extract 8–20 terse bullets (one fact/decision/topic per line) from this chat segment.

Rules:
- Be very terse. One idea per line.
- No prose, no numbering, no markdown bullets. Just lines of text.
- Capture every distinct topic/decision/number/step.
- Skip small talk/meta.

TEXT:
\"\"\"{chunk}\"\"\""""

REDUCE_PLAIN_PROMPT = """You will receive many bullet lines covering the whole conversation (all segments combined).

Write your output in this EXACT plain-text format (no JSON, no extra text):
SUMMARY:
<one paragraph that covers EVERY distinct topic exactly once; max {max_words} words; no lists; no fluff>

TAGS:
misc/tag1
misc/tag2
...
(10–15 tags total, each starts with "misc/", all lowercase, short, search-friendly)

BULLETS:
{bullets}
"""

TRIM_PROMPT = """Shorten the following summary to <= {max_words} words WITHOUT dropping any distinct topics.
Return ONLY the revised summary paragraph (no labels, no JSON).

Summary:
\"\"\"{summary}\"\"\""""

YAML_HEADER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
YAML_FM_RE = YAML_HEADER_RE  # alias

# --------------------------
# Markdown/YAML helpers
# --------------------------

def has_yaml_frontmatter(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
        return bool(YAML_FM_RE.match(head))
    except Exception:
        return False

def strip_yaml(s: str) -> str:
    return YAML_HEADER_RE.sub("", s, count=1)

def extract_filename_date_title(fname: str):
    # Expect: YYYY-MM-DD - Title - <id>.md  (or without - <id>)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*-\s*(.*?)\s*-(?:.*)\.md$", fname)
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(r"^(\d{4}-\d{2}-\d{2})\s*-\s*(.*)\.md$", fname)
    if m2:
        return m2.group(1), m2.group(2)
    return "", Path(fname).stem

def yaml_escape_scalar(s: str) -> str:
    if s == "" or re.search(r"[:#\-\?\[\]\{\},&\*\!\|\>\<\=\'\"\%\@\`]", s) or s.strip() != s or "\n" in s:
        return '"' + s.replace('"', '\\"') + '"'
    if re.search(r"\s", s):
        return '"' + s.replace('"', '\\"') + '"'
    return s

def yaml_folded_block(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = s.split("\n")
    lines = [l.rstrip() for l in lines]
    return ">\n" + "\n".join(("  " + l if l else "  ") for l in lines)

def build_yaml_frontmatter(title: str, date: str, summary: str, tags):
    out = ["---"]
    out.append(f"title: {yaml_escape_scalar(title)}")
    if date:
        out.append(f"date: {yaml_escape_scalar(date)}")
    out.append("tags:")
    # normalize: ensure misc/... prefix, lowercase, keep 10–15 if possible
    norm, seen = [], set()
    for t in tags:
        t = str(t).strip().lower()
        if not t:
            continue
        if not t.startswith("misc/"):
            t = "misc/" + t.lstrip("#/ ").replace(" ", "-")
        if t not in seen:
            seen.add(t)
            norm.append(t)
        if len(norm) >= 15:
            break
    for t in norm:
        out.append(f"  - {yaml_escape_scalar(t)}")
    out.append("summary: " + yaml_folded_block(summary))
    out.append("---")
    out.append("")  # blank line after YAML
    return "\n".join(out)

def chunk_text(s: str, n_chars: int):
    if len(s) <= n_chars:
        return [s]
    chunks, i, L = [], 0, len(s)
    while i < L:
        j = min(i + n_chars, L)
        k = s.rfind("\n\n", i, j)
        if k == -1 or k < i + int(n_chars * 0.6):
            k = j
        chunk = s[i:k].strip()
        if chunk:
            chunks.append(chunk)
        i = k
    return chunks

def word_count(s: str) -> int:
    return len(re.findall(r"\w+", s))

# --------------------------
# HTTP (stdlib) + retries
# --------------------------

def post_json(path: str, payload: dict, api_key: str, timeout=600) -> dict:
    data = _json.dumps(payload).encode("utf-8")
    req = request.Request(
        API_BASE + path,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return _json.loads(body)

def llm_call(messages: list, api_key: str, retries: int = RETRY_LIMIT) -> str:
    """Chat completion with retries/backoff. Returns raw content string (plain text)."""
    for attempt in range(1, retries + 1):
        try:
            payload = {"model": MODEL, "messages": messages, "temperature": 0.15}
            data = post_json("/chat/completions", payload, api_key, timeout=600)
            return data["choices"][0]["message"]["content"]
        except (error.HTTPError,
                error.URLError,
                http_client.RemoteDisconnected,
                ConnectionResetError,
                TimeoutError,
                socket.timeout) as e:
            if attempt < retries:
                # exponential backoff with jitter
                sleep_s = (RETRY_BACKOFF ** attempt) * (1.0 + 0.25 * random.random())
                time.sleep(sleep_s)
                continue
            raise

# --------------------------
# MAP (plain bullets) & REDUCE (plain text format)
# --------------------------

def map_chunk_plain(chunk: str, api_key: str):
    """Return a list of terse bullets from a plain-text response."""
    content = llm_call(
        [
            {"role": "system", "content": "Return only terse bullet lines, one idea per line. No numbering, no JSON."},
            {"role": "user", "content": MAP_PLAIN_PROMPT.format(chunk=chunk)},
        ],
        api_key,
    ).strip()
    # Split into lines, strip any bullet symbols, keep up to ~20 lines
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    cleaned = []
    for l in lines:
        l = re.sub(r"^[\-\*\d\.\)\(]+", "", l).strip()  # remove leading -,*,1., etc.
        l = l.strip("-• ").strip()
        if l:
            cleaned.append(l)
    if len(cleaned) > 20:
        cleaned = cleaned[:20]
    return cleaned

def reduce_bullets_plain(all_bullets: list[str], max_words: int, api_key: str):
    bullets_text = "\n".join(f"- {b}" for b in all_bullets[:2000])
    user = REDUCE_PLAIN_PROMPT.format(max_words=max_words, bullets=bullets_text)
    raw = llm_call(
        [
            {"role": "system", "content": "Produce exactly the format requested. No extra sections."},
            {"role": "user", "content": user},
        ],
        api_key,
    ).strip()

    if DEBUG:
        print("[DEBUG] Reduce raw (first 400 chars):")
        print(raw[:400])

    # Parse the plain text format:
    summary = ""
    tags = []
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    summary_match = re.search(r"SUMMARY:\s*(.+?)\n\s*\nTAGS:\s*", text, flags=re.DOTALL | re.IGNORECASE)
    if summary_match:
        summary = summary_match.group(1).strip()
        tail = text[summary_match.end():]
    else:
        tag_pos = text.upper().find("TAGS:")
        if tag_pos != -1:
            summary = text[:tag_pos].replace("SUMMARY:", "").strip()
            tail = text[tag_pos + len("TAGS:"):].strip()
        else:
            summary = text.strip()
            tail = ""

    for line in tail.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        m = re.search(r"(misc/[A-Za-z0-9\-\_/]+)", line)
        if m:
            tags.append(m.group(1).lower())

    norm, seen = [], set()
    for t in tags:
        if not t.startswith("misc/"):
            t = "misc/" + t.lstrip("#/ ").replace(" ", "-")
        if t and t not in seen:
            seen.add(t)
            norm.append(t)
        if len(norm) >= 15:
            break

    return summary, norm

# --------------------------
# Work unit (per file)
# --------------------------

def summarize_file(path: Path, api_key: str) -> tuple[Path, str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    body = strip_yaml(raw)
    date, title = extract_filename_date_title(path.name)

    # remove first H1 (optional)
    body_for_summary = re.sub(r"^# .*\n+\s*", "", body, count=1)
    chunks = chunk_text(body_for_summary, CHUNK_CHARS)

    # MAP: plain bullets per chunk (robust)
    all_bullets = []
    for ch in chunks:
        all_bullets.extend(map_chunk_plain(ch, api_key))

    # dynamic cap
    MAX_SUMMARY_WORDS = 150 if len(all_bullets) <= 25 else 250

    # REDUCE: one synthesis call (plain text format)
    summary, tags = reduce_bullets_plain(all_bullets, MAX_SUMMARY_WORDS, api_key)

    # If over cap, trim in a final plain-text pass
    if word_count(summary) > MAX_SUMMARY_WORDS:
        summary = llm_call(
            [
                {"role": "system", "content": "Concise editor."},
                {"role": "user", "content": TRIM_PROMPT.format(max_words=MAX_SUMMARY_WORDS, summary=summary)},
            ],
            api_key,
        ).strip()

    # Write YAML frontmatter
    fm = build_yaml_frontmatter(title, date, summary, tags)
    new_text = fm + body
    path.write_text(new_text, encoding="utf-8")
    return path, f"chunks={len(chunks)} bullets={len(all_bullets)} words={word_count(summary)} tags={len(tags)}"

# --------------------------
# Main (with until-done loop & skip-YAML + exact dashboard.md & notes.md skip)
# --------------------------

def main():
    global DEBUG
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Folder containing .md files (e.g., Final_MD)")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default {MAX_WORKERS})")
    ap.add_argument("--debug", action="store_true", help="Print debug details")
    ap.add_argument("--until-done", action="store_true",
                    help="Keep making passes until all files have YAML or max passes reached")
    ap.add_argument("--max-passes", type=int, default=6, help="Max passes when --until-done is set (default 6)")
    ap.add_argument("--pass-sleep", type=float, default=5.0,
                    help="Seconds to sleep between passes (default 5)")
    ap.add_argument("--no-skip-yaml", action="store_true",
                    help="Process files even if they already have YAML (normally skipped)")
    ap.add_argument("--only", help="Process only files whose name contains this substring")
    args = ap.parse_args()
    DEBUG = args.debug

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: Please set OPENAI_API_KEY environment variable.")
        return

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        return

    print(f"Processing files with model {MODEL} using {args.workers} workers...")

    pass_num = 0
    total_ok, total_fail = 0, 0

    while True:
        pass_num += 1

        # collect targets for this pass
        all_files = sorted(root.rglob("*.md"))
        # skip exact case-sensitive 'dashboard.md' and 'notes.md'
        all_files = [f for f in all_files if f.name not in SKIP_BASENAMES]
        if args.only:
            all_files = [f for f in all_files if args.only in f.name]

        if args.no_skip_yaml:
            targets = all_files
        else:
            targets = [f for f in all_files if not has_yaml_frontmatter(f)]

        if not targets:
            print("No files need processing (all have YAML).")
            break

        print(f"\nPass {pass_num}: {len(targets)} file(s) without YAML")
        ok, fail = 0, 0

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(summarize_file, f, api_key): f for f in targets}
            for fut in as_completed(futs):
                f = futs[fut]
                try:
                    path, meta = fut.result()
                    ok += 1
                    print(f"[OK] {path.name}  ({meta})")
                except Exception as e:
                    fail += 1
                    print(f"[FAIL] {f.name}: {e}")

        total_ok += ok
        total_fail += fail

        if not args.until_done:
            break

        # Re-check if anything remains without YAML
        remaining = [p for p in root.rglob("*.md")
                     if (p.name not in SKIP_BASENAMES)
                     and (args.only in p.name if args.only else True)
                     and (args.no_skip_yaml or not has_yaml_frontmatter(p))]

        if not remaining:
            print("\nAll files now have YAML. Done.")
            break

        if pass_num >= args.max_passes:
            print(f"\nReached max passes ({args.max_passes}). Remaining files still need YAML:")
            for p in remaining[:20]:
                print("  -", p.name)
            if len(remaining) > 20:
                print(f"  ... and {len(remaining)-20} more")
            break

        print(f"\nSleeping {args.pass_sleep:.1f}s before next pass…")
        time.sleep(args.pass_sleep)

    print(f"\nDone. Total Success: {total_ok}, Total Failed: {total_fail}")

if __name__ == "__main__":
    main()