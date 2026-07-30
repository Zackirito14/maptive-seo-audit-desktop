import gzip
import io
import posixpath
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml,text/xml,text/plain,text/html;q=0.9,*/*;q=0.8",
}

ASSET_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".avif", ".tif", ".tiff",
    ".pdf", ".zip", ".rar", ".7z", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".wmv", ".webm",
    ".css", ".js", ".json", ".xml"
}

ASSET_PATH_KEYWORDS = [
    "/wp-content/uploads/",
    "/wp-content/cache/",
    "/slider/cache/",
    "/cdn-cgi/",
]


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    return session


def normalize_url(url: str):
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def get_base_domain(url: str):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return url


def same_host(url1: str, url2: str):
    try:
        return urlparse(url1).netloc.lower() == urlparse(url2).netloc.lower()
    except Exception:
        return False


def xml_local_name(tag: str):
    if "}" in tag:
        return tag.split("}", 1)[1].lower()
    return tag.lower()


def is_probable_sitemap_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    return (
        path.endswith(".xml")
        or path.endswith(".xml.gz")
        or "sitemap" in path
    )


def decode_response_content(response):
    content = response.content
    final_url = response.url.lower()

    is_gzip = (
        response.headers.get("Content-Encoding", "").lower() == "gzip"
        or final_url.endswith(".gz")
        or response.headers.get("Content-Type", "").lower().find("gzip") != -1
    )

    if is_gzip:
        try:
            return gzip.GzipFile(fileobj=io.BytesIO(content)).read().decode("utf-8", errors="replace")
        except Exception:
            pass

    return content.decode("utf-8", errors="replace")


def fetch_text(url: str, timeout: int = 15, session: requests.Session = None):
    session = session or build_session()
    response = session.get(
        url,
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    return decode_response_content(response), response.url, response.headers.get("Content-Type", "")


def fetch_robots_txt(domain_url: str, timeout: int = 15, session: requests.Session = None):
    base = get_base_domain(domain_url)
    robots_url = urljoin(base, "/robots.txt")
    try:
        text, final_url, _ = fetch_text(robots_url, timeout=timeout, session=session)
        return text, final_url
    except Exception:
        return "", robots_url


def extract_sitemaps_from_robots(robots_text: str):
    sitemaps = []
    for line in robots_text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)
    return sitemaps


def discover_sitemap_candidates(domain_url: str, timeout: int = 15, session: requests.Session = None):
    domain_url = normalize_url(domain_url)
    base = get_base_domain(domain_url)

    robots_text, robots_url = fetch_robots_txt(domain_url, timeout=timeout, session=session)
    robots_sitemaps = extract_sitemaps_from_robots(robots_text)

    fallback_candidates = [
        urljoin(base, "/sitemap.xml"),
        urljoin(base, "/sitemap_index.xml"),
        urljoin(base, "/sitemap-index.xml"),
        urljoin(base, "/wp-sitemap.xml"),
    ]

    seen = set()
    candidates = []

    for url in robots_sitemaps + fallback_candidates:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)

    return {
        "robots_url": robots_url,
        "robots_sitemaps": robots_sitemaps,
        "candidates": candidates,
    }


def parse_xml_locs(xml_text: str):
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "unknown", []

    tag_name = xml_local_name(root.tag)

    if tag_name == "sitemapindex":
        locs = []
        for node in root.iter():
            if xml_local_name(node.tag) == "loc" and node.text and node.text.strip():
                locs.append(node.text.strip())
        return "sitemapindex", locs

    if tag_name == "urlset":
        locs = []
        for node in root.iter():
            if xml_local_name(node.tag) == "loc" and node.text and node.text.strip():
                locs.append(node.text.strip())
        return "urlset", locs

    return "unknown", []


def looks_like_asset_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()

    for keyword in ASSET_PATH_KEYWORDS:
        if keyword in path:
            return True

    _, ext = posixpath.splitext(path)
    if ext.lower() in ASSET_EXTENSIONS:
        return True

    return False


def is_page_url(url: str) -> bool:
    return not looks_like_asset_url(url)


def load_sitemaps(
    domain_url: str,
    timeout: int = 15,
    max_depth: int = 10,
    allow_external_urls: bool = False,
    filter_text: str = "",
    log_callback=None,
    cancel_event=None,
    pages_only: bool = True,
):
    domain_url = normalize_url(domain_url)
    if not domain_url:
        raise ValueError("Invalid domain URL")

    session = build_session()
    discovery = discover_sitemap_candidates(domain_url, timeout=timeout, session=session)

    exact_input_mode = is_probable_sitemap_url(domain_url)

    visited_sitemaps = set()
    urlset_sitemaps = []
    all_urls = []
    seen_urls = set()
    errors = []

    skipped_asset_urls = []
    seen_skipped_assets = set()

    filter_text = (filter_text or "").strip().lower()

    def log(message: str):
        if log_callback:
            log_callback(message)

    def matches_filter(url: str):
        if not filter_text:
            return True
        return filter_text in url.lower()

    def maybe_add_skipped_asset(url: str):
        if url not in seen_skipped_assets:
            seen_skipped_assets.add(url)
            skipped_asset_urls.append(url)

    def walk(sitemap_url: str, depth: int):
        if cancel_event and cancel_event.is_set():
            log("Sitemap loading cancelled by user.")
            return

        if depth > max_depth:
            errors.append(f"Max depth exceeded: {sitemap_url}")
            log(f"SKIP max depth: {sitemap_url}")
            return

        sitemap_url = normalize_url(sitemap_url)
        if not sitemap_url:
            return

        if sitemap_url in visited_sitemaps:
            return

        if not allow_external_urls and not same_host(sitemap_url, domain_url):
            log(f"SKIP external sitemap: {sitemap_url}")
            return

        visited_sitemaps.add(sitemap_url)
        log(f"Fetching sitemap: {sitemap_url}")

        try:
            xml_text, final_url, content_type = fetch_text(sitemap_url, timeout=timeout, session=session)
            detected_type, locs = parse_xml_locs(xml_text)

            log(f"Fetched: {final_url} | type={detected_type}")

            if detected_type == "sitemapindex":
                if not locs:
                    log(f"No child sitemaps found in index: {final_url}")

                for child_url in locs:
                    if cancel_event and cancel_event.is_set():
                        log("Sitemap loading cancelled by user.")
                        return
                    child_url = normalize_url(child_url)
                    if not child_url:
                        continue
                    if not matches_filter(child_url):
                        log(f"FILTERED child sitemap: {child_url}")
                        continue
                    walk(child_url, depth + 1)

            elif detected_type == "urlset":
                urlset_sitemaps.append(final_url)

                if not locs:
                    log(f"No URLs found in urlset: {final_url}")

                for page_url in locs:
                    if cancel_event and cancel_event.is_set():
                        log("Sitemap loading cancelled by user.")
                        return

                    page_url = normalize_url(page_url)
                    if not page_url:
                        continue

                    if not allow_external_urls and not same_host(page_url, domain_url):
                        continue

                    if not matches_filter(page_url):
                        continue

                    if pages_only and not is_page_url(page_url):
                        maybe_add_skipped_asset(page_url)
                        continue

                    if page_url not in seen_urls:
                        seen_urls.add(page_url)
                        all_urls.append(page_url)

            else:
                errors.append(f"Unknown XML type: {final_url}")
                log(f"Unknown XML type: {final_url} | content-type={content_type}")

        except Exception as exc:
            errors.append(f"{sitemap_url} -> {exc}")
            log(f"ERROR fetching {sitemap_url}: {exc}")

    if exact_input_mode:
        starting_candidates = [domain_url]
        log(f"Exact sitemap mode detected: {domain_url}")
    else:
        starting_candidates = discovery["candidates"]

    if filter_text:
        filtered = [c for c in starting_candidates if matches_filter(c)]
        if filtered:
            starting_candidates = filtered

    for candidate in starting_candidates:
        if cancel_event and cancel_event.is_set():
            log("Sitemap loading cancelled by user.")
            break
        walk(candidate, 0)

    return {
        "domain_url": domain_url,
        "input_mode": "exact_sitemap" if exact_input_mode else "domain_discovery",
        "robots_url": discovery["robots_url"],
        "robots_sitemaps": discovery["robots_sitemaps"],
        "candidates": discovery["candidates"],
        "visited_sitemaps": list(visited_sitemaps),
        "urlset_sitemaps": urlset_sitemaps,
        "urls": all_urls,
        "errors": errors,
        "cancelled": bool(cancel_event and cancel_event.is_set()),
        "pages_only": pages_only,
        "skipped_asset_count": len(skipped_asset_urls),
        "skipped_asset_urls": skipped_asset_urls,
    }