#!/usr/bin/env python3
"""
Scan _posts/ to discover all (year, month) combinations.
Generate Jekyll Pages:
  /year/YYYY/index.md          → layout: year_month, year: YYYY
  /year/YYYY/MM/index.md       → layout: year_month, year: YYYY, month: MM

Idempotent: re-running overwrites only changed pages.

Usage:
    python3 generate_year_month_pages.py
"""
import os
import re
from pathlib import Path

POSTS_DIR = Path('/home/z/my-project/dajia-repo/_posts')
YEAR_DIR = Path('/home/z/my-project/dajia-repo/year')


def main():
    ym = set()
    for fname in os.listdir(POSTS_DIR):
        if not fname.endswith('.md'):
            continue
        m = re.match(r'^(\d{4})-(\d{2})-\d{2}-', fname)
        if not m:
            continue
        ym.add((m.group(1), m.group(2)))

    years = sorted({y for y, _ in ym}, reverse=True)
    print(f"Years: {years}")

    for y in years:
        # /year/YYYY/index.md
        ydir = YEAR_DIR / y
        ydir.mkdir(parents=True, exist_ok=True)
        ypage = ydir / 'index.md'
        with open(ypage, 'w', encoding='utf-8') as f:
            f.write(f"""---
layout: year_month
title: "{y}年 · 腾讯·大家存档"
year: "{y}"
---
""")
        print(f"  wrote {ypage.relative_to(Path('/home/z/my-project/dajia-repo'))}")

        # /year/YYYY/MM/index.md for each month
        months = sorted({m for yy, m in ym if yy == y})
        for m in months:
            mdir = ydir / m
            mdir.mkdir(parents=True, exist_ok=True)
            mpage = mdir / 'index.md'
            with open(mpage, 'w', encoding='utf-8') as f:
                f.write(f"""---
layout: year_month
title: "{y}年{int(m)}月 · 腾讯·大家存档"
year: "{y}"
month: "{m}"
---
""")
        print(f"    {len(months)} months: {months}")


if __name__ == '__main__':
    main()
