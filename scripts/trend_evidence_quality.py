"""Prospective, fail-closed checks for trend claims and cited web pages.

The page check proves that the quoted passage and publication timestamp are
present on the cited page when the gate runs. A researcher must still judge
whether that passage supports the economic inference.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
from pathlib import Path
import ipaddress
import json
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BEIJING = timezone(timedelta(hours=8))
START_DATE = "2026-11-10"
GAP_LANGUAGE = re.compile(r"未披露|尚未兑现|待验证|仍需验证|仍待核验|缺少|尚未形成|尚未获得|无法确认|尚待")
PUBLISHED_KEYS = {"article:published_time", "datepublished", "pubdate", "dc.date", "publishdate"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


urlopen = build_opener(_NoRedirect()).open


def _moment(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None and result.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _compact(value):
    return re.sub(r"\s+", "", value if isinstance(value, str) else "").lower()


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.dates = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self._hidden += 1
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in PUBLISHED_KEYS:
                self.dates.append(attrs.get("content"))
        if tag == "time" and attrs.get("datetime"):
            self.dates.append(attrs["datetime"])

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._hidden:
            self._hidden -= 1

    def handle_data(self, data):
        if not self._hidden:
            self.text.append(data)


def _read_page(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith(".local"):
        raise ValueError("unsafe_source_url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("unsafe_source_url")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 TrendEvidenceAudit/1.0"})
    with urlopen(request, timeout=8) as response:
        if response.status != 200:
            raise ValueError("http_status")
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("page_too_large")
    page = _Page()
    page.feed(raw.decode(charset, errors="replace"))
    # JSON-LD publication dates are common on news sites.
    for match in re.finditer(r'"datePublished"\s*:\s*"([^"]+)"', raw.decode(charset, errors="replace")):
        page.dates.append(match.group(1))
    return _compact(" ".join(page.text)), page.dates


def source_review_errors(review, source, claim, day, cache=None):
    """Return explicit errors; never treat URL shape as page verification."""
    if not isinstance(review, dict) or review.get("status") not in {"VERIFIED", "UNVERIFIED", "MISMATCH"}:
        return ["source_review_missing"]
    if review.get("source") != source:
        return ["source_review_url_mismatch"]
    if review["status"] == "MISMATCH":
        return ["source_mismatch"]
    if review["status"] != "VERIFIED":
        return ["source_unverified"]
    cutoff = _moment(day + "T18:30:00+08:00")
    published = _moment(review.get("published_at"))
    available = _moment(review.get("available_at"))
    is_local = isinstance(source, str) and source.startswith(("data/", "research/"))
    if (not available or available > cutoff
            or (not is_local and (not published or published > available))):
        return ["source_after_cutoff_or_date_unverified"]
    excerpt = review.get("excerpt")
    anchor = review.get("claim_anchor")
    if (not isinstance(excerpt, str) or len(excerpt.strip()) < 12
            or not isinstance(anchor, str) or len(anchor.strip()) < 6
            or _compact(anchor) not in _compact(excerpt)
            or _compact(anchor) not in _compact(claim)
            or not isinstance(review.get("relevance_reason"), str)
            or len(review["relevance_reason"].strip()) < 12):
        return ["source_claim_mismatch"]
    if isinstance(source, str) and source.startswith(("data/", "research/")):
        root = Path(__file__).resolve().parents[1]
        path = (root / source).resolve()
        try:
            path.relative_to(root)
            if not path.is_file() or path.stat().st_size > 2_000_000:
                raise ValueError("local source missing or too large")
            raw = path.read_bytes()
            body = raw.decode("utf-8")
            payload = json.loads(body)
            generated = _moment(payload.get("generated_at")) if isinstance(payload, dict) else None
            if generated is not None:
                if not published or generated != published or available < generated:
                    return ["source_publication_time_mismatch"]
            else:
                # Some same-session market snapshots have an as-of trade date
                # but no publication timestamp. Verify their identity via Git
                # blob SHA instead of inventing a published_at timestamp.
                snap_day = payload.get("trade_date") if isinstance(payload, dict) else None
                blob_sha = hashlib.sha1(
                    b"blob " + str(len(raw)).encode("ascii") + b"\\0" + raw
                ).hexdigest()
                if (published is not None or not isinstance(snap_day, str)
                        or not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", snap_day)
                        or snap_day > day or snap_day != review.get("snapshot_trade_date")
                        or blob_sha != review.get("snapshot_blob_sha")
                        or available.astimezone(BEIJING).date().isoformat() < snap_day):
                    return ["source_snapshot_provenance_mismatch"]
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            return ["source_page_unverifiable"]
        return [] if _compact(excerpt) in _compact(body) else ["source_excerpt_not_on_page"]
    if not isinstance(source, str) or not source.startswith(("https://", "http://")):
        return ["source_page_unverifiable"]
    # On a live web page, the page's published timestamp is the earliest
    # verifiable availability timestamp; a manually supplied earlier time
    # cannot make a late article eligible.
    if available != published:
        return ["source_availability_time_unverified"]
    try:
        if cache is not None and source in cache:
            text, dates = cache[source]
        else:
            text, dates = _read_page(source)
            if cache is not None:
                cache[source] = (text, dates)
    except (OSError, ValueError, UnicodeError, LookupError):
        return ["source_page_unverifiable"]
    if _compact(excerpt) not in text:
        return ["source_excerpt_not_on_page"]
    if published not in {date for value in dates if (date := _moment(value)) is not None}:
        return ["source_publication_time_mismatch"]
    return []


def counter_errors(evidence):
    """A missing disclosure or future transmission is a gap, not a COUNTER."""
    if evidence.get("direction") != "COUNTER":
        return []
    fact = evidence.get("adverse_fact")
    if (evidence.get("counter_fact_status") != "VERIFIED_ADVERSE_FACT"
            or not isinstance(fact, str) or len(fact.strip()) < 12
            or GAP_LANGUAGE.search(fact)
            or GAP_LANGUAGE.search(evidence.get("finding")
                                   if isinstance(evidence.get("finding"), str) else "")):
        return ["counter_not_verified_adverse_fact"]
    return []
