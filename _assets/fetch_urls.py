"""
通过 web.archive.org CDX API 拉取 dajia.qq.com 的全部文章 URL。

对每篇 original URL（含 /original/* 和 /blog/* 两种）：
- 收集所有捕获记录
- 优先选择最早的 HTTP 200 快照
- 输出 articles.json: [{key, original_url, timestamp, statuscode}, ...]

key 是去掉 host 后的路径部分（用于唯一标识一篇文章），例如：
  /original/shizhe/ryf20191127.html
  /blog/177011002066160

用法:
    python3 fetch_urls.py
"""
import json
import re
import sys
import time
import urllib.parse
from collections import defaultdict

import requests

ARCHIVE_CDX = "https://web.archive.org/cdx/search/cdx"
OUTPUT = "/home/z/my-project/dajia-cache/articles.json"

# 抓取两个 URL 前缀
SOURCES = [
    "dajia.qq.com/original/*",
    "dajia.qq.com/blog/*",
]

# 过滤掉明显不是文章的 URL
NON_ARTICLE_PATTERNS = [
    r"^/original/?$",
    r"^/original/[a-zA-Z0-9_]+/?$",
    r"^/blog/?$",
    r"^/blog$",
    r"\?.*$",                  # 带 query string 的不是文章
    r"^/$",
    r"^/?\?",
]


def normalize_url(u: str) -> str:
    """去掉 :80 端口、统一 host、保留 path+query 的归一化函数。
    返回 (host_lower, path_with_query) 二元组。
    """
    p = urllib.parse.urlsplit(u)
    host = p.hostname or ""
    host = host.lower().replace(":80", "")
    path = p.path or ""
    # 不保留 query，文章 URL 都是 path 形式
    return host, path


def url_key(u: str) -> str:
    """返回去掉 host 后的路径，用于唯一标识一篇文章。"""
    host, path = normalize_url(u)
    return path


def is_article(u: str, statuscode: str) -> bool:
    if statuscode != "200":
        return False
    host, path = normalize_url(u)
    if not path or path == "/":
        return False
    for pat in NON_ARTICLE_PATTERNS:
        if re.match(pat, path):
            return False
    return True


def fetch_cdx(url_prefix: str) -> list:
    """分页抓取 CDX，返回 list of (timestamp, original, statuscode)。"""
    rows = []
    offset = 0
    page_size = 5000
    while True:
        params = {
            "url": url_prefix,
            "output": "json",
            "fl": "timestamp,original,statuscode",
            "limit": str(page_size),
            "offset": str(offset),
            "filter": "statuscode:200",  # 只取 200，减少数据量
        }
        for attempt in range(3):
            try:
                r = requests.get(ARCHIVE_CDX, params=params, timeout=60)
                if r.status_code == 200:
                    break
                print(f"  HTTP {r.status_code}, retry {attempt+1}", file=sys.stderr)
            except requests.RequestException as e:
                print(f"  error: {e}, retry {attempt+1}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
        else:
            print(f"  giving up on offset {offset}", file=sys.stderr)
            break

        try:
            data = r.json()
        except json.JSONDecodeError:
            print(f"  bad json at offset {offset}", file=sys.stderr)
            break

        if not data or len(data) <= 1:
            break

        # 第一行是表头
        page_rows = data[1:]
        rows.extend(page_rows)
        print(f"  +{len(page_rows)} (total {len(rows)}) from {url_prefix} @ offset {offset}", file=sys.stderr)

        if len(page_rows) < page_size:
            break
        offset += page_size
        time.sleep(1)  # 礼貌延迟

    return rows


def main():
    # 收集所有原始记录
    all_rows = []
    for src in SOURCES:
        print(f"Fetching {src} ...", file=sys.stderr)
        rows = fetch_cdx(src)
        all_rows.extend(rows)
        print(f"  got {len(rows)} rows", file=sys.stderr)

    print(f"\nTotal raw rows: {len(all_rows)}", file=sys.stderr)

    # 按 key 分组，每组保留最早的 200 快照
    by_key = defaultdict(list)
    for ts, original, statuscode in all_rows:
        if not is_article(original, statuscode):
            continue
        key = url_key(original)
        by_key[key].append((ts, original, statuscode))

    print(f"Unique article keys: {len(by_key)}", file=sys.stderr)

    articles = []
    for key, snaps in by_key.items():
        # 按 timestamp 升序，取最早的
        snaps.sort(key=lambda x: x[0])
        ts, original, statuscode = snaps[0]
        articles.append({
            "key": key,
            "original_url": original,
            "timestamp": ts,
            "statuscode": statuscode,
            "snapshots": len(snaps),
        })

    # 按 timestamp 升序排序（旧→新）
    articles.sort(key=lambda x: x["timestamp"])

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(articles)} articles to {OUTPUT}", file=sys.stderr)
    print(f"\nFirst 5:", file=sys.stderr)
    for a in articles[:5]:
        print(f"  {a['timestamp']}  {a['key']}", file=sys.stderr)
    print(f"\nLast 5:", file=sys.stderr)
    for a in articles[-5:]:
        print(f"  {a['timestamp']}  {a['key']}", file=sys.stderr)


if __name__ == "__main__":
    main()
