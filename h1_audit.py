import time
from typing import List, Dict, Optional, Tuple

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


def trim_text(text: str, max_len: int = 70) -> str:
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def is_meaningful_heading(text: str) -> bool:
    text = clean_text(text)
    if not text:
        return False
    if len(text) < 3:
        return False

    bad_values = {
        "menu",
        "navigation",
        "read more",
        "learn more",
        "click here",
        "submit",
        "home",
    }
    return text.lower() not in bad_values


def find_best_promotable_heading(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    Returns:
        (heading_tag, heading_text)
        ex: ("h2", "Rhinoplasty in Fort Wayne")
    """
    for level in ["h2", "h3", "h4", "h5", "h6"]:
        tags = soup.find_all(level)
        for tag in tags:
            text = clean_text(tag.get_text(" ", strip=True))
            if is_meaningful_heading(text):
                return level.upper(), text
    return "", ""


def build_recommended_h1(
    page_title: str,
    h1_texts: List[str],
    note: str,
    promoted_heading_text: str = "",
) -> str:
    if note == "Missing H1":
        if promoted_heading_text:
            return trim_text(promoted_heading_text, 70)
        return trim_text(page_title, 70)

    if note == "Multiple H1s" and h1_texts:
        return trim_text(h1_texts[0], 70)

    if len(h1_texts) == 1:
        return trim_text(h1_texts[0], 70)

    return ""


def build_priority_and_action(note: str, status: str, promoted_heading_tag: str = "", promoted_heading_text: str = "") -> Dict:
    status = (status or "").upper()

    if status in {"INVALID", "TIMEOUT", "REDIRECT_ERROR", "FETCH_FAILED", "NON_HTML"}:
        return {
            "priority": "High",
            "action_needed": "Fix fetch/access issue before reviewing H1.",
        }

    if note == "Missing H1":
        if promoted_heading_text and promoted_heading_tag:
            return {
                "priority": "High",
                "action_needed": f'Promote existing {promoted_heading_tag} "{promoted_heading_text}" to H1.',
            }
        return {
            "priority": "High",
            "action_needed": "Add one primary H1 to the page.",
        }

    if note == "Multiple H1s":
        return {
            "priority": "Medium",
            "action_needed": "Keep the main H1 and change extra H1 tags to H2.",
        }

    return {
        "priority": "Low",
        "action_needed": "No action needed.",
    }


def build_change_templates(h1_texts: List[str], promoted_heading_tag: str = "", promoted_heading_text: str = "") -> Dict:
    h1_count = len(h1_texts)

    if h1_count == 0:
        change_templates = ""
        heading_texts = ""

        if promoted_heading_text and promoted_heading_tag:
            heading_texts = promoted_heading_text
            change_templates = f'Promote {promoted_heading_tag} heading "{promoted_heading_text}" to "H1".'

        return {
            "original_tags": promoted_heading_tag if promoted_heading_tag else "",
            "new_tags": "H1" if promoted_heading_tag else "",
            "heading_texts": heading_texts,
            "change_templates": change_templates,
            "note": "Missing H1",
        }

    if h1_count == 1:
        return {
            "original_tags": "H1",
            "new_tags": "H1",
            "heading_texts": h1_texts[0],
            "change_templates": "",
            "note": "OK",
        }

    original_tags = []
    new_tags = []
    change_lines = []

    for idx, text in enumerate(h1_texts):
        original_tags.append("H1")
        if idx == 0:
            new_tags.append("H1")
        else:
            new_tags.append("H2")
            change_lines.append(f'Changed H1 heading from "{text}" to "H2".')

    return {
        "original_tags": "\n".join(original_tags),
        "new_tags": "\n".join(new_tags),
        "heading_texts": "\n".join(h1_texts),
        "change_templates": "\n".join(change_lines),
        "note": "Multiple H1s",
    }


def extract_h1_data(html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    page_title = title_tag.get_text(" ", strip=True) if title_tag else ""
    page_title = clean_text(page_title)

    h1_tags = soup.find_all("h1")
    h1_texts: List[str] = []

    for tag in h1_tags:
        text = tag.get_text(" ", strip=True)
        if text:
            h1_texts.append(clean_text(text))

    promoted_heading_tag = ""
    promoted_heading_text = ""

    if not h1_texts:
        promoted_heading_tag, promoted_heading_text = find_best_promotable_heading(soup)

    h1_count = len(h1_texts)
    change_data = build_change_templates(
        h1_texts,
        promoted_heading_tag=promoted_heading_tag,
        promoted_heading_text=promoted_heading_text,
    )
    recommended_h1 = build_recommended_h1(
        page_title,
        h1_texts,
        change_data["note"],
        promoted_heading_text=promoted_heading_text,
    )
    pa = build_priority_and_action(
        change_data["note"],
        "OK",
        promoted_heading_tag=promoted_heading_tag,
        promoted_heading_text=promoted_heading_text,
    )

    return {
        "title": page_title,
        "h1_count": h1_count,
        "h1_texts": h1_texts,
        "original_tags": change_data["original_tags"],
        "new_tags": change_data["new_tags"],
        "heading_texts": change_data["heading_texts"],
        "change_templates": change_data["change_templates"],
        "note": change_data["note"],
        "recommended_h1": recommended_h1,
        "priority": pa["priority"],
        "action_needed": pa["action_needed"],
        "promoted_heading_tag": promoted_heading_tag,
        "promoted_heading_text": promoted_heading_text,
    }


def audit_single_url(url: str, timeout: int = 15, session: Optional[requests.Session] = None) -> Dict:
    normalized = normalize_url(url)

    if not normalized:
        pa = build_priority_and_action("", "INVALID")
        return {
            "url": url,
            "status": "INVALID",
            "status_code": "",
            "title": "",
            "h1_count": "",
            "h1_texts": [],
            "original_tags": "",
            "new_tags": "",
            "heading_texts": "",
            "change_templates": "",
            "note": "Invalid URL",
            "recommended_h1": "",
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
            pa = build_priority_and_action("", "NON_HTML")
            return {
                "url": final_url,
                "status": "NON_HTML",
                "status_code": status_code,
                "title": "",
                "h1_count": "",
                "h1_texts": [],
                "original_tags": "",
                "new_tags": "",
                "heading_texts": "",
                "change_templates": "",
                "note": "URL did not return HTML",
                "recommended_h1": "",
                "priority": pa["priority"],
                "action_needed": pa["action_needed"],
                "error": "",
            }

        parsed = extract_h1_data(response.text)

        return {
            "url": final_url,
            "status": "OK",
            "status_code": status_code,
            "title": parsed["title"],
            "h1_count": parsed["h1_count"],
            "h1_texts": parsed["h1_texts"],
            "original_tags": parsed["original_tags"],
            "new_tags": parsed["new_tags"],
            "heading_texts": parsed["heading_texts"],
            "change_templates": parsed["change_templates"],
            "note": parsed["note"],
            "recommended_h1": parsed["recommended_h1"],
            "priority": parsed["priority"],
            "action_needed": parsed["action_needed"],
            "error": "",
        }

    except requests.exceptions.Timeout:
        pa = build_priority_and_action("", "TIMEOUT")
        return {
            "url": normalized,
            "status": "TIMEOUT",
            "status_code": "",
            "title": "",
            "h1_count": "",
            "h1_texts": [],
            "original_tags": "",
            "new_tags": "",
            "heading_texts": "",
            "change_templates": "",
            "note": "Request timed out",
            "recommended_h1": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": "Timeout",
        }
    except requests.exceptions.TooManyRedirects:
        pa = build_priority_and_action("", "REDIRECT_ERROR")
        return {
            "url": normalized,
            "status": "REDIRECT_ERROR",
            "status_code": "",
            "title": "",
            "h1_count": "",
            "h1_texts": [],
            "original_tags": "",
            "new_tags": "",
            "heading_texts": "",
            "change_templates": "",
            "note": "Too many redirects",
            "recommended_h1": "",
            "priority": pa["priority"],
            "action_needed": pa["action_needed"],
            "error": "Too many redirects",
        }
    except requests.exceptions.RequestException as exc:
        pa = build_priority_and_action("", "FETCH_FAILED")
        return {
            "url": normalized,
            "status": "FETCH_FAILED",
            "status_code": "",
            "title": "",
            "h1_count": "",
            "h1_texts": [],
            "original_tags": "",
            "new_tags": "",
            "heading_texts": "",
            "change_templates": "",
            "note": "Fetch failed",
            "recommended_h1": "",
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
                log_callback("H1 audit cancelled by user.")
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
                        log_callback("H1 audit cancelled during delay.")
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
                "H1 Count",
                "Original Tag(s)",
                "New Tag(s)",
                "Heading Text(s)",
                "Change Templates",
                "Note",
                "Recommended H1",
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
            str(row.get("h1_count", "")),
            str(row.get("original_tags", "")),
            str(row.get("new_tags", "")),
            str(row.get("heading_texts", "")),
            str(row.get("change_templates", "")),
            str(row.get("note", "")),
            str(row.get("recommended_h1", "")),
            str(row.get("priority", "")),
            str(row.get("action_needed", "")),
            str(row.get("error", "")),
        ]
        safe_values = [v.replace("\t", " ").replace("\r", " ").replace("\n", " | ") for v in values]
        lines.append("\t".join(safe_values))

    return "\n".join(lines)