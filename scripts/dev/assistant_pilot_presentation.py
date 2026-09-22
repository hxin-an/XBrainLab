"""Offline, escaped presentation of Pilot scores and hash-verified case evidence.

This module renders the existing report; it does not score or amend measurements.

Reading order: shared HTML fragments, bounded evidence readers, case pages, then
the report writer. Evidence readers verify stored bytes; presentation functions
only display those observations. Browser styling and filtering live in assets.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

_LIMIT = 32 * 1024**2
# Load fixed presentation assets once. The audit hashes these exact loaded bytes,
# while HTML embeds their text so copied reports do not need an asset directory.
_ASSET_DIRECTORY = Path(__file__).with_name("assistant_report_assets")
_ASSET_BYTES = {
    name: (_ASSET_DIRECTORY / name).read_bytes() for name in ("report.css", "cases.js")
}
_STYLE = _ASSET_BYTES["report.css"].decode("utf-8")
_CASE_SCRIPT = _ASSET_BYTES["cases.js"].decode("utf-8")


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _pre(value: object) -> str:
    return (
        "<pre>" + _escape(value if isinstance(value, str) else _json(value)) + "</pre>"
    )


def render_page(title: str, content: str) -> str:
    """Self-contained HTML shared by the run entry, report and case pages."""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_escape(title)}</title><style>{_STYLE}</style>"
        f'</head><body><main id="main">{content}</main></body></html>'
    )


def experiment_title(directory: Path, *, dev: bool) -> str:
    """Identify the experiment folder, not a report rebuild timestamp."""
    stage = "DEV initial baseline" if dev else "DEV Pilot"
    return f"{directory.name.upper()} | {stage}"


def experiment_conditions(report: dict, *, dev: bool) -> str:
    count = len(report.get("conditions", {}))
    unit = "model" if dev else "model condition"
    models = f"{count} {unit}{'' if count == 1 else 's'} · " if count else ""
    questions = len({row["case_id"] for row in report.get("cases", [])})
    population = (
        f"{questions} question{'' if questions == 1 else 's'} · " if questions else ""
    )
    return models + population + ("RAG on" if dev else "RAG conditions shown below")


def render_evidence_notice(issues: dict) -> str:
    """Only unresolved evidence issues belong in the reading-level warning."""
    selected = sum(not key.startswith("superseded:") for key in issues)
    if not selected:
        return ""
    noun = "result has" if selected == 1 else "results have"
    return f'<p class="notice">{selected} selected {noun} incomplete evidence.</p>'


def _html_table(headers: list[str], rows: list[list]) -> str:
    """Escape all table content at the rendering boundary."""
    headings = "".join(f'<th scope="col">{_escape(label)}</th>' for label in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return (
        '<div class="table"><table><thead><tr>'
        + headings
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def render_overview(report: dict) -> str:
    """Compact view of existing aggregates; never compute or substitute scores."""
    conditions = report.get("conditions", {})
    rows = []
    for name, condition in conditions.items():
        timing = condition["decision_latency_seconds"].get("overall", {})
        rows.append(
            [
                name,
                f"{condition['counts']['valid_decision']} / {condition['counts']['planned']}",
                *[
                    "n/a"
                    if condition["macro"][phase] is None
                    else f"{condition['macro'][phase]:.1%}"
                    for phase in ("first", "final")
                ],
                _number(timing.get("p50")),
                _number(timing.get("max")),
            ]
        )
    table = _html_table(
        [
            "Condition",
            "Valid / planned",
            "First-answer accuracy",
            "Accuracy after format repair",
            "Median decision (s)",
            "Slowest decision (s)",
        ],
        rows,
    )
    return f"""<section id="overview">
        <div class="section-heading"><h2>Model results</h2>
        <a href="results.csv" download>Download CSV</a></div>
        {table}
        <p class="muted table-note">Both accuracy columns weight the three categories equally.
        The second includes format repair when used, otherwise the first answer.
        Decision time includes parsing, validation and any repair, but excludes model loading.
        DEV results, not a formal model ranking.</p>
    </section>"""


def _bytes(root: Path, path: Path, digest: str | None = None) -> bytes:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Evidence path escapes run directory")
    with resolved.open("rb") as source:
        content = source.read(_LIMIT + 1)
    if len(content) > _LIMIT:
        raise ValueError("Evidence exceeds bounded reader size")
    if digest is not None and hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Evidence hash mismatch")
    return content


def _link(path: Path, page: Path, label: str) -> str:
    try:
        href = quote(Path(os.path.relpath(path, page.parent)).as_posix(), safe="/")
    except ValueError:  # Windows cannot express a relative path across drives.
        href = path.resolve().as_uri()
    return f'<a href="{_escape(href)}">{_escape(label)}</a>'


def _capture(root: Path, row: dict, result: dict, capture: dict) -> dict:
    """Ignore recorded absolute paths; derive location from bounded identities."""
    metadata = capture["metadata"]
    session, sequence = metadata["session_id"], metadata["sequence"]
    if (
        not isinstance(session, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session)
        or type(sequence) is not int
        or sequence < 0
    ):
        raise ValueError("Invalid capture session or sequence")
    runtime = result.get("condition_evidence", {})
    condition_artifact = (
        runtime.get("artifact_id", row["condition"])
        if isinstance(runtime, dict)
        else row["condition"]
    )
    if not re.fullmatch(
        re.escape(row["condition"]) + r"(?:__attempt-[1-9][0-9]*)?", condition_artifact
    ):
        raise ValueError("Invalid condition artifact identity")
    base = (
        root / "conditions" / condition_artifact
        if isinstance(result.get("condition_evidence"), dict)
        else root / "cases" / row.get("artifact_id", row["id"])
    )
    path = base / "prompts" / session / str(sequence)
    stored = json.loads(_bytes(root, path / "metadata.json"))
    if stored != metadata or metadata.get("status") not in {
        "completed",
        "cancelled",
        "failed",
    }:
        raise ValueError("Capture metadata mismatch")
    values = {"path": path, "status": metadata["status"]}
    for name, key in (("prompt", "prompt_sha256"), ("raw-output", "raw_output_sha256")):
        digest = metadata[key]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Missing capture digest")
        values[name] = _bytes(root, path / f"{name}.txt", digest).decode("utf-8")
    return values


def _details(root: Path, row: dict, *, require_generation: bool = False) -> dict:
    detail = {"request": {}, "result": {}, "captures": [], "issues": []}
    if row["evidence_status"] != "verified":
        detail["issues"] = [
            "Request/result evidence unavailable: " + row["evidence_status"]
        ]
        return detail
    try:
        artifact = row.get("artifact_id", row["id"])
        detail["request"] = json.loads(
            _bytes(
                root,
                root / "cases" / f"{artifact}.request.json",
                row["request_sha256"],
            )
        )
        detail["result"] = result = json.loads(
            _bytes(
                root, root / "cases" / artifact / "result.json", row["result_sha256"]
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"request": {}, "result": {}, "captures": [], "issues": [str(exc)]}
    generations = result.get("trace", {}).get("generations", [])
    if (
        require_generation
        and not generations
        and not (
            result.get("scores", {}).get("execution_status") == "decision_timeout"
            and result.get("input_audit", {}).get("sent_to_model") is False
        )
    ):
        detail["issues"].append(
            "Decision has no generation evidence or verified pre-dispatch timeout"
        )
    captures = result.get("capture_audit", {}).get("captures", [])
    warmups = 0 if isinstance(result.get("condition_evidence"), dict) else 1
    if len(captures) != len(generations) + warmups:
        detail["issues"].append("Capture/generation count mismatch")
        return detail
    try:
        verified = [_capture(root, row, result, capture) for capture in captures]
        for generation, capture in zip(generations, verified[warmups:], strict=True):
            observed, raw = generation["raw_response"], capture["raw-output"]
            cancelled = (
                generation.get("terminal") == "cancelled"
                and capture["status"] == "cancelled"
            )
            if raw != observed and not (cancelled and raw.startswith(observed)):
                raise ValueError("Capture and observed response mismatch")  # noqa: TRY301 - record per-case integrity failure
        detail["captures"] = verified[warmups:]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        detail["issues"].append(str(exc))
    return detail


def _case_page(root: Path, output: Path, row: dict, detail: dict) -> None:
    artifact = row.get("artifact_id", row["id"])
    page = output / "cases" / f"{artifact}.html"
    request, result = detail["request"], detail["result"]
    status = "FAILED" if detail["issues"] else "verified"

    def decision_label(value: object) -> str:
        return (
            "Correct"
            if value is True
            else "Incorrect"
            if value is False
            else "Unavailable"
        )

    def fields(values: list[tuple[str, object]]) -> str:
        return (
            "<dl>"
            + "".join(
                f"<dt>{_escape(label)}</dt><dd>{_pre(value)}</dd>"
                for label, value in values
            )
            + "</dl>"
        )

    parts = [
        '<nav aria-label="Report"><a href="../index.html#case-index">All conditions and cases</a></nav>',
        '<header class="hero"><p class="eyebrow">Case evidence</p>',
        f"<h1>{_escape(row.get('case_id', row['id']))}</h1>",
        f'<p class="muted">{_escape(row.get("condition", "unavailable"))} · '
        f"{_escape(row.get('decision', 'unavailable'))} · {_escape(artifact)}</p>",
        f'<p><span class="badge">First decision: {decision_label(row.get("first"))}</span> '
        f'<span class="badge">Final decision: {decision_label(row.get("final"))}</span></p></header>',
        f'<p class="notice">Capture integrity: {status}. '
        f"Measurement evidence: {_escape(row['evidence_status'])}. "
        f"Decision measurement valid: {_escape(row['decision_valid'])}. "
        "A decision score does not establish execution success.</p>",
    ]
    if detail["issues"]:
        parts.extend(
            ["<h2>Evidence presentation incomplete</h2>", _pre(detail["issues"])]
        )
    if not result:
        parts.append("<p>Model input/output unavailable; no result inferred.</p>")
    else:
        case = request.get("case", {})
        scores = result.get("scores", {})
        attempts = scores.get("attempt_decisions", [])
        final = attempts[-1] if attempts else {}
        product = result.get("product_outcome") or {}
        parts.extend(
            [
                '<section class="panel"><h2>Actual user request</h2>',
                _pre(case.get("input", "unavailable")),
                '</section><div class="comparison">',
                '<section class="panel"><h2>Expected decision</h2>',
                fields(
                    [
                        (
                            "Workflow stage",
                            case.get("expected_workflow_stage", "unavailable"),
                        ),
                        ("Tool", case.get("expected_tool", "unavailable")),
                        ("Parameters", case.get("expected_parameters", "unavailable")),
                    ]
                ),
                '<p class="muted">Oracle reference, not model input.</p></section>',
                '<section class="panel"><h2>Recorded final decision</h2>',
                fields(
                    [
                        ("Workflow stage", final.get("observed_stage", "unavailable")),
                        ("Tool", final.get("observed_tool", "unavailable")),
                        ("Score reason", final.get("reason", "unavailable")),
                    ]
                ),
                '<p class="muted">Recorded scorer fields only. Compare parameter values '
                "with the raw model output below; no new parsing or scoring is performed.</p>",
                "</section></div>",
                '<section class="panel"><h2>Product outcome — separate evidence</h2>',
                '<p class="muted">Tool admission, execution and UI handoff are not the '
                "decision score. Missing observations do not imply success.</p>",
                "<p>"
                + " · ".join(
                    f"{label}: <strong>{_escape(product.get(key, 'unavailable'))}</strong>"
                    for label, key in (
                        ("Measurement valid", "measurement_valid"),
                        ("Outcome", "outcome"),
                        ("Execution", "execution"),
                        ("UI handoff", "ui_handoff"),
                    )
                )
                + "</p>",
                "<details><summary>Recorded product evidence</summary>",
                _pre(product or "unavailable"),
                "</details>",
                "</section><h2>Decision and source details</h2>",
                "<details><summary>Oracle / fixture — scorer reference, not model input</summary>",
                _pre({key: value for key, value in case.items() if key != "input"}),
                _pre(request.get("fixture", {})),
                "</details>",
                "<details><summary>Recorded decision scores — all attempts</summary>",
                _pre(scores),
                "</details>",
            ]
        )
        for index, generation in enumerate(
            result.get("trace", {}).get("generations", [])
        ):
            parts.extend(
                [
                    '<section class="panel">',
                    f"<h2>Generation {index + 1}</h2>",
                    '<p class="muted">Initial response</p>'
                    if index == 0
                    else '<p class="muted">Format-repair response, not a new case attempt</p>',
                    "<details><summary>Actual generation messages</summary>",
                    _pre(generation.get("request", {})),
                    "</details>",
                ]
            )
            if detail["captures"]:
                capture = detail["captures"][index]
                parts.extend(
                    [
                        "<details><summary>Final rendered prompt — hash verified</summary>",
                        _pre(capture["prompt"]),
                        "</details>",
                        "<details open><summary>Raw model output — hash verified</summary>",
                        _pre(capture["raw-output"]),
                        "</details>",
                        _link(capture["path"] / "prompt.txt", page, "Prompt file"),
                        " · ",
                        _link(
                            capture["path"] / "raw-output.txt", page, "Raw output file"
                        ),
                    ]
                )
            else:
                parts.append(
                    "<p>Rendered prompt/raw output not shown: capture integrity unavailable.</p>"
                )
            parts.append("</section>")
        parts.extend(
            [
                "<details><summary>Full observed trace / recovery / errors</summary>",
                _pre(result.get("trace", {})),
                "</details>",
                "<h2>Source artifacts</h2>",
                _link(
                    root / "cases" / f"{artifact}.request.json", page, "Request JSON"
                ),
                " · ",
                _link(
                    root / "cases" / artifact / "result.json",
                    page,
                    "Result and trace JSON",
                ),
                _pre(
                    {
                        key: row.get(key)
                        for key in (
                            "timings",
                            "issues",
                        )
                    }
                ),
            ]
        )
    page.write_text(render_page(row["id"], "\n".join(parts)), encoding="utf-8")


def _rate(value: dict) -> str:
    suffix = "n/a" if value["rate"] is None else f"{value['rate']:.1%}"
    return f"{value['numerator']} / {value['denominator']} ({suffix})"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _excel(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _case_filters(conditions: dict) -> str:
    """Controls match cases.js IDs; filtering never changes exported rows."""
    options = "".join(
        f'<option value="{_escape(name)}">{_escape(name)}</option>'
        for name in conditions
    )
    return f"""
    <h2 id="cases">Explore cases</h2>
    <p class="muted">Open a case to compare expected and observed decisions. Filters combine.</p>
    <div class="filters">
        <label>Search
            <input id="search" aria-label="Filter cases" placeholder="Case ID or request">
        </label>
        <label>Model condition
            <select id="condition"><option value="">All conditions</option>{options}</select>
        </label>
        <label>Category
            <select id="category">
                <option value="">All categories</option>
                <option>Action</option><option>Clarification</option><option>No-call</option>
            </select>
        </label>
        <label>Final decision
            <select id="outcome">
                <option value="">All outcomes</option>
                <option value="correct">Correct</option>
                <option value="incorrect">Incorrect</option>
                <option value="unavailable">Unavailable / invalid measurement</option>
            </select>
        </label>
        <button id="reset" type="button">Reset filters</button>
    </div>
    <p id="case-count" role="status" aria-live="polite"></p>
    <noscript><p>Filters require JavaScript. All cases are listed below.</p></noscript>
    """


def _render_detailed_results(
    report: dict, details: dict, issues: dict, detail_count: int
) -> tuple[list[str], list[str]]:
    """Format saved aggregate results as HTML and Markdown, without rescoring."""
    dev = report["schema"] == "xbrainlab.assistant_dev_report.v1"
    md, body = [], []

    def paragraph(value: str) -> None:
        md.extend([value, ""])
        body.append("<p>" + _escape(value) + "</p>")

    def table(title: str, headers: list[str], rows: list[list]) -> None:
        md.extend(
            [
                "## " + title,
                "",
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
            ]
        )
        anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        body.append(f'<h2 id="{anchor}">{_escape(title)}</h2>')
        for cells in rows:
            md.append(
                "| "
                + " | ".join(
                    str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells
                )
                + " |"
            )
        md.append("")
        body.append(_html_table(headers, rows))

    paragraph(
        "DEV initial baseline. No formal model ranking or Validation/Test conclusion. P95 is descriptive."
        if dev
        else "DEV Pilot only. No formal model ranking, Validation/Test conclusion, or stable P95."
    )
    paragraph(
        f"Partial: {report['partial']}. "
        f"Selected schedule complete: {report['complete_selected_schedule']}."
    )
    if dev:
        paragraph(
            f"Protocol: {report['experiment']['protocol']}. "
            f"Full DEV initial baseline complete (264 cases x 5 models): {report['dev_complete']}. "
            "A complete selected smoke schedule does not satisfy the full initial baseline."
        )
    paragraph(
        f"Evidence presentation {'incomplete' if issues else 'verified'}: "
        f"{len(issues)} / {detail_count} measurements have missing or unverifiable detail artifacts. "
        "Scores below reproduce report.json; capture problems are flagged separately, not rescored."
    )
    paragraph(
        "Macro score equally weights Action, Clarification and No-call. Valid measurement is not a correct "
        "decision. Invalid model output is a measured failure and remains in its score denominator. "
        "Missing/invalid measurement is excluded; product outcome is reported separately."
    )
    body.append(
        '<nav><a href="results.csv">Excel CSV</a> · <a href="report.json">Scoring JSON</a> · '
        '<a href="presentation-audit.json">Detail integrity audit</a> · <a href="#cases">Case index</a></nav>'
    )
    body.append(
        "<nav>"
        + " · ".join(
            f'<a href="#{anchor}">{label}</a>'
            for anchor, label in (
                ("condition-scores", "Scores"),
                ("category-scores", "Categories"),
                ("decision-latency", "Latency"),
                ("setup-and-case-timing", "Setup"),
                ("repair-attempts-and-newly-correct-decisions", "Repairs"),
                ("final-failure-reasons-one-per-wrong-decision", "Failures"),
                ("product-outcomes-separate-from-accuracy", "Product outcomes"),
            )
        )
        + "</nav>"
    )
    md.extend(
        [
            "[Interactive report](index.html) · [Excel CSV](results.csv) · [Scoring JSON](report.json)",
            "",
        ]
    )
    summary, categories, latency, overhead, repairs, failures, products = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    overall, latency_audits = [], []
    for name, condition in report["conditions"].items():
        counts = condition["counts"]
        summary.append(
            [
                name,
                f"{counts['valid_decision']} / {counts['planned']}",
                *[
                    "n/a"
                    if condition["macro"][phase] is None
                    else f"{condition['macro'][phase]:.1%}"
                    for phase in ("first", "final")
                ],
                counts["invalid_model_output"],
                counts["missing"],
                counts["unresolved"],
                counts["invalid_measurement"] + counts["invalid_evidence"],
            ]
        )
        for category, values in condition["categories"].items():
            categories.append(
                [
                    name,
                    category,
                    values["planned"],
                    _rate(values["first"]),
                    _rate(values["final"]),
                ]
            )
        for status, values in condition["decision_latency_seconds"].items():
            latency.append(
                [
                    name,
                    status,
                    values["n"],
                    _number(values["p50"]),
                    *([_number(values["p95"])] if dev else []),
                    _number(values["max"]),
                ]
            )
        if dev:
            overall.append(
                [
                    name,
                    *[
                        _rate(condition["overall"][phase])
                        for phase in ("first", "final")
                    ],
                ]
            )
            audit = condition["decision_latency_audit"]
            latency_audits.append(
                [
                    name,
                    audit["planned"],
                    audit["included"],
                    audit["excluded"],
                    _json(audit["exclusions"]),
                    _json(audit["execution_status_counts"]),
                ]
            )
        for metric, values in condition["overhead_seconds"].items():
            overhead.append(
                [
                    name,
                    metric,
                    values["n"],
                    _number(values["p50"]),
                    _number(values["max"]),
                    _number(values["total"]),
                ]
            )
        values = condition["repairs"]
        repairs.append(
            [
                name,
                *[values["histogram"][str(i)] for i in range(3)],
                values["unavailable"],
                values["first_new_correct"],
                values["second_new_correct"],
            ]
        )
        reasons = Counter()
        for row in report["cases"]:
            if row["condition"] != name or row.get("final") is not False:
                continue
            attempts = (
                details[row["id"]]["result"]
                .get("scores", {})
                .get("attempt_decisions", [])
            )
            reasons[
                attempts[-1].get("reason", "unavailable")
                if attempts
                else row.get("execution_status", "unavailable")
            ] += 1
        failures.extend(
            [name, reason, count] for reason, count in sorted(reasons.items())
        )
        for axis, values in condition["product_counts"].items():
            products.extend(
                [name, axis, outcome, count]
                for outcome, count in sorted(values.items())
            )
    table(
        "Condition scores",
        [
            "Condition",
            "Valid / planned",
            "First macro",
            "Final macro",
            "Invalid output (any attempt)",
            "Missing",
            "Unresolved",
            "Invalid measurement/evidence",
        ],
        summary,
    )
    table(
        "Category scores",
        [
            "Condition",
            "Category",
            "Planned",
            "First correct / valid",
            "Final correct / valid",
        ],
        categories,
    )
    if dev:
        table(
            "Overall scores",
            ["Condition", "First correct / valid", "Final correct / valid"],
            overall,
        )
    paragraph(
        "Latency units: seconds. Overall includes all valid recorded decision terminals, including "
        "invalid output, host-blocked decisions and valid decision timeouts. Success/failure means "
        "final decision correctness. Quantiles use linear interpolation at (n - 1) * p; "
        "missing timing is never replaced by zero or a configured timeout."
        if dev
        else "Latency units: seconds. Success/failure below means final decision correctness among completed "
        "decisions. Timeouts are censored and excluded, never interpreted as completion times."
    )
    table(
        "Decision latency",
        [
            "Condition",
            "Final correctness",
            "n",
            "p50 (s)",
            *(["p95 (s)"] if dev else []),
            "max (s)",
        ],
        latency,
    )
    if dev:
        table(
            "Latency denominator",
            [
                "Condition",
                "Planned",
                "Included",
                "Excluded",
                "Exclusion reasons",
                "Included terminal statuses",
            ],
            latency_audits,
        )
    paragraph(
        "Model load and warmup are separate from decision latency. n shows measured occurrences: "
        "batched runs load once per condition runtime. Setup/case overhead includes superseded "
        "measurements when present. Overlapping timing spans must not be added together."
    )
    table(
        "Setup and case timing",
        ["Condition", "Metric", "n", "p50 (s)", "max (s)", "total (s)"],
        overhead,
    )
    table(
        "Repair attempts and newly correct decisions",
        [
            "Condition",
            "0 repairs",
            "1 repair",
            "2 repairs",
            "Unavailable",
            "Rescued at repair 1",
            "Rescued at repair 2",
        ],
        repairs,
    )
    table(
        "Final failure reasons (one per wrong decision)",
        ["Condition", "Reason", "Cases"],
        failures,
    )
    table(
        "Product outcomes (separate from accuracy)",
        ["Condition", "Axis", "Outcome", "Cases"],
        products,
    )
    paragraph(
        f"Active budget charged: {report['active_budget']['charged_seconds']:.2f} s."
    )
    for limitation in report["limitations"]:
        paragraph(limitation)
    return body, md


def _write_case_index(
    root: Path, output: Path, report: dict, details: dict, previous_details: dict
) -> tuple[list[str], list[str]]:
    """Write case pages and CSV from the same rows; return their HTML/Markdown index."""
    md, body = [], []
    body.append(_case_filters(report["conditions"]))
    body.append(
        '<div class=table><table id="case-index"><thead><tr><th>Case</th><th>Category</th>'
        "<th>Measurement</th><th>First / final</th><th>Capture integrity</th><th>Request</th></tr></thead><tbody>"
    )
    md.extend(
        [
            "## Case index",
            "",
            "Each case page separates the oracle from actual model messages and includes the full trace.",
            "",
        ]
    )
    with (output / "results.csv").open("x", encoding="utf-8-sig", newline="") as target:
        fields = [
            "id",
            "condition",
            "case_id",
            "category",
            "request",
            "evidence_status",
            "measurement_valid",
            "first_correct",
            "final_correct",
            "invalid_model_output_any_attempt",
            "execution_status",
            "decision_seconds",
            "repair_count",
            "final_failure_reason",
            "product_outcome",
            "capture_integrity",
            "detail_issues",
            "case_page",
            "request_sha256",
            "result_sha256",
        ]
        writer = csv.writer(target)
        writer.writerow(fields)
        for row in report["cases"]:
            detail = details[row["id"]]
            _case_page(root, output, row, detail)
            request = detail["request"].get("case", {}).get("input", "unavailable")
            integrity = "failed" if detail["issues"] else "verified"
            link = f"cases/{row.get('artifact_id', row['id'])}.html"
            attempts = detail["result"].get("scores", {}).get("attempt_decisions", [])
            reason = (
                attempts[-1].get("reason", "")
                if attempts and row.get("final") is False
                else ""
            )
            values = [
                row["id"],
                row["condition"],
                row["case_id"],
                row["decision"],
                request,
                row["evidence_status"],
                row["decision_valid"],
                row.get("first"),
                row.get("final"),
                row.get("invalid_model_output"),
                row.get("execution_status"),
                row.get("timings", {}).get("decision"),
                row.get("repairs", {}).get("count"),
                reason,
                _json(row.get("product_outcome")),
                integrity,
                "; ".join(detail["issues"]),
                link,
                row.get("request_sha256"),
                row.get("result_sha256"),
            ]
            writer.writerow([_excel(value) for value in values])
            outcome = "unavailable"
            if row["decision_valid"] and isinstance(row.get("final"), bool):
                outcome = "correct" if row["final"] else "incorrect"
            body.append(
                f'<tr data-condition="{_escape(row["condition"])}" data-category="{_escape(row["decision"])}" data-outcome="{outcome}">'
                f'<td><a href="{quote(link)}">{_escape(row["id"])}</a></td>'
                + "".join(
                    f"<td>{_escape(value)}</td>"
                    for value in [
                        row["decision"],
                        row["evidence_status"],
                        f"{row.get('first', 'n/a')} / {row.get('final', 'n/a')}",
                        integrity,
                        request,
                    ]
                )
                + "</tr>"
            )
            md.append(
                f"- [{row['id']}]({link}) — {row['evidence_status']}; first/final {row.get('first', 'n/a')}/{row.get('final', 'n/a')}; captures {integrity}"
            )
    body.append(
        '</tbody></table></div><p id="no-cases" hidden>No cases match these filters.</p>'
        '<div class="pagination" hidden><button id="previous" type="button">Previous</button>'
        '<span id="page-number"></span><button id="next" type="button">Next</button></div>'
    )
    if report.get("superseded_cases"):
        note = "Superseded measurements remain preserved below and are excluded from the selected score and latency denominators."
        md.extend([note, ""])
        body.append('<details id="history"><summary>Earlier attempts</summary>')
        body.append("<p>" + _escape(note) + "</p>")
        md.extend(["## Superseded measurements", ""])
        body.append("<h2>Superseded measurements</h2>")
        for row in report["superseded_cases"]:
            artifact = row["artifact_id"]
            detail = previous_details[artifact]
            _case_page(root, output, row, detail)
            link = f"cases/{artifact}.html"
            md.append(
                f"- [{artifact}]({link}) — {row.get('measurement_status', row['evidence_status'])}"
            )
            body.append(f'<p><a href="{quote(link)}">{_escape(artifact)}</a></p>')
        body.append("</details>")
    return body, md


def write_presentation(report: dict, output: Path) -> None:
    """Write a local report and case index without changing aggregate report JSON."""
    root = Path(report["run"])
    (output / "cases").mkdir()
    dev = report["schema"] == "xbrainlab.assistant_dev_report.v1"
    details = {
        row["id"]: _details(root, row, require_generation=dev)
        for row in report["cases"]
    }
    if dev and any(
        details[row["id"]]["issues"] != row["capture_integrity"]["issues"]
        for row in report["cases"]
    ):
        raise ValueError(
            "Capture artifacts changed during report; retain evidence and rebuild from a stable snapshot"
        )
    previous_details = {
        row["artifact_id"]: _details(root, row)
        for row in report.get("superseded_cases", [])
    }
    issues = {key: value["issues"] for key, value in details.items() if value["issues"]}
    issues.update(
        {
            "superseded:" + key: value["issues"]
            for key, value in previous_details.items()
            if value["issues"]
        }
    )
    detail_count = len(details) + len(previous_details)
    directory = root.parent if dev and root.name == "raw" else root
    title = experiment_title(directory, dev=dev)
    md, body = (
        ["# " + title, ""],
        [
            '<header class="hero"><span class="eyebrow">XBrainLab / Experiment report</span>',
            f"<h1>{_escape(title)}</h1>",
            f'<p class="muted">{_escape(experiment_conditions(report, dev=dev))}</p>',
            '<p class="muted">Evaluation complete</p>'
            if report["complete_selected_schedule"]
            and not render_evidence_notice(issues)
            else '<p class="notice">Selected results incomplete</p>',
            "</header>",
            render_evidence_notice(issues),
            render_overview(report),
        ],
    )

    detail_html, detail_markdown = _render_detailed_results(
        report, details, issues, detail_count
    )
    case_html, case_markdown = _write_case_index(
        root, output, report, details, previous_details
    )
    body.extend(case_html)
    body.append('<details id="evidence"><summary>Technical details</summary>')
    body.extend(detail_html)
    body.append("</details>")
    # Initialize filters and deep links only after all referenced sections exist.
    body.append(f"<script>{_CASE_SCRIPT}</script>")
    md.extend(detail_markdown)
    md.extend(case_markdown)
    (output / "index.html").write_text(
        render_page(title, "\n".join(body)), encoding="utf-8"
    )
    (output / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (output / "presentation-audit.json").write_text(
        _json(
            {
                "complete": not issues,
                "selected_complete": not any(
                    value["issues"] for value in details.values()
                ),
                "case_count": len(details),
                "superseded_measurement_count": len(previous_details),
                "issues": issues,
                "renderer_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "presentation_assets_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in _ASSET_BYTES.items()
                },
                "report_script_sha256": hashlib.sha256(
                    Path(__file__).with_name("assistant_pilot_report.py").read_bytes()
                ).hexdigest(),
                "scope": "Request/result digests and capture metadata/prompt/raw hashes; not an independent scorer audit.",
            }
        ),
        encoding="utf-8",
    )
