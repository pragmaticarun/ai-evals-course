"""Check every link in the built site.

    uv run zensical build --clean --strict
    uv run python scripts/check_links.py [--site site] [--external] [--json runs/links.json]

Internal links (relative paths, and absolute links to this site or this repository's files) must resolve to a
file, and their #fragment to an id on the target page. External links (with --external) are fetched once each:
2xx and 3xx are OK; 401, 403, and 429 count as OK-but-unverified, because many publishers refuse automated
requests; anything else, or no answer, is broken. Exit code 1 if anything is broken.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://pragmaticarun.github.io/ai-evals-course/"
BASE_PATH = urlparse(SITE_URL).path  # "/ai-evals-course/"
REPO_PREFIXES = (
    "https://github.com/pragmaticarun/ai-evals-course/edit/main/",
    "https://github.com/pragmaticarun/ai-evals-course/blob/main/",
    "https://github.com/pragmaticarun/ai-evals-course/tree/main/",
)
SOFT_OK = {401, 403, 429}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}
UA = "Mozilla/5.0 (X11; Linux x86_64) ai-evals-course-linkcheck/1.0"


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for key in ("href", "src"):
            v = a.get(key)
            if v and tag in ("a", "img", "script", "link", "source", "iframe"):
                if tag == "link" and a.get("rel") in ("preconnect", "dns-prefetch"):
                    continue
                self.links.append(v)


def parse(path: Path) -> Page:
    p = Page()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return p


def target_file(site: Path, page: Path, href: str) -> Path:
    path = unquote(urlparse(href).path)
    base = "/" + page.relative_to(site).as_posix()
    resolved = urljoin(base, path) if path else base
    f = site / resolved.lstrip("/")
    if resolved.endswith("/") or f.is_dir():
        f = f / "index.html"
    return f


def check_site(site: Path, external: bool) -> dict:
    pages = sorted(site.rglob("*.html"))
    parsed = {p: parse(p) for p in pages}
    internal_bad: list[tuple[str, str, str]] = []
    ext: dict[str, set[str]] = defaultdict(set)
    n_internal = 0
    for page, info in parsed.items():
        src = page.relative_to(site).as_posix()
        for href in info.links:
            if href.startswith(("mailto:", "javascript:", "data:", "tel:")):
                continue
            if href.startswith(SITE_URL):
                href = BASE_PATH + href[len(SITE_URL) :]
            if href.startswith(BASE_PATH):
                href = (
                    "/" + href[len(BASE_PATH) :]
                )  # root-absolute: the site is served under /ai-evals-course/
            if href.startswith(REPO_PREFIXES):
                n_internal += 1
                rel = next(href[len(p) :] for p in REPO_PREFIXES if href.startswith(p))
                if not (ROOT / unquote(urldefrag(rel)[0])).exists():
                    internal_bad.append((src, href, "repository file not found"))
                continue
            if urlparse(href).scheme in ("http", "https") or href.startswith("//"):
                if urlparse(href).hostname in LOCAL_HOSTS:
                    continue  # a local app the reader starts (module 9's review app), not a web page
                ext[urldefrag(href)[0]].add(src)
                continue
            n_internal += 1
            f = target_file(site, page, href)
            if not f.exists():
                internal_bad.append((src, href, "file not found"))
                continue
            frag = urldefrag(href)[1]
            if frag and f.suffix == ".html":
                ids = parsed[f].ids if f in parsed else parse(f).ids
                if unquote(frag) not in ids:
                    internal_bad.append((src, href, f"no id #{frag}"))
    result = {"pages": len(pages), "internal_links": n_internal, "internal_broken": internal_bad,
              "external_urls": len(ext), "external": {}}  # fmt: skip
    if external:
        with ThreadPoolExecutor(max_workers=12) as pool:
            for url, status in zip(ext, pool.map(fetch, ext), strict=True):
                result["external"][url] = {"status": status, "pages": sorted(ext[url])}
    return result


def fetch(url: str) -> int | str:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            url, method=method, headers={"User-Agent": UA, "Accept": "*/*"}
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 404, 405, 429, 500, 501, 503):
                continue  # some servers reject HEAD; try GET before judging
            return e.code
        except Exception as e:  # noqa: BLE001 (DNS, TLS, timeout: all mean "could not verify")
            if method == "HEAD":
                continue
            return type(e).__name__
    return "no answer"


def verdict(status: int | str) -> str:
    if isinstance(status, int) and status < 400:
        return "ok"
    if status in SOFT_OK:
        return "ok (refused automated check)"
    return "broken"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default=str(ROOT / "site"))
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    site = Path(a.site)
    if not (site / "index.html").exists():
        print(f"{site} has no index.html: build the site first", file=sys.stderr)
        return 2
    res = check_site(site, a.external)
    print(
        f"{res['pages']} pages, {res['internal_links']} internal links, {res['external_urls']} external URLs"
    )
    for src, href, why in res["internal_broken"]:
        print(f"  BROKEN internal  {src}: {href} ({why})")
    bad_ext = 0
    if a.external:
        counts: dict[str, int] = defaultdict(int)
        for url, r in sorted(res["external"].items()):
            v = verdict(r["status"])
            counts[v] += 1
            if v != "ok":
                print(f"  {v:28} {r['status']}  {url}  (on {', '.join(r['pages'][:2])})")
            bad_ext += v == "broken"
        print("external: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))
    print(f"internal broken: {len(res['internal_broken'])}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=1, default=list))
    return 1 if res["internal_broken"] or bad_ext else 0


if __name__ == "__main__":
    sys.exit(main())
