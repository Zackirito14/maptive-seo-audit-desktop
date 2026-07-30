import re
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


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


def normalize_url(url: str) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def clean_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def slug_to_title(url: str) -> str:
    try:
        path = urlparse(url).path.strip("/")
        if not path:
            return "Home"
        last = path.split("/")[-1]
        last = re.sub(r"[-_]+", " ", last)
        return last.title().strip()
    except Exception:
        return ""


def trim_to_length(text: str, max_len: int) -> str:
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def validate_title(title: str) -> str:
    length = len(title.strip())
    if length == 0:
        return "Missing Title"
    if length < 30:
        return "Title Too Short"
    if length > 60:
        return "Title Too Long"
    return "OK"


def validate_meta_desc(desc: str) -> str:
    length = len(desc.strip())
    if length == 0:
        return "Missing Meta Description"
    if length < 120:
        return "Meta Too Short"
    if length > 160:
        return "Meta Too Long"
    return "OK"


def recommend_title(title: str, fallback_title: str, url: str) -> str:
    base = clean_text(title) or clean_text(fallback_title) or slug_to_title(url)
    if not base:
        base = "Page Title"
    if len(base) < 30:
        base = f"{base} | Professional Services"
    return trim_to_length(base, 60)


def recommend_meta(title: str, meta_desc: str, url: str) -> str:
    if meta_desc and 120 <= len(clean_text(meta_desc)) <= 160:
        return clean_text(meta_desc)

    base_title = clean_text(title) or slug_to_title(url) or "This page"
    suggestion = f"Learn more about {base_title} and explore key details, services, and helpful information on this page."
    suggestion = clean_text(suggestion)

    if len(suggestion) < 120:
        suggestion += " Contact us to learn more."
    return trim_to_length(suggestion, 160)


def build_priority_and_action(title_status: str, meta_status: str, status: str) -> Dict:
    status = (status or "").upper()

    if status in {"INVALID", "TIMEOUT", "REDIRECT_ERROR", "FETCH_FAILED", "NON_HTML"}:
        return {
            "priority": "High",
            "action_needed": "Fix fetch/access issue before reviewing metadata.",
        }

    if title_status == "Missing Title" or meta_status == "Missing Meta Description":
        return {
            "priority": "High",
            "action_needed": "Add the missing metadata field.",
        }

    if title_status in {"Title Too Short", "Title Too Long"} or meta_status in {"Meta Too Short", "Meta Too Long"}:
        return {
            "priority": "Medium",
            "action_needed": "Revise metadata to fit recommended length.",
        }

    return {
        "priority": "Low",
        "action_needed": "No action needed.",
    }


def extract_meta_data(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""

    h1_tag = soup.find("h1")
    fallback_title = h1_tag.get_text(" ", strip=True) if h1_tag else ""

    meta_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
    meta_desc = meta_tag.get("content", "").strip() if meta_tag else ""

    title = clean_text(title)
    fallback_title = clean_text(fallback_title)
    meta_desc = clean_text(meta_desc)

    title_status = validate_title(title)
    meta_status = validate_meta_desc(meta_desc)
    recommended_title = recommend_title(title, fallback_title, url)
    recommended_meta = recommend_meta(title or fallback_title, meta_desc, url)
    pa = build_priority_and_action(title_status, meta_status, "OK")

    return {
        "title": title,
        "title_length": len(title),
        "title_status": title_status,
        "meta_description": meta_desc,
        "meta_length": len(meta_desc),
        "meta_status": meta_status,
        "recommended_title": recommended_title,
        "recommended_meta_description": recommended_meta,
        "priority": pa["priority"],
        "action_needed": pa["action_needed"],
    }


def audit_single_url(url: str, timeout: int = 15, session: Optional[requests.Session] = None) -> Dict:
    normalized = normalize_url(url)

    if not normalized:
        pa = build_priority_and_action("", "", "INVALID")
        return {
            "url": url,
            "status": "INVALID",
            "status_code": "",
            "title": "",
            "title_length": "",
            "title_status": "",
            "meta_description": "",
            "meta_length": "",
            "meta_status": "",
            "recommended_title": "",
            "recommended_meta_description": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": "Invalid URL",
        }

    session = session or build_session()

    try:
        response = session.get(
            normalized,
            timeout=timeout,
            allow_redirects=True,
        )

        final_url = response.url
        status_code = response.status_code
        content_type = response.headers.get("Content-Type", "")

        if "text/html" not in content_type.lower():
            pa = build_priority_and_action("", "", "NON_HTML")
            return {
                "url": final_url,
                "status": "NON_HTML",
                "status_code": status_code,
                "title": "",
                "title_length": "",
                "title_status": "",
                "meta_description": "",
                "meta_length": "",
                "meta_status": "",
                "recommended_title": "",
                "recommended_meta_description": "",
                "priority": pa["priority"],
                "action_needed": pa["action_needed"],
                "error": "URL did not return HTML",
            }

        parsed = extract_meta_data(response.text, final_url)

        return {
            "url": final_url,
            "status": "OK",
            "status_code": status_code,
            "title": parsed["title"],
            "title_length": parsed["title_length"],
            "title_status": parsed["title_status"],
            "meta_description": parsed["meta_description"],
            "meta_length": parsed["meta_length"],
            "meta_status": parsed["meta_status"],
            "recommended_title": parsed["recommended_title"],
            "recommended_meta_description": parsed["recommended_meta_description"],
            "priority": parsed["priority"],
            "action_needed": parsed["action_needed"],
            "error": "",
        }

    except requests.exceptions.Timeout:
        pa = build_priority_and_action("", "", "TIMEOUT")
        return {
            "url": normalized,
            "status": "TIMEOUT",
            "status_code": "",
            "title": "",
            "title_length": "",
            "title_status": "",
            "meta_description": "",
            "meta_length": "",
            "meta_status": "",
            "recommended_title": "",
            "recommended_meta_description": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": "Timeout",
        }
    except requests.exceptions.TooManyRedirects:
        pa = build_priority_and_action("", "", "REDIRECT_ERROR")
        return {
            "url": normalized,
            "status": "REDIRECT_ERROR",
            "status_code": "",
            "title": "",
            "title_length": "",
            "title_status": "",
            "meta_description": "",
            "meta_length": "",
            "meta_status": "",
            "recommended_title": "",
            "recommended_meta_description": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": "Too many redirects",
        }
    except requests.exceptions.RequestException as exc:
        pa = build_priority_and_action("", "", "FETCH_FAILED")
        return {
            "url": normalized,
            "status": "FETCH_FAILED",
            "status_code": "",
            "title": "",
            "title_length": "",
            "title_status": "",
            "meta_description": "",
            "meta_length": "",
            "meta_status": "",
            "recommended_title": "",
            "recommended_meta_description": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": str(exc),
        }


def audit_urls(
    urls: List[str],
    timeout: int = 15,
    delay_ms: int = 0,
    progress_callback=None,
    log_callback=None,
    cancel_event=None,
) -> List[Dict]:
    cleaned_urls = []
    seen = set()

    for raw in urls:
        value = (raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned_urls.append(value)

    total = len(cleaned_urls)
    results: List[Dict] = []
    session = build_session()

    for index, url in enumerate(cleaned_urls, start=1):
        if cancel_event and cancel_event.is_set():
            if log_callback:
                log_callback("Meta audit cancelled by user.")
            break

        if log_callback:
            log_callback(f"[{index}/{total}] Auditing {url}")

        result = audit_single_url(url, timeout=timeout, session=session)
        results.append(result)

        if progress_callback:
            progress_callback(index, total, result)

        if delay_ms > 0 and index < total:
            slept = 0
            while slept < delay_ms:
                if cancel_event and cancel_event.is_set():
                    if log_callback:
                        log_callback("Meta audit cancelled during delay.")
                    return results
                chunk = min(100, delay_ms - slept)
                time.sleep(chunk / 1000)
                slept += chunk

    return results


def results_to_tsv(results: List[Dict]) -> str:
    lines = [
        "\t".join(
            [
                "URL",
                "Status",
                "Status Code",
                "Title",
                "Title Length",
                "Title Status",
                "Meta Description",
                "Meta Length",
                "Meta Status",
                "Recommended Title",
                "Recommended Meta Description",
                "Priority",
                "Action Needed",
                "Error",
            ]
        )
    ]

    for row in results:
        values = [
            str(row.get("url", "")),
            str(row.get("status", "")),
            str(row.get("status_code", "")),
            str(row.get("title", "")),
            str(row.get("title_length", "")),
            str(row.get("title_status", "")),
            str(row.get("meta_description", "")),
            str(row.get("meta_length", "")),
            str(row.get("meta_status", "")),
            str(row.get("recommended_title", "")),
            str(row.get("recommended_meta_description", "")),
            str(row.get("priority", "")),
            str(row.get("action_needed", "")),
            str(row.get("error", "")),
        ]
        safe_values = [v.replace("\t", " ").replace("\r", " ").replace("\n", " ") for v in values]
        lines.append("\t".join(safe_values))

    return "\n".join(lines)