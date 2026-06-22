# dajia 爬虫脚本与状态备份

本目录是 **爬虫脚本 + 全量 URL 列表 + 进度快照** 的备份。
任何新的 sandbox agent 都可以读这份 README，把脚本拷回 `/home/z/my-project/scripts/`、把数据拷回 `/home/z/my-project/dajia-cache/`，**从断点继续爬取**，不需要重新生成脚本、不需要重新拉 URL 列表、不需要重爬已经完成的文章。

> ⚠️ 如果你修改了脚本逻辑，请同步更新本 README 与 `_assets/` 中的脚本副本，并把改动 push 到 GitHub。

---

## 1. 任务概述

- **数据源**：web.archive.org 收录的 `dajia.qq.com`（腾讯·大家）历史文章
- **目标**：把每篇文章爬取下来，存为 Jekyll 兼容的 markdown，发布到 `lishuhang.me/dajia`
- **GitHub repo**：`lishuhang/dajia`（GitHub Pages 已启用，Jekyll 主题 `jekyll-theme-minimal`）
- **GitHub token**：通过环境变量 `DAJIA_GH_TOKEN` 传入（用户已在原任务中提供，**不要硬编码到脚本里**，否则 GitHub secret scanning 会拒绝 push）
- **每 10 篇推一次 commit**

## 2. 当前进度（截至本 README 更新时）

| 指标 | 数值 |
|------|------|
| 文章 URL 总数 | 13,395 |
| 已完成 (archived=true) | 见 `progress.json` 的 `done` 列表长度 |
| 未被收录 (archived=false) | 见 `progress.json` 的 `not_archived` 列表 |
| 失败 | 见 `progress.json` 的 `failed` 列表 |
| 待爬 | `total - done - not_archived` |

**最新进度请直接读 `_assets/progress.json`**。每次 scraper 运行会更新本地 `dajia-cache/progress.json`，主 agent 应周期性把更新后的 `progress.json` 拷回 `_assets/` 并 push。

## 3. 文件清单

| 文件 | 作用 |
|------|------|
| `scraper.py` | **主爬虫**。从 articles.json + progress.json 出发，处理未完成文章，每 10 篇推一次 GitHub |
| `fetch_urls.py` | 通过 web.archive.org CDX API 拉取 dajia.qq.com 全部 URL（已运行过，结果在 articles.json） |
| `merge_urls.py` | 把 CDX 原始 JSON 合并去重，输出 articles.json（已运行过） |
| `rebuild_progress.py` | 从已生成 `_posts/*.md` 的 front matter 反推 progress.json（用于断点恢复） |
| `articles.json` | 全量 URL 列表，每条 `{key, original_url, timestamp, statuscode, snapshots}` |
| `progress.json` | 进度记录，`{done: [...keys], not_archived: [...], failed: [...], pushed_batches: N}` |

## 4. 文章 URL 格式

dajia.qq.com 历史上用过两种 URL 格式：

```
/blog/{id}              例: /blog/177011002066160          (2012~2014 早期)
/blog/{id}.html         例: /blog/365738076207146.html     (后期)
/original/{category}/{code}{date}.html
                        例: /original/shizhe/ryf20191127.html
                        例: /original/category/snkc20191127.html
                        例: /original/recommend/wz20191126.html
```

`articles.json` 中每篇文章用 `key` 字段唯一标识（即 URL path 部分，以 `/` 开头），如 `/blog/177011002066160` 或 `/original/shizhe/ryf20191127.html`。

## 5. 输出 md 格式

文件名：`YYYY-MM-DD-作者-标题.md`（Jekyll 标准格式，前一个 agent 已采用；用户原文要求 `YYYYMMDD-...` 但 Jekyll 要求 YYYY-MM-DD 才能正确解析 date，保持现状）

front matter：
```yaml
---
layout: post
title: "标题"
date: YYYY-MM-DD
author: 作者名
blog_id: blog/123456 或 original/shizhe/ryf20191127.html（去掉前导 / ）
original_url: 完整原始 URL
archived: true 或 false（false 表示 archive.org 没收录，已建立空文档说明）
---
```

正文：图片保留 **源 URL**（去掉 `https://web.archive.org/web/{ts}id_/` 前缀，`//img1.gtimg.com/...` 改写为 `https://img1.gtimg.com/...`）。

文末固定块：
```
---

原文链接：{original_url}
存档快照：https://web.archive.org/web/{ts}id_/{original_url}
```

## 6. 三种 HTML 结构

scraper.py 用通用 parser（`find_title`/`find_author`/`find_date`/`find_content`）自动识别三种格式：

### 6.1 2012 /blog/ 格式
- 标题：`<div class="txt">` 第一个 `<h2>`
- 作者：`<a href="http://dajia.qq.com/user/xxx">作者名</a>`
- 日期：`<div class="date">` 内 "12月13日 23:44"（年份从 archive_ts 取）
- 正文：`<div id="content" class="txt">` 内的 `<p>`

### 6.2 2013+ /blog/ 格式
- 标题：`<div class="article_mod">` → `<div class="title">` → `<h1>`
- 作者：`<h3>作者名 <span class="date">9月9日 22:01</span></h3>`，去掉 date span 剩下的就是作者
- 日期：`<span class="date">` 或 h3 整体文本中的 "9月9日"
- 正文：`<div class="text tj">` 内的 `<p>`

### 6.3 /original/ 格式
- 标题：`<div id="article">` → `<div class="title">` → `<h1>`
- 作者：`<a href="http://dajia.qq.com/author_personal.htm#!/208">冉云飞</a>`
- 日期：`<span class="publishtime">2019-11-27</span>`
- 正文：`<div id="articleContent">` 内的 `<p>` 和 `<div class="tuzhu">`（图注）

## 7. 新 agent 接手步骤（沙箱重启后）

```bash
# === 1. 设置 GitHub token ===
export DAJIA_GH_TOKEN="PASTE_TOKEN_HERE"  # 用户提供

# === 2. clone repo ===
cd /home/z/my-project
git clone https://lishuhang:${DAJIA_GH_TOKEN}@github.com/lishuhang/dajia.git dajia-repo

# === 3. 恢复 cache 目录 ===
mkdir -p /home/z/my-project/scripts /home/z/my-project/dajia-cache/html
cp /home/z/my-project/dajia-repo/_assets/scraper.py          /home/z/my-project/scripts/
cp /home/z/my-project/dajia-repo/_assets/fetch_urls.py       /home/z/my-project/scripts/
cp /home/z/my-project/dajia-repo/_assets/merge_urls.py       /home/z/my-project/scripts/
cp /home/z/my-project/dajia-repo/_assets/rebuild_progress.py /home/z/my-project/scripts/
cp /home/z/my-project/dajia-repo/_assets/articles.json       /home/z/my-project/dajia-cache/
cp /home/z/my-project/dajia-repo/_assets/progress.json       /home/z/my-project/dajia-cache/

# === 4. 检查进度 ===
python3 -c "import json;d=json.load(open('/home/z/my-project/dajia-cache/progress.json'));a=json.load(open('/home/z/my-project/dajia-cache/articles.json'));print(f'total={len(a)} done={len(d[\"done\"])} not_archived={len(d.get(\"not_archived\",[]))} failed={len(d.get(\"failed\",[]))} todo={len(a)-len(d[\"done\"])-len(d.get(\"not_archived\",[]))}')"

# === 5. 用 _posts/ 反推 progress.json（防止 push 后 progress 丢失） ===
python3 /home/z/my-project/scripts/rebuild_progress.py

# === 6. 测试一篇 (--once) ===
cd /home/z/my-project && python3 scripts/scraper.py --once

# === 7. 跑一批 (默认 ~8 分钟) ===
cd /home/z/my-project && timeout 540 python3 scripts/scraper.py

# === 8. 持续跑（多批，每批 540s） ===
# 注意：sandbox 的 bash 后台进程会被杀，必须用前台或循环
for i in $(seq 1 20); do
  echo "=== batch $i ==="
  timeout 540 python3 /home/z/my-project/scripts/scraper.py
  sleep 5
done

# === 9. 周期性把 progress.json 同步回 _assets/ 并 push ===
cp /home/z/my-project/dajia-cache/progress.json /home/z/my-project/dajia-repo/_assets/
cp /home/z/my-project/scripts/scraper.py /home/z/my-project/dajia-repo/_assets/
cd /home/z/my-project/dajia-repo && \
  git add _assets/ && \
  git -c user.name=dajia-bot -c user.email=bot@lishuhang.me commit -m "Update _assets: progress snapshot" && \
  git push https://lishuhang:${DAJIA_GH_TOKEN}@github.com/lishuhang/dajia.git
```

## 8. 关键注意事项（前人踩过的坑）

1. **CDX API 分页**：`offset` 参数对带 filter 的查询不工作，必须用 `page=N` 参数；先调 `showNumPages=true` 拿到总页数。
2. **archive.org 偶尔卡死**：单篇请求最长 45 秒，超过就重试。如果连续失败，scraper 会 sleep 30s 退避。
3. **沙箱后台进程会被杀**：`nohup`、`setsid`、`disown` 都不可靠。必须用 **前台 `timeout` + 循环** 的方式持续跑。
4. **每 10 篇推一次 GitHub**：scraper 内部已实现，避免 push 太频繁触发 GitHub 限流。
5. **图片 URL 必须去掉 archive.org 前缀**：用户明确要求保留源 URL，已实现。
6. **gb2312/gb18030 编码**：早期文章用 gb2312，后期 utf-8。scraper 通过 meta charset 自动检测。
7. **作者提取优先级**：`div.authorImg > a` > `a[href*=/user/]` > `a[href*=author_personal.htm]` > `div.author_mod > a` > `<title>` 中 "作者：标题" 模式（最后这种容易误识别，加了长度<20 限制）。
8. **正文长度 < 50 字时标记 `archived: false`**：表示 archive.org 没有完整收录，仍建立 md 文档说明。

## 9. 文章 URL 拉取方式

如果 `articles.json` 丢失或需要重新拉取：

```bash
# /original/ 共 3 页
for p in 0 1 2; do
  curl -s -o "/tmp/original_p${p}.json" \
    "https://web.archive.org/cdx/search/cdx?url=dajia.qq.com/original/*&output=json&page=${p}&fl=timestamp,original,statuscode&filter=statuscode:200"
done

# /blog/ 共 5 页
for p in 0 1 2 3 4; do
  curl -s -o "/tmp/blog_p${p}.json" \
    "https://web.archive.org/cdx/search/cdx?url=dajia.qq.com/blog/*&output=json&page=${p}&fl=timestamp,original,statuscode&filter=statuscode:200"
done

# 合并去重
mkdir -p /home/z/my-project/dajia-cache/raw
mv /tmp/original_p*.json /tmp/blog_p*.json /home/z/my-project/dajia-cache/raw/
python3 /home/z/my-project/scripts/merge_urls.py
```

## 10. Jekyll 配置

- `_config.yml`：`baseurl: "/dajia"`，`theme: jekyll-theme-minimal`，`paginate: 30`
- `_layouts/default.html`、`_layouts/home.html`、`_layouts/post.html` 已配置
- `index.md`：列出最近 50 篇文章
- GitHub Pages URL: <https://lishuhang.me/dajia/>
