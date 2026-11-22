"""Render the module 9 screenshots of the annotation app (headless Chrome, no server needed).

Pages are rendered with FastAPI's TestClient into a temporary folder, numbered callouts are added
with a few lines of JavaScript, and Chrome takes the screenshot. The PNGs are then converted to
small WebP files in docs/assets/m9/. Needs google-chrome and network access for `uv run --with
pillow`; not part of CI.

Usage:  uv run python scripts/make_module09_screenshots.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from annotate.app import Config, create_app
from evalkit import repo_root
from mediadoctor import lab09

OUT = repo_root() / "docs" / "assets" / "m9"
STATIC = repo_root() / "labs" / "annotate" / "src" / "annotate" / "static"

CALLOUT = """
<style>main{padding-left:38px}.callout{position:absolute;z-index:99;background:#c2185b;color:#fff;font:700 13px/22px system-ui;
border-radius:50%;width:22px;height:22px;text-align:center;box-shadow:0 0 0 2px #fff}</style>
<script>
window.addEventListener("load", function () {
  for (const [sel, n, side, dy] of CALLOUTS) {
    const el = document.querySelector(sel);
    if (!el) { console.log("callout target missing: " + sel); continue; }
    const r = el.getBoundingClientRect();
    const d = document.createElement("div");
    d.className = "callout"; d.textContent = n;
    d.style.left = (side === "r" ? r.right + 6 : side === "t" ? r.left + r.width / 2 - 11 : r.left - 28) + window.scrollX + "px";
    d.style.top = (side === "t" ? r.top - 26 : r.top + dy) + window.scrollY + "px";
    document.body.appendChild(d);
  }
});
</script>
"""


def shoot(
    html: str, callouts: list[tuple[str, int, str, int]], name: str, tmp: Path, size: str
) -> Path:
    html = html.replace('"/static/', '"static/')
    html = html.replace(
        "</body>", f"<script>const CALLOUTS = {json.dumps(callouts)};</script>{CALLOUT}</body>"
    )
    page = tmp / f"{name}.html"
    page.write_text(html, encoding="utf-8")
    png = tmp / f"{name}.png"
    subprocess.run(
        ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={size}", "--virtual-time-budget=3000", f"--screenshot={png}", page.as_uri()],
        check=True, capture_output=True,
    )  # fmt: skip
    return png


def main() -> int:
    lab09.write_store()
    items = lab09.queue(limit=60)
    lab09.write_queue(items)
    board = lab09.runs_dir() / "dashboard.json"
    board.write_text(json.dumps(lab09.dashboard(), indent=2, default=str) + "\n")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        shutil.copytree(STATIC, tmp / "static")
        cfg = Config(
            lab09.runs_dir() / "traces.jsonl",
            lab09.modes_path("v1"),
            tmp / "labels",
            lab09.runs_dir() / "queue.jsonl",
            board,
            {"annotator-a": lab09.annotator_path("a"), "annotator-b": lab09.annotator_path("b")},
            "MediaDoctor trace review",
        )
        c = TestClient(create_app(cfg))
        c.cookies.set("annotator", "arun")
        pos = next(
            i
            for i, it in enumerate(items)
            if lab09.label_of(it.request_id).modes
            == ["unknown-device-guess", "fabricated-evidence"]
            and "ffprobe" in json.dumps(lab09.store()[it.request_id])
        )
        c.post(
            f"/label/{(pos + 1) % len(items)}", data={"verdict": "pass"}
        )  # one done, for the counter
        review = c.get(f"/review/{pos}").text
        pngs = [
            shoot(
                review,
                [
                    (".bar span", 1, "l", -2),
                    ("[data-context]", 2, "r", -2),
                    (".legend", 3, "r", -5),
                    (".node.err", 4, "l", 2),
                    (".verdict", 5, "l", 10),
                    (".modes legend", 6, "r", -2),
                    ("#new-mode", 7, "l", 4),
                    (".golden", 8, "l", -2),
                ],
                "review",
                tmp,
                "1180,820",
            ),
            shoot(
                c.get("/agreement?a=annotator-a&b=annotator-b").text,
                [
                    (".card p b:nth-of-type(3)", 1, "r", -3),
                    (".mini tr:nth-child(2) td:nth-child(2) ", 2, "l", -2),
                ],
                "agreement",
                tmp,
                "1000,760",
            ),
            shoot(
                c.get("/dashboard").text,
                [("svg.chart", 1, "l", 4), (".card ul li", 2, "l", -2), ("td.hot", 3, "l", -2)],
                "dashboard",
                tmp,
                "1000,1000",
            ),
        ]
        OUT.mkdir(parents=True, exist_ok=True)
        code = (
            "import sys; from PIL import Image\n"
            "for p in sys.argv[2:]:\n"
            "    im = Image.open(p).convert('RGB')\n"
            "    im.save(f\"{sys.argv[1]}/{p.rsplit('/', 1)[1][:-4]}.webp\", 'WEBP', quality=72, method=6)\n"
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--no-project",
                "--with",
                "pillow",
                "python",
                "-c",
                code,
                str(OUT),
                *map(str, pngs),
            ],
            check=True,
        )
    for p in sorted(OUT.glob("*.webp")):
        print(f"{p.relative_to(repo_root())}: {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
