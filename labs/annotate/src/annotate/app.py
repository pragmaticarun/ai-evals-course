"""The review app: FastAPI on the server, HTMX and a few lines of JavaScript in the browser.

    GET  /                       queue, progress, and who is annotating
    POST /annotator              set the annotator name (a cookie)
    GET  /review/{pos}           one trace, full page;  GET /panel/{pos} is the same as an HTMX fragment
    POST /label/{pos}            save pass/fail, note, modes, golden flag; returns the next trace
    GET  /export/labels.csv      this annotator's labels (evalkit annotation CSV)
    GET  /export/taxonomy.csv    failure modes ranked by count x severity (evalkit taxonomy CSV)
    GET  /export/golden.jsonl    golden-dataset candidates: failing or flagged traces
    GET  /export/golden-flags.json
    GET  /agreement              Cohen's kappa between two annotators, and where they differ
    GET  /dashboard              the monitoring summary, if one was given

Every form works without JavaScript too (plain POST and a redirect); with HTMX the next trace is
swapped in without a page load, and the keyboard drives everything. The app binds to 127.0.0.1,
keeps no secrets, and writes only into its output directory.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from annotate import render
from annotate.store import Workspace, valid_name
from evalkit.annotate import (
    TAXONOMY_HEADER,
    Annotation,
    kappa_report,
    rank_modes,
)

HERE = Path(__file__).parent
COOKIE = "annotator"


@dataclass
class Config:
    traces: Path
    modes: Path
    out_dir: Path
    queue: Path | None = None
    dashboard: Path | None = None
    compare: dict[str, Path] = field(default_factory=dict)  # read-only label files by name
    title: str = "Trace review"


def create_app(cfg: Config) -> FastAPI:
    ws = Workspace(cfg.traces, cfg.queue, cfg.modes, cfg.out_dir, cfg.compare)
    app = FastAPI(title=cfg.title, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    app.state.ws = ws

    def who(request: Request) -> str:
        name = request.cookies.get(COOKIE, "")
        return name if valid_name(name) and name not in ws.extra_labels else ""

    def page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        base = {
            "title": cfg.title,
            "annotator": who(request),
            "has_dashboard": cfg.dashboard is not None,
        }
        return templates.TemplateResponse(request, name, {**base, **ctx})

    def item_ctx(
        request: Request, pos: int, error: str = "", form: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not 0 <= pos < len(ws.queue):
            raise HTTPException(404, "no such queue position")
        it = ws.queue[pos]
        trace = ws.traces[it.trace_id]
        name = who(request)
        labels = ws.labels(name) if name else {}
        ann = labels.get(it.case_id)
        modes = ws.modes()
        if form is None:
            form = {
                "verdict": ann.verdict if ann else "",
                "note": ann.note if ann else "",
                "modes": set(ann.modes) if ann else set(),
                "golden": it.case_id in (ws.flags(name) if name else set()),
            }
        return {
            "pos": pos,
            "total": len(ws.queue),
            "done": len(labels),
            "item": it,
            "head": render.header(trace),
            "nodes": render.tree(trace),
            "answer": render.answer_parts(trace),
            "modes": list(modes.values()),
            "form": form,
            "error": error,
            "labelled": ann is not None,
        }

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        name = who(request)
        labels = ws.labels(name) if name else {}
        rows = [(i, it, labels.get(it.case_id)) for i, it in enumerate(ws.queue)]
        nxt = ws.next_unlabelled(name) if name else None
        return page(
            request, "index.html", rows=rows, done=len(labels), next=nxt, annotators=ws.annotators()
        )

    @app.post("/annotator")
    def set_annotator(name: str = Form(...)) -> Response:
        name = name.strip().lower()
        if not valid_name(name) or name in ws.extra_labels:
            raise HTTPException(400, "use 1-32 lowercase letters, digits, - or _")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, name, httponly=True, samesite="strict")
        return resp

    @app.get("/review/{pos}", response_class=HTMLResponse)
    def review(request: Request, pos: int) -> Response:
        if not who(request):
            return RedirectResponse("/", status_code=303)
        return page(request, "review.html", **item_ctx(request, pos))

    @app.get("/panel/{pos}", response_class=HTMLResponse)
    def panel(request: Request, pos: int) -> Response:
        if not who(request):
            return Response(status_code=401)
        resp = page(request, "_panel.html", **item_ctx(request, pos))
        resp.headers["HX-Push-Url"] = f"/review/{pos}"
        return resp

    @app.post("/label/{pos}", response_class=HTMLResponse)
    async def label(request: Request, pos: int) -> Response:
        name = who(request)
        if not name:
            return RedirectResponse("/", status_code=303)
        if not 0 <= pos < len(ws.queue):
            raise HTTPException(404, "no such queue position")
        data = await request.form()
        verdict = str(data.get("verdict", ""))
        note = str(data.get("note", "")).strip()
        modes = [str(m) for m in data.getlist("modes")]
        new_mode = str(data.get("new_mode", "")).strip().lower()
        golden = data.get("golden") in ("1", "on", "true")
        form = {
            "verdict": verdict,
            "note": note,
            "modes": set(modes),
            "golden": golden,
            "new_mode": new_mode,
        }
        error = ""
        if verdict not in ("pass", "fail"):
            error = "Choose pass (p) or fail (f)."
        elif verdict == "fail" and not (note or modes or new_mode):
            error = "A fail needs a note or a failure mode, so the label can be coded later."
        elif new_mode:
            try:
                ws.add_mode(new_mode, note)
                modes.append(new_mode)
            except ValueError as exc:
                error = str(exc)
        unknown = set(modes) - set(ws.modes())
        if not error and unknown:
            error = f"Unknown failure mode: {', '.join(sorted(unknown))}"
        htmx = request.headers.get("HX-Request") == "true"
        if error:
            ctx = item_ctx(request, pos, error, form)
            return page(request, "_panel.html" if htmx else "review.html", **ctx)
        it = ws.queue[pos]
        modes = modes if verdict == "fail" else []
        ws.save(
            name,
            Annotation(it.case_id, verdict, note, "", sorted(set(modes)), trace_id=it.trace_id),
            golden,
        )
        nxt = ws.next_unlabelled(name, pos)
        if nxt is None:
            if htmx:
                return Response(headers={"HX-Redirect": "/"})
            return RedirectResponse("/", status_code=303)
        if htmx:
            resp = page(request, "_panel.html", **item_ctx(request, nxt))
            resp.headers["HX-Push-Url"] = f"/review/{nxt}"
            return resp
        return RedirectResponse(f"/review/{nxt}", status_code=303)

    def annotator_param(request: Request, annotator: str | None) -> str:
        name = annotator or who(request)
        if not name or name not in ws.annotators():
            raise HTTPException(404, "no labels for that annotator yet")
        return name

    @app.get("/export/labels.csv")
    def export_labels(request: Request, annotator: str | None = None) -> Response:
        name = annotator_param(request, annotator)
        path = ws.extra_labels.get(name) or ws.labels_path(name)
        return Response(
            path.read_text(encoding="utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="labels-{name}.csv"'},
        )

    @app.get("/export/taxonomy.csv")
    def export_taxonomy(request: Request, annotator: str | None = None) -> Response:
        name = annotator_param(request, annotator)
        rows = rank_modes(list(ws.labels(name).values()), ws.modes())
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(TAXONOMY_HEADER)
        for r in rows:
            m = r.mode
            w.writerow(
                [r.rank, m.id, m.name, m.definition, " ".join(r.examples), r.count, f"{100 * r.pct:.0f}",
                 m.severity, m.fixability, r.priority, r.first_upstream, m.detector, m.owner]
            )  # fmt: skip
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="taxonomy-{name}.csv"'},
        )

    @app.get("/export/golden.jsonl")
    def export_golden(request: Request, annotator: str | None = None) -> Response:
        name = annotator_param(request, annotator)
        flags = ws.flags(name) if name not in ws.extra_labels else set()
        lines = []
        for a in ws.labels(name).values():
            if not (a.failed or a.case_id in flags):
                continue
            pos = ws.position.get(a.case_id)
            if pos is None:
                continue
            it = ws.queue[pos]
            head = render.header(ws.traces[it.trace_id])
            lines.append(
                json.dumps(
                    {
                        "case_id": a.case_id,
                        "trace_id": it.trace_id,
                        "question": head["question"],
                        "answer": head["attrs"].get("mediadoctor.answer", ""),
                        "verdict": a.verdict,
                        "modes": a.modes,
                        "note": a.note,
                        "flagged": a.case_id in flags,
                        "duplicates": it.duplicates,
                        "annotator": name,
                        "status": "candidate",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return Response(
            "\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson"
        )

    @app.get("/export/golden-flags.json")
    def export_flags(request: Request, annotator: str | None = None) -> Response:
        name = annotator_param(request, annotator)
        return Response(json.dumps(sorted(ws.flags(name))), media_type="application/json")

    @app.get("/agreement", response_class=HTMLResponse)
    def agreement(request: Request, a: str | None = None, b: str | None = None) -> HTMLResponse:
        names = ws.annotators()
        if not (a and b):
            pairs = [(x, y) for i, x in enumerate(names) for y in names[i + 1 :]]
            overlap = {(x, y): len(set(ws.labels(x)) & set(ws.labels(y))) for x, y in pairs}
            a, b = max(overlap, key=lambda k: overlap[k]) if overlap else (None, None)
        rep = None
        diffs = []
        if a and b and a in names and b in names:
            la, lb = ws.labels(a), ws.labels(b)
            rep = kappa_report(list(la.values()), list(lb.values()), a, b)
            diffs = [(cid, la[cid], lb[cid], ws.position.get(cid)) for cid in rep.disagreements]
        return page(request, "agreement.html", rep=rep, a=a, b=b, names=names, diffs=diffs)

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        if cfg.dashboard is None or not cfg.dashboard.exists():
            raise HTTPException(404, "start the app with --dashboard FILE")
        data = json.loads(cfg.dashboard.read_text(encoding="utf-8"))
        return page(request, "dashboard.html", d=data, svg=chart_svg(data.get("chart", {})))

    return app


def chart_svg(chart: dict[str, Any], width: int = 560, height: int = 170) -> str:
    """A p-chart as inline SVG: the rate per period, its upper limit, and out-of-limit points."""
    pts = chart.get("points", [])
    if not pts:
        return ""
    top = max(max(p["rate"], p["ucl"]) for p in pts) * 1.15 or 1.0
    pad, w, h = 34, width - 64, height - 40

    def xy(i: int, v: float) -> tuple[float, float]:
        return pad + i * w / max(1, len(pts) - 1), 10 + h - v / top * h

    rate = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, p["rate"]) for i, p in enumerate(pts)))
    ucl = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, p["ucl"]) for i, p in enumerate(pts)))
    dots, labels = [], []
    for i, p in enumerate(pts):
        x, y = xy(i, p["rate"])
        cls = "dot-high" if p["status"] == "high" else "dot"
        dots.append(
            f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{p["label"]}: {100 * p["rate"]:.1f}%</title></circle>'
        )
        labels.append(
            f'<text x="{x:.1f}" y="{height - 6}" text-anchor="middle">{p["label"]}</text>'
        )
    grid = "".join(
        f'<text x="2" y="{xy(0, v)[1] + 4:.1f}">{100 * v:.0f}%</text>'
        f'<line class="grid" x1="{pad}" x2="{pad + w}" y1="{xy(0, v)[1]:.1f}" y2="{xy(0, v)[1]:.1f}"/>'
        for v in (0, top / 2, top / 1.15)
    )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="p-chart">'
        f'{grid}<polyline class="ucl" points="{ucl}"/><polyline class="rate" points="{rate}"/>'
        f"{''.join(dots)}{''.join(labels)}</svg>"
    )


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8009) -> None:
    import uvicorn

    print(f"annotate: http://{host}:{port}/  (labels go to {cfg.out_dir})")
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
