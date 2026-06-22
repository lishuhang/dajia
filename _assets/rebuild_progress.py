"""从 dajia-repo/_posts/ 已有 md 文件反推 progress.json。
每篇 md 的 front matter 中 blog_id 字段就是 article 的 key（去掉前导 / ）。
"""
import os, re, json

POSTS_DIR = "/home/z/my-project/dajia-repo/_posts"
OUT = "/home/z/my-project/dajia-cache/progress.json"

done = set()
not_archived = set()  # archived: false 的
failed = []

pat_blog_id = re.compile(r'^blog_id:\s*(.+?)\s*$', re.M)
pat_archived = re.compile(r'^archived:\s*(\w+)\s*$', re.M)

for fname in os.listdir(POSTS_DIR):
    if not fname.endswith(".md"):
        continue
    path = os.path.join(POSTS_DIR, fname)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = pat_blog_id.search(text)
    if not m:
        continue
    blog_id = m.group(1).strip().strip('"').strip("'")
    # blog_id 形如 "blog/123456" 或 "original/shizhe/ryf20191127"
    key = "/" + blog_id if not blog_id.startswith("/") else blog_id
    ma = pat_archived.search(text)
    archived = ma.group(1).lower() == "true" if ma else True
    if archived:
        done.add(key)
    else:
        not_archived.add(key)

prog = {
    "done": sorted(done),
    "not_archived": sorted(not_archived),
    "failed": failed,
    "pushed_batches": 0,  # 不重要，重置
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(prog, f, ensure_ascii=False, indent=2)

print(f"done (archived=true):  {len(done)}")
print(f"not_archived:          {len(not_archived)}")
print(f"total processed:       {len(done) + len(not_archived)}")
