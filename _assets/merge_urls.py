"""合并 CDX 原始数据，按 URL key 去重，每篇保留最早的 200 快照。"""
import json, re, os, urllib.parse
from collections import defaultdict

RAW_DIR = "/home/z/my-project/dajia-cache/raw"
OUT = "/home/z/my-project/dajia-cache/articles.json"

NON_ARTICLE_PATTERNS = [
    r"^/original/?$",
    r"^/original/[a-zA-Z0-9_]+/?$",
    r"^/blog/?$",
    r"^/blog$",
    r"\?.*$",
    r"^/$",
]

def normalize(u: str):
    p = urllib.parse.urlsplit(u)
    host = (p.hostname or "").lower()
    host = host.replace(":80", "")
    return host, (p.path or "")

def is_article(u: str):
    host, path = normalize(u)
    if not path or path == "/":
        return False
    for pat in NON_ARTICLE_PATTERNS:
        if re.match(pat, path):
            return False
    return True

def key(u: str):
    _, path = normalize(u)
    return path

# 收集所有行
all_rows = []
for fname in sorted(os.listdir(RAW_DIR)):
    if not fname.endswith(".json"):
        continue
    with open(os.path.join(RAW_DIR, fname)) as f:
        data = json.load(f)
    if not data or len(data) <= 1:
        continue
    for row in data[1:]:
        ts, original, statuscode = row[0], row[1], row[2]
        if statuscode != "200":
            continue
        if not is_article(original):
            continue
        all_rows.append((ts, original, statuscode))

print(f"total 200 rows: {len(all_rows)}")

# 按 key 分组，每组保留最早
by_key = defaultdict(list)
for ts, original, statuscode in all_rows:
    k = key(original)
    by_key[k].append((ts, original))

articles = []
for k, snaps in by_key.items():
    snaps.sort(key=lambda x: x[0])
    ts, original = snaps[0]
    articles.append({
        "key": k,
        "original_url": original,
        "timestamp": ts,
        "statuscode": "200",
        "snapshots": len(snaps),
    })

# 按时间升序
articles.sort(key=lambda x: x["timestamp"])

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(articles, f, ensure_ascii=False, indent=2)

print(f"unique articles: {len(articles)}")
print(f"\nfirst 5:")
for a in articles[:5]:
    print(f"  {a['timestamp']}  {a['key']}  snaps={a['snapshots']}")
print(f"\nlast 5:")
for a in articles[-5:]:
    print(f"  {a['timestamp']}  {a['key']}  snaps={a['snapshots']}")

# 按 key 类型统计
original_count = sum(1 for a in articles if a["key"].startswith("/original/"))
blog_count = sum(1 for a in articles if a["key"].startswith("/blog/"))
print(f"\n/original/ : {original_count}")
print(f"/blog/     : {blog_count}")
