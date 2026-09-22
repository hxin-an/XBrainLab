"""Offline, escaped presentation of Pilot scores and hash-verified case evidence.

This module renders the existing report; it does not score or amend measurements.
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
_STYLE = """
body{font:16px/1.55 system-ui,sans-serif;color:#172638;background:#f3f6fa;margin:0}
main{max-width:1280px;margin:auto;padding:32px}h1,h2,h3{line-height:1.2}
h1{font-size:32px}h2{margin-top:36px}a{color:#075ea8}small{color:#526275}
table{border-collapse:collapse;width:100%;background:white;font-size:14px}
th,td{border-bottom:1px solid #d7e0eb;padding:10px;text-align:left;vertical-align:top}
th{background:#e7eef7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;
padding:16px;border:1px solid #d7e0eb;border-radius:6px;font:13px/1.55 monospace}
details{margin:12px 0}summary{cursor:pointer;font-weight:600}.table{overflow-x:auto}
.notice{padding:16px;border-left:4px solid #bb7700;background:#fff3db}
input{padding:10px;width:min(550px,90%);font:inherit}nav{margin:20px 0}
@media(max-width:700px){main{padding:16px}th,td{padding:6px}}
"""


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _pre(value: object) -> str:
    return (
        "<pre>" + _escape(value if isinstance(value, str) else _json(value)) + "</pre>"
    )


def _page(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_escape(title)}</title><style>{_STYLE}</style><main>{content}</main></html>"
    )


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
    parts = [
        '<nav><a href="../index.html">All conditions and cases</a></nav>',
        f"<h1>{_escape(row['id'])}</h1>",
        f'<p class="notice">Capture integrity: {status}. '
        f"Measurement evidence: {_escape(row['evidence_status'])}. "
        f"Decision measurement valid: {_escape(row['decision_valid'])}. "
        f"Final decision correct: {_escape(row.get('final', 'unavailable'))}.</p>",
    ]
    if detail["issues"]:
        parts.extend(
            ["<h2>Evidence presentation incomplete</h2>", _pre(detail["issues"])]
        )
    if not result:
        parts.append("<p>Model input/output unavailable; no result inferred.</p>")
    else:
        parts.extend(
            [
                "<h2>Actual user request</h2>",
                _pre(request["case"].get("input", "unavailable")),
                "<details><summary>Oracle / fixture — scorer reference, not model input</summary>",
                _pre(
                    {
                        key: value
                        for key, value in request["case"].items()
                        if key != "input"
                    }
                ),
                _pre(request.get("fixture", {})),
                "</details>",
                "<details><summary>Decision score and product outcome (separate measurements)</summary>",
                _pre(result.get("scores", {})),
                _pre(result.get("product_outcome", {})),
                "</details>",
            ]
        )
        for index, generation in enumerate(
            result.get("trace", {}).get("generations", [])
        ):
            parts.extend(
                [
                    f"<h2>Generation {index + 1}</h2>",
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
                        "<h3>Raw model output — hash verified</h3>",
                        _pre(capture["raw-output"]),
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
                            "request_sha256",
                            "result_sha256",
                            "timings",
                            "issues",
                        )
                    }
                ),
            ]
        )
    page.write_text(_page(row["id"], "\n".join(parts)), encoding="utf-8")


def _rate(value: dict) -> str:
    suffix = "n/a" if value["rate"] is None else f"{value['rate']:.1%}"
    return f"{value['numerator']} / {value['denominator']} ({suffix})"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _excel(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


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
    title = "Assistant DEV initial baseline" if dev else "Assistant Pilot evidence"
    md, body = ["# " + title, ""], [f"<h1>{title}</h1>"]

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
        body.append(
            f'<h2 id="{anchor}">{_escape(title)}</h2><div class=table><table><thead><tr>'
            + "".join(f"<th>{_escape(item)}</th>" for item in headers)
            + "</tr></thead><tbody>"
        )
        for cells in rows:
            md.append(
                "| "
                + " | ".join(
                    str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells
                )
                + " |"
            )
            body.append(
                "<tr>"
                + "".join(f"<td>{_escape(cell)}</td>" for cell in cells)
                + "</tr>"
            )
        md.append("")
        body.append("</tbody></table></div>")

    paragraph(
        "DEV initial baseline. No formal model ranking or Validation/Test conclusion. P95 is descriptive."
        if dev
        else "DEV Pilot only. No formal model ranking, Validation/Test conclusion, or stable P95."
    )
    paragraph(
        f"Frozen source: {report['frozen_source']['head']}. Partial: {report['partial']}. "
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
    paragraph(
        f"Manifest SHA256: {report['manifest_sha256']}. Journal SHA256: {report['journal_sha256']}."
    )
    body.append(
        '<h2 id="cases">Case index</h2><p>Search condition, case, category, status, or request.</p>'
        '<input id="search" aria-label="Filter cases" placeholder="Filter cases">'
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
            body.append(
                f'<tr><td><a href="{quote(link)}">{_escape(row["id"])}</a></td>'
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
        "</tbody></table></div><script>document.getElementById('search').addEventListener('input',"
        "function(){const q=this.value.toLowerCase();document.querySelectorAll('#case-index tbody tr')"
        ".forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>"
    )
    if report.get("superseded_cases"):
        paragraph(
            "Superseded measurements remain preserved below and are excluded from the selected score and latency denominators."
        )
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
    (output / "index.html").write_text(_page(title, "\n".join(body)), encoding="utf-8")
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
                "report_script_sha256": hashlib.sha256(
                    Path(__file__).with_name("assistant_pilot_report.py").read_bytes()
                ).hexdigest(),
                "scope": "Request/result digests and capture metadata/prompt/raw hashes; not an independent scorer audit.",
            }
        ),
        encoding="utf-8",
    )
