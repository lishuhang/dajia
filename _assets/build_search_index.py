#!/usr/bin/env python3
"""
Generate search-index.json from _posts/*.md.

For each post, extract:
- title (from front matter)
- author (from front matter)
- date (from filename YYYY-MM-DD)
- url (Jekyll permalink: /posts/{title-without-date}/)
- body (markdown content stripped of front matter, stripped of HTML tags,
        truncated to ~5000 chars for index size)

Output: /search-index.json at repo root (committed alongside _posts).

Usage:
    python3 build-search-index.py [posts_dir] [output_path]

Default:
    posts_dir  = /home/z/my-project/dajia-repo/_posts
    output     = /home/z/my-project/dajia-repo/search-index.json
"""
import os
import re
import sys
import json
import html
from pathlib import Path


def strip_markdown(text: str) -> str:
    """Remove markdown syntax to get plain text for search indexing."""
    # Remove image markdown ![alt](url)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    # Remove link markdown [text](url) -> keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # Remove headers markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.M)
    # Remove blockquote markers
    text = re.sub(r'^>\s*', '', text, flags=re.M)
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove horizontal rules
    text = re.sub(r'^---+\s*$', '', text, flags=re.M)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_post(filepath: str) -> dict | None:
    """Parse a Jekyll post markdown file."""
    try:
        with open(filepath, encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  skip {filepath}: {e}", file=sys.stderr)
        return None

    # Split front matter
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.S)
    if not m:
        return None
    front_matter = m.group(1)
    body = m.group(2)

    # Parse front matter (simple YAML)
    title = ''
    author = ''
    archived = True
    for line in front_matter.split('\n'):
        m = re.match(r'^title:\s*"?(.+?)"?\s*$', line)
        if m: title = m.group(1).strip()
        m = re.match(r'^author:\s*(.+?)\s*$', line)
        if m: author = m.group(1).strip().strip('"').strip("'")
        m = re.match(r'^archived:\s*(\w+)\s*$', line)
        if m: archived = m.group(1).lower() == 'true'

    # Date from filename
    fname = os.path.basename(filepath)
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})-', fname)
    if not m:
        return None
    date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # URL: Jekyll permalink /posts/:title/
    # title = filename without date prefix and without .md
    title_slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', fname)
    title_slug = re.sub(r'\.md$', '', title_slug)
    url = f"/posts/{title_slug}/"

    # Strip markdown for body
    plain_body = strip_markdown(body)
    # Truncate to 5000 chars for index size
    if len(plain_body) > 5000:
        plain_body = plain_body[:5000]

    return {
        'title': title,
        'author': author,
        'date': date,
        'url': url,
        'body': plain_body,
        'archived': archived,
    }


def main():
    posts_dir = sys.argv[1] if len(sys.argv) > 1 else '/home/z/my-project/dajia-repo/_posts'
    output = sys.argv[2] if len(sys.argv) > 2 else '/home/z/my-project/dajia-repo/search-index.json'

    posts = []
    for fname in sorted(os.listdir(posts_dir)):
        if not fname.endswith('.md'):
            continue
        fp = os.path.join(posts_dir, fname)
        post = parse_post(fp)
        if post:
            posts.append(post)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, separators=(',', ':'))

    print(f"Wrote {len(posts)} posts to {output}", file=sys.stderr)
    # Stats
    archived_count = sum(1 for p in posts if p['archived'])
    print(f"  archived=true: {archived_count}", file=sys.stderr)
    print(f"  archived=false: {len(posts) - archived_count}", file=sys.stderr)


if __name__ == '__main__':
    main()
