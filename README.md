# Maptive SEO Audit Desktop

A lightweight desktop application for technical SEO auditing. It processes URL lists and sitemaps, checks H1 tags and metadata, filters results, and exports structured findings for faster website QA.

## Features

- H1 audit for missing, duplicate, or multiple headings
- Meta title and description audit
- Sitemap loading and URL extraction
- Search, sorting, filtering, and copy/export workflows
- Background processing to keep the UI responsive
- Local desktop settings without a server dependency

## Tech stack

Python · CustomTkinter · Requests · BeautifulSoup · lxml · Threading

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Privacy

The repository intentionally excludes local settings, audited client URLs, exports, and cached files. Do not commit client URL lists or audit results without permission.

## Portfolio

https://jorgen-fosgate.jorgengilfosgate.workers.dev
