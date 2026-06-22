#!/usr/bin/env python3
"""
dajia.qq.com 历史文章爬虫 (v2)

数据源: web.archive.org
输出:   _posts/YYYY-MM-DD-作者-标题.md (Jekyll 兼容)
推送:   每 10 篇推送到 GitHub repo lishuhang/dajia

支持三种 HTML 格式（用通用 parser 处理）:
  1. 2012 /blog/: div#content(class=txt), h2(标题), div.date(日期), a[/user/](作者)
  2. 2013+ /blog/: div.article_mod > div.title > h1, h3 > span.date, div.text.tj
  3. /original/: div#article > div.title > h1, span.publishtime, div#articleContent, div.authorImg > a

用法:
    python3 scraper.py              # 处理下一批（约8分钟）
    python3 scraper.py --once       # 仅处理 1 篇（测试用）
    python3 scraper.py --limit N    # 处理 N 篇后退出
    python3 scraper.py --key KEY    # 仅处理指定 key 的文章
"""
import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString

# ============ 路径 ============
BASE = Path("/home/z/my-project")
CACHE = BASE / "dajia-cache"
HTML_DIR = CACHE / "html"
ARTICLES_JSON = CACHE / "articles.json"
PROGRESS_JSON = CACHE / "progress.json"
SCRAPER_LOG = CACHE / "scraper.log"

REPO_DIR = BASE / "dajia-repo"
POSTS_DIR = REPO_DIR / "_posts"

# GitHub
# Token 从环境变量 DAJIA_GH_TOKEN 读取；如果未设置，回退到默认值（仅用于本地测试）
GH_TOKEN = os.environ.get("DAJIA_GH_TOKEN", "")
GH_REPO = "lishuhang/dajia"

# Runtime limit (seconds). Can be overridden via --max-runtime
MAX_RUNTIME = 480

# ============ HTTP ============
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})

# ============ 工具 ============

def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(SCRAPER_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_url(url: str, timeout: int = 30) -> requests.Response | None:
    """带重试的 GET。"""
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=(10, timeout), allow_redirects=True)
            return r
        except requests.RequestException as e:
            log(f"  fetch error attempt {attempt+1}: {e}")
            time.sleep(2 ** attempt)
    return None


def fetch_article_html(article: dict) -> tuple[str, str] | None:
    """返回 (html_text, archive_ts) 或 None。"""
    original = article["original_url"]
    ts = article["timestamp"]
    key_safe = article["key"].strip("/").replace("/", "_")
    html_path = HTML_DIR / f"{ts}_{key_safe}.html"

    if html_path.exists() and html_path.stat().st_size > 1000:
        try:
            with open(html_path, "rb") as f:
                raw = f.read()
            return decode_html(raw), ts
        except Exception:
            pass

    archive_url = f"https://web.archive.org/web/{ts}id_/{original}"
    r = fetch_url(archive_url, timeout=45)
    if r and r.status_code == 200 and len(r.content) > 1000:
        HTML_DIR.mkdir(parents=True, exist_ok=True)
        with open(html_path, "wb") as f:
            f.write(r.content)
        return decode_html(r.content), ts

    log(f"  primary ts failed, finding alternatives...")
    alt_ts = find_alt_timestamps(original)
    for alt in alt_ts:
        if alt == ts:
            continue
        archive_url = f"https://web.archive.org/web/{alt}id_/{original}"
        r = fetch_url(archive_url, timeout=45)
        if r and r.status_code == 200 and len(r.content) > 1000:
            html_path_alt = HTML_DIR / f"{alt}_{key_safe}.html"
            with open(html_path_alt, "wb") as f:
                f.write(r.content)
            return decode_html(r.content), alt
    return None


def find_alt_timestamps(original: str) -> list[str]:
    """查询同一 URL 的所有 200 快照时间戳。"""
    cdx_url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": original,
        "output": "json",
        "fl": "timestamp,statuscode",
        "filter": "statuscode:200",
        "limit": "50",
    }
    try:
        r = SESSION.get(cdx_url, params=params, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        if not data or len(data) <= 1:
            return []
        return [row[0] for row in data[1:]]
    except Exception as e:
        log(f"  cdx error: {e}")
        return []


def decode_html(raw: bytes) -> str:
    """尝试多种编码。"""
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    if m:
        enc = m.group(1).lower()
        try:
            return raw.decode(enc, errors="replace")
        except LookupError:
            pass
    for enc in ["utf-8", "gb18030", "gb2312"]:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ============ Parser (通用) ============

ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\n\r\t]')


def sanitize_filename(s: str) -> str:
    s = ILLEGAL_CHARS.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(".")
    if not s:
        s = "untitled"
    if len(s) > 100:
        s = s[:100]
    return s


def html_node_to_markdown(node) -> str:
    """将 BeautifulSoup 节点转成 markdown 文本。
    用迭代式而非递归式，避免深度嵌套 HTML 导致 RecursionError。
    """
    if node is None:
        return ""

    import sys
    OLD_LIMIT = sys.getrecursionlimit()
    sys.setrecursionlimit(max(OLD_LIMIT, 10000))

    try:
        def process(n) -> str:
            if n is None:
                return ""
            if isinstance(n, str) or isinstance(n, NavigableString):
                return str(n)
            if not hasattr(n, "name") or n.name is None:
                return n.get_text() if hasattr(n, "get_text") else str(n)
            name = n.name

            if name == "img":
                src = n.get("src", "")
                src = re.sub(r"^https?://web\.archive\.org/web/\d+(?:im_|id_)?/", "", src)
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("http://"):
                    src = "https://" + src[len("http://"):]
                alt = n.get("alt", "")
                return f"\n\n![{alt}]({src})\n\n"

            if name in ("p",):
                inner = "".join(process(c) for c in n.children)
                return inner.strip() + "\n\n"

            if name in ("br",):
                return "\n"

            if name in ("strong", "b"):
                inner = "".join(process(c) for c in n.children).strip()
                return f"**{inner}**" if inner else ""

            if name in ("em", "i"):
                inner = "".join(process(c) for c in n.children).strip()
                return f"*{inner}*" if inner else ""

            if name == "a":
                return "".join(process(c) for c in n.children)

            if name in ("h1","h2","h3","h4","h5","h6"):
                inner = "".join(process(c) for c in n.children).strip()
                return f"\n\n## {inner}\n\n" if inner else ""

            if name == "blockquote":
                inner = "".join(process(c) for c in n.children).strip()
                inner = re.sub(r"^", "> ", inner, flags=re.M)
                return f"\n\n{inner}\n\n" if inner else ""

            if name == "div":
                cls = n.get("class", []) or []
                if "tuzhu" in cls:
                    inner = "".join(process(c) for c in n.children).strip()
                    return f"\n\n*{inner}*\n\n" if inner else ""
                return "".join(process(c) for c in n.children)

            if name in ("script", "style", "noscript"):
                return ""

            return "".join(process(c) for c in n.children)

        text = process(node)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    finally:
        sys.setrecursionlimit(OLD_LIMIT)


def find_title(soup) -> tuple[str, str]:
    """返回 (title, subtitle)。subtitle 可能为空。"""
    # 1. div#article > div.title > h1
    art = soup.find(id="article")
    if art:
        td = art.find("div", class_="title")
        if td:
            h1 = td.find("h1")
            if h1:
                t = h1.get_text().strip()
                st = ""
                h2 = td.find("h2")
                if h2:
                    st = h2.get_text().strip()
                return re.sub(r"\s+", " ", t), re.sub(r"\s+", " ", st)

    # 2. div.article_mod > div.title > h1
    am = soup.find("div", class_="article_mod")
    if am:
        td = am.find("div", class_="title")
        if td:
            h1 = td.find("h1")
            if h1:
                t = h1.get_text().strip()
                return re.sub(r"\s+", " ", t), ""

    # 3. 全文找第一个有意义的 h1
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text().strip()
        if t and "腾讯" not in t and "大家" not in t[:5]:
            return re.sub(r"\s+", " ", t), ""

    # 4. 找第一个无 class 的 h2（排除侧边栏的）
    for h2 in soup.find_all("h2"):
        cls = h2.get("class", []) or []
        if cls:
            continue
        t = h2.get_text().strip()
        if not t or len(t) > 200:
            continue
        if t in ("《大家》官方微信", "精华评论", "今日头条") or "官方微信" in t:
            continue
        # 紧跟着的 h3 当副标题
        st = ""
        nxt = h2.find_next_sibling()
        if nxt and getattr(nxt, "name", None) == "h3":
            st = nxt.get_text().strip()
        return re.sub(r"\s+", " ", t), re.sub(r"\s+", " ", st)

    # 5. 用 <title>
    if soup.title:
        t = soup.title.string or ""
        # 去掉 "_ 腾讯 · 大家" 后缀
        m = re.match(r"^\s*([^：]+?)\s*[：:]\s*(.+?)\s*[_－-]\s*腾讯", t)
        if m:
            return re.sub(r"\s+", " ", m.group(2).strip()), ""
        m = re.match(r"^\s*(.+?)\s*[_－-]\s*腾讯", t)
        if m:
            return re.sub(r"\s+", " ", m.group(1).strip()), ""
        return re.sub(r"\s+", " ", t.strip()), ""

    return "untitled", ""


def find_author(soup) -> str:
    """找作者。"""
    # 1. div.authorImg > a
    ai = soup.find("div", class_="authorImg")
    if ai:
        a = ai.find("a")
        if a:
            t = a.get_text().strip()
            if t:
                return t
    # 2. a[href*=user/]  (2012 / 2013 blog)
    for a in soup.find_all("a"):
        href = a.get("href", "") or ""
        if "dajia.qq.com/user/" in href or href.startswith("/user/") or "dajia.qq.com:80/user/" in href:
            t = a.get_text().strip()
            if t and len(t) < 30:
                return t
    # 3. a[href*=author_personal.htm]  (original 格式)
    for a in soup.find_all("a"):
        href = a.get("href", "") or ""
        if "author_personal.htm" in href:
            t = a.get_text().strip()
            if t and t != "更多" and len(t) < 30:
                return t
    # 4. div.author_mod > a
    am = soup.find("div", class_="author_mod")
    if am:
        a = am.find("a")
        if a:
            t = a.get_text().strip()
            if t:
                return t
    # 5. h2 > a[href*=user/]
    for h2 in soup.find_all("h2"):
        a = h2.find("a")
        if a:
            href = a.get("href", "") or ""
            if "/user/" in href:
                t = a.get_text().strip()
                if t and len(t) < 30:
                    return t
    # 6. <title> "作者 ： 标题 ..."
    if soup.title:
        m = re.match(r"^\s*([^：]+?)\s*[：:]\s*(.+)", soup.title.string or "")
        if m:
            t = m.group(1).strip()
            # 排除标题误识别（标题通常较长或含特定关键词）
            if t and len(t) < 20 and "腾讯" not in t and "大家" not in t:
                return t
    return "佚名"


def find_date(soup, archive_ts: str) -> str:
    """找日期，返回 YYYY-MM-DD。"""
    # 1. span.publishtime
    pt = soup.find("span", class_="publishtime")
    if pt:
        d = pt.get_text().strip()
        if d:
            return normalize_date(d, archive_ts)
    # 2. div.date (2012 blog)
    dd = soup.find("div", class_="date")
    if dd:
        t = dd.get_text()
        # "4月17日 15:42" or "12月13日 23:44"
        m = re.search(r"(\d{1,2}月\d{1,2}日)", t)
        if m:
            return normalize_date(m.group(1), archive_ts)
    # 3. h3 > span.date (2013+ blog)
    for h3 in soup.find_all("h3"):
        sp = h3.find("span", class_="date")
        if sp:
            d = sp.get_text().strip()
            if d:
                return normalize_date(d, archive_ts)
        # 也尝试 h3 整体文本 "朱江明 9月9日 22:01"
        t = h3.get_text().strip()
        m = re.search(r"(\d{1,2}月\d{1,2}日)", t)
        if m:
            return normalize_date(m.group(1), archive_ts)
    # 4. div.remark 内
    rm = soup.find("div", class_="remark")
    if rm:
        m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", rm.get_text())
        if m:
            return normalize_date(m.group(1), archive_ts)
    # 5. 回退到 archive_ts 的日期
    return normalize_date(archive_ts[:8], archive_ts)


def find_content(soup) -> str:
    """找正文 div 并转 markdown。"""
    # 优先级 1: div#articleContent
    c = soup.find(id="articleContent")
    if c:
        # 移除 div#articleContent 内的 div.editor / div.isShow 等
        for sel in ["div.editor", "div.isShow", "div.share_bottom", "div.related",
                    "div.pinglun", "div.article_lists", "div.hasc"]:
            for el in c.select(sel):
                el.decompose()
        return html_node_to_markdown(c)
    # 优先级 2: div.article_mod > div.text
    am = soup.find("div", class_="article_mod")
    if am:
        # 移除侧边栏
        for sel in ["div.author_mod", "div.articleIndex_mod", "div.moreArticle",
                    "div.articleBox", "div.shareMenuV2", "div.shareIcon",
                    "div.data", "div.focusComment", "div.publicationComment"]:
            for el in am.select(sel):
                el.decompose()
        t = am.find("div", class_="text")
        if t:
            return html_node_to_markdown(t)
        # 备用：article_mod 内所有 p
        return html_node_to_markdown(am)
    # 优先级 3: div#content
    c = soup.find(id="content")
    if c:
        return html_node_to_markdown(c)
    # 优先级 4: div.txt 第一个
    t = soup.find("div", class_="txt")
    if t:
        return html_node_to_markdown(t)
    return ""


def parse_article(html: str, article: dict, archive_ts: str) -> dict:
    """通用 parser。"""
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["script", "style", "noscript"]):
        s.decompose()

    title, subtitle = find_title(soup)
    author = find_author(soup)
    date = find_date(soup, archive_ts)
    content = find_content(soup)
    content = clean_content(content)

    # 副标题加到标题里
    if subtitle:
        title = f"{title} {subtitle}"

    return {
        "title": title,
        "author": author,
        "date": date,
        "content": content,
        "archived": True,
    }


def normalize_date(s: str, archive_ts: str) -> str:
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{1,2})月(\d{1,2})日", s)
    if m:
        y = archive_ts[:4]
        return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return f"{archive_ts[:4]}-{archive_ts[4:6]}-{archive_ts[6:8]}"


TAIL_PATTERNS = [
    r"【责任编辑[：:].*?】",
    r"责任编辑[：:].*?$",
    r"版权声明.*?追究法律责任。",
    r"本文系腾讯《大家》独家稿件.*?追究法律责任。",
    r"文章内容纯属作者个人观点.*?不代表平台观点。",
    r"关注《大家》微信.*?$",
    r"扫描二维码.*?$",
    r"扫码关注.*?$",
    r"手机二维码扫描.*?$",
]
TAIL_RE = re.compile("|".join(TAIL_PATTERNS), re.S | re.M)


def clean_content(text: str) -> str:
    if not text:
        return ""
    text = TAIL_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ============ 输出 ============

def build_filename(meta: dict, article: dict) -> str:
    date = meta["date"]
    author = sanitize_filename(meta["author"]) or "佚名"
    title = sanitize_filename(meta["title"])
    if not title or title == "untitled":
        title = sanitize_filename(article["key"].split("/")[-1])
    return f"{date}-{author}-{title}.md"


def build_markdown(meta: dict, article: dict, archive_ts: str) -> str:
    blog_id = article["key"].lstrip("/")
    original_url = article["original_url"]
    archived = "true" if meta["archived"] else "false"

    front = [
        "---",
        "layout: post",
        f'title: "{meta["title"].replace(chr(34), "")}"',
        f"date: {meta['date']}",
        f"author: {meta['author']}",
        f"blog_id: {blog_id}",
        f"original_url: {original_url}",
        f"archived: {archived}",
        "---",
    ]
    parts = ["\n".join(front)]
    if meta["content"]:
        parts.append(meta["content"])
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(f"原文链接：{original_url}")
    parts.append(f"存档快照：https://web.archive.org/web/{archive_ts}id_/{original_url}")
    return "\n".join(parts)


# ============ Progress ============

def load_progress() -> dict:
    if PROGRESS_JSON.exists():
        with open(PROGRESS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "not_archived": [], "failed": [], "pushed_batches": 0}


def save_progress(prog: dict):
    with open(PROGRESS_JSON, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


# ============ Git Push ============

def git_push_batch(batch_num: int, files: list[Path]) -> bool:
    if not files:
        return False
    try:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "dajia-bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@lishuhang.me"
        env["GIT_COMMITTER_NAME"] = "dajia-bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@lishuhang.me"
        for f in files:
            subprocess.run(
                ["git", "add", str(f.relative_to(REPO_DIR))],
                cwd=REPO_DIR, env=env, check=False, capture_output=True
            )
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR, env=env)
        if r.returncode == 0:
            log(f"  no changes to commit")
            return True
        msg = f"Add batch {batch_num}: {len(files)} articles"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=REPO_DIR, env=env, check=True, capture_output=True
        )
        if not GH_TOKEN:
            log("  warning: DAJIA_GH_TOKEN env var not set, skipping push")
            return False
        for attempt in range(5):
            r = subprocess.run(
                ["git", "push", f"https://lishuhang:{GH_TOKEN}@github.com/{GH_REPO}.git"],
                cwd=REPO_DIR, env=env, capture_output=True, text=True
            )
            if r.returncode == 0:
                log(f"  pushed batch {batch_num}: {len(files)} articles")
                return True
            log(f"  push attempt {attempt+1} failed: {r.stderr[:200]}")
            # If rejected (non-fast-forward), pull --rebase and retry
            if "rejected" in r.stderr or "non-fast-forward" in r.stderr:
                log(f"  pulling --rebase to resolve conflict...")
                subprocess.run(
                    ["git", "fetch", f"https://lishuhang:{GH_TOKEN}@github.com/{GH_REPO}.git", "main"],
                    cwd=REPO_DIR, env=env, capture_output=True, text=True
                )
                # Stash any uncommitted search-index.json changes (GitHub Actions may update)
                subprocess.run(["git", "stash"], cwd=REPO_DIR, env=env, capture_output=True, text=True)
                r2 = subprocess.run(
                    ["git", "rebase", "FETCH_HEAD"],
                    cwd=REPO_DIR, env=env, capture_output=True, text=True
                )
                if r2.returncode != 0:
                    log(f"  rebase failed: {r2.stderr[:200]}")
                    subprocess.run(["git", "rebase", "--abort"], cwd=REPO_DIR, env=env, capture_output=True)
                    subprocess.run(["git", "stash", "pop"], cwd=REPO_DIR, env=env, capture_output=True)
                    time.sleep(5)
                    continue
                subprocess.run(["git", "stash", "pop"], cwd=REPO_DIR, env=env, capture_output=True, text=True)
            time.sleep(3)
        return False
    except Exception as e:
        log(f"  git push error: {e}")
        return False


# ============ 主流程 ============

def process_one(article: dict, prog: dict) -> tuple[bool, str, "Path | None"]:
    key = article["key"]
    if key in prog["done"] or key in prog.get("not_archived", []):
        return True, "already_done", None

    result = fetch_article_html(article)
    if not result:
        prog.setdefault("failed", []).append(key)
        prog["failed"] = list(set(prog["failed"]))
        save_progress(prog)
        return False, "fetch_failed", None

    html, archive_ts = result
    try:
        meta = parse_article(html, article, archive_ts)
    except Exception as e:
        log(f"  parse error for {key}: {e}")
        prog.setdefault("failed", []).append(key)
        prog["failed"] = list(set(prog["failed"]))
        save_progress(prog)
        return False, f"parse_error: {e}", None

    if not meta["content"] or len(meta["content"]) < 50:
        meta["archived"] = False
        meta["content"] = f"本文未被 web.archive.org 完整收录。\n\n原始 URL: {article['original_url']}"

    fname = build_filename(meta, article)
    fpath = POSTS_DIR / fname
    md = build_markdown(meta, article, archive_ts)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md)

    if meta["archived"]:
        prog["done"].append(key)
    else:
        prog.setdefault("not_archived", []).append(key)
    save_progress(prog)
    return True, "ok", fpath


def main():
    global MAX_RUNTIME
    limit = None
    target_key = None
    shard_n = None  # 1-based shard index
    shard_m = None  # total shards
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--once":
            limit = 1
        elif a == "--limit" and i + 1 < len(args):
            limit = int(args[i+1]); i += 1
        elif a == "--key" and i + 1 < len(args):
            target_key = args[i+1]; i += 1
        elif a == "--shard" and i + 2 < len(args):
            shard_n = int(args[i+1]); shard_m = int(args[i+2]); i += 2
        elif a == "--max-runtime" and i + 1 < len(args):
            MAX_RUNTIME = int(args[i+1]); i += 1
        elif a.isdigit():
            limit = int(a)
        i += 1

    with open(ARTICLES_JSON, encoding="utf-8") as f:
        articles = json.load(f)
    prog = load_progress()

    done_set = set(prog["done"])
    na_set = set(prog.get("not_archived", []))
    failed_set = set(prog.get("failed", []))
    if target_key:
        todo = [a for a in articles if a["key"] == target_key]
    else:
        todo = [a for a in articles if a["key"] not in done_set and a["key"] not in na_set]

    # 分片：每个 shard 处理 todo[i] where i % shard_m == shard_n - 1
    if shard_n and shard_m:
        todo = [a for i, a in enumerate(todo) if i % shard_m == (shard_n - 1)]
        log(f"shard {shard_n}/{shard_m}: {len(todo)} articles assigned")

    log(f"total={len(articles)} done={len(done_set)} not_archived={len(na_set)} failed={len(failed_set)} todo={len(todo)}")

    if not todo:
        log("nothing to do")
        return

    batch_files = []
    batch_num = prog.get("pushed_batches", 0)
    processed_this_run = 0
    start_time = time.time()
    if not MAX_RUNTIME:
        MAX_RUNTIME = 480

    for i, article in enumerate(todo):
        if limit and processed_this_run >= limit:
            break
        if time.time() - start_time > MAX_RUNTIME:
            log(f"reached MAX_RUNTIME ({MAX_RUNTIME}s), stopping")
            break

        key = article["key"]
        log(f"[{i+1}/{len(todo)}] {key}")
        ok, reason, fpath = process_one(article, prog)
        if ok and reason == "ok" and fpath:
            batch_files.append(fpath)
            if len(batch_files) >= 10:
                batch_num += 1
                git_push_batch(batch_num, batch_files)
                prog["pushed_batches"] = batch_num
                save_progress(prog)
                batch_files = []
            time.sleep(1.5)
        elif reason == "fetch_failed":
            log(f"  fetch failed, backing off 30s")
            time.sleep(30)
        else:
            log(f"  skip: {reason}")
            time.sleep(1)

        processed_this_run += 1

    if batch_files:
        batch_num += 1
        git_push_batch(batch_num, batch_files)
        prog["pushed_batches"] = batch_num
        save_progress(prog)

    log(f"run finished: processed {processed_this_run}, done={len(prog['done'])}, failed={len(prog.get('failed', []))}")


if __name__ == "__main__":
    main()
