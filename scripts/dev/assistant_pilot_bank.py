"""Read the explicitly supplied non-Test authoring workbook; never discover banks.

This is a bounded reader for this workbook contract, not a general Excel reader.
It preserves human/oracle provenance and makes no product-readiness claims.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from copy import copy
from pathlib import Path, PurePosixPath
from xml.sax.saxutils import quoteattr

SCHEMA = "xbrainlab.assistant_pilot_bank.v1"
DEV_EXPERIMENT = {
    "protocol": "xbrainlab.assistant_dev_initial.v1",
    "stage": "DEV",
    "candidate": "initial",
    "candidate_index": 1,
    "max_candidates": 5,
    "rag_enabled": True,
    "projection_id": "dev-state-card-nuisance-v1",
    "qt_platform": "offscreen",
}
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_REQUIRED = {"DEV", "VALID", "ground_truth", "情境定義"}
_ALLOWED = _REQUIRED | {"使用說明", "覆蓋與題數", "語義核對", "跨組近似", "執行驗證"}
_MAX_FILE = 16 * 1024 * 1024
_MAX_MEMBER = 4 * 1024 * 1024
_MAX_TOTAL = 32 * 1024 * 1024
_HUMAN = {"題號", "Family", "英文題目", "情境編號"}
_TRUTH = {
    "case_id",
    "family_id",
    "split",
    "decision",
    "expected_tool",
    "expected_parameters_json",
    "missing_fields_json",
    "explicit_info_json",
    "expected_workflow_stage",
    "fixture_id",
}
_FIXTURE = {"fixture_id", "family_id", "workflow_stage", "起始情境", "結構化條件_JSON"}


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    data = archive.read(name)
    # Decode first: UTF-16/NUL obfuscation cannot bypass entity/DTD rejection.
    text = data.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Unsafe XML declaration")
    # ZIP/XML byte limits and UTF-8 DTD/entity rejection precede this parser.
    root = ET.fromstring(text)  # noqa: S314
    if sum(1 for _ in root.iter()) > 100_000:
        raise ValueError("XML element limit exceeded")
    return root


def _sheets(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = _xml(archive, "xl/workbook.xml")
    sheets = workbook.findall(f"{_NS}sheets/{_NS}sheet")
    names = [sheet.get("name", "") for sheet in sheets]
    # Metadata gate precedes sharedStrings and all worksheet contents.
    if (
        len(names) != len(set(names))
        or set(names) - _ALLOWED
        or not set(names) >= _REQUIRED
    ):
        raise ValueError("Unsupported, duplicate or missing workbook sheet")
    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    targets = {}
    for rel in relationships.findall(f"{_PACKAGE}Relationship"):
        ident, target = rel.get("Id", ""), rel.get("Target", "")
        if (
            not ident
            or ident in targets
            or rel.get("TargetMode", "Internal") != "Internal"
        ):
            raise ValueError("Unsafe or duplicate workbook relationship")
        parts = PurePosixPath(target).parts
        if (
            not target
            or target.startswith("/")
            or "\\" in target
            or ":" in target
            or ".." in parts
        ):
            raise ValueError("Unsafe workbook target")
        targets[ident] = (target, rel.get("Type"))
    result = {}
    for sheet in sheets:
        target, kind = targets.get(sheet.get(f"{_REL}id"), ("", ""))
        if kind != _REL[1:-1] + "/worksheet" or not re.fullmatch(
            r"worksheets/sheet[0-9]+\.xml", target
        ):
            raise ValueError("Unsafe worksheet target")
        result[sheet.get("name")] = "xl/" + target
    if len(set(result.values())) != len(result):
        raise ValueError("Duplicate worksheet targets")
    return result


def _table(
    archive: zipfile.ZipFile, path: str, shared: list[str], required: set[str]
) -> list[dict[str, str]]:
    root = _xml(archive, path)
    rows = root.findall(f"{_NS}sheetData/{_NS}row")
    if not rows or len(rows) > 5001:
        raise ValueError("Missing rows or worksheet row limit exceeded")
    records, headers, previous_row = [], None, 0
    for row in rows:
        row_number = int(row.get("r", "0"))
        if row_number <= previous_row or row_number > 5001:
            raise ValueError("Invalid or duplicate worksheet row")
        previous_row = row_number
        values = {}
        for cell in row.findall(f"{_NS}c"):
            match = re.fullmatch(r"([A-Z]{1,2})([1-9][0-9]*)", cell.get("r", ""))
            if (
                not match
                or int(match[2]) != row_number
                or cell.find(f"{_NS}f") is not None
            ):
                raise ValueError("Invalid cell address or selected-cell formula")
            column = 0
            for char in match[1]:
                column = column * 26 + ord(char) - 64
            if column > 64 or column in values:
                raise ValueError("Duplicate cell or column limit exceeded")
            kind = cell.get("t", "n")
            value = cell.findtext(f"{_NS}v", default="")
            if kind == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(f".//{_NS}t"))
            elif kind == "s":
                if not value.isdecimal() or int(value) >= len(shared):
                    raise ValueError("Invalid shared string reference")
                value = shared[int(value)]
            elif kind not in {"n", "str", "b"}:
                raise ValueError("Unsupported selected cell type")
            if len(value) > 100_000:
                raise ValueError("Selected cell length limit exceeded")
            values[column] = value
        if not any(values.values()):
            continue
        if headers is None:
            headers = [values.get(index, "") for index in range(1, max(values) + 1)]
            if (
                "" in headers
                or len(headers) != len(set(headers))
                or not required <= set(headers)
            ):
                raise ValueError("Missing or duplicate worksheet headers")
        else:
            if max(values) > len(headers):
                raise ValueError("Unexpected worksheet column")
            records.append(
                {name: values.get(index, "") for index, name in enumerate(headers, 1)}
            )
    if not records:
        raise ValueError("Empty selected worksheet")
    return records


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("Nonfinite JSON number")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite JSON number")
    return result


def _json(value: str, expected: type):
    result = json.loads(
        value,
        object_pairs_hook=_json_object,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )
    if type(result) is not expected:
        raise ValueError("Unexpected JSON value type")
    return result


def _index(rows: list[dict[str, str]], field: str) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        ident = row[field]
        if not ident or ident != ident.strip() or ident in result:
            raise ValueError("Missing, invalid or duplicate identifier")
        result[ident] = row
    return result


def _normalize(tables: dict[str, list[dict[str, str]]]) -> tuple[list[dict], dict]:
    truths = _index(tables["ground_truth"], "case_id")
    fixture_rows = _index(tables["情境定義"], "fixture_id")
    fixtures = {
        key: {"conditions": _json(row["結構化條件_JSON"], dict), "metadata": row}
        for key, row in fixture_rows.items()
    }
    cases, seen, family_splits, used_fixtures = [], set(), {}, set()
    for split in ("DEV", "VALID"):
        for case_id, human in _index(tables[split], "題號").items():
            truth = truths.get(case_id)
            family, fixture_id = human["Family"], human["情境編號"]
            if not truth or case_id in seen or not case_id.startswith(split + "-"):
                raise ValueError("Missing or conflicting case identity")
            if (
                truth["split"] != split
                or truth["family_id"] != family
                or truth["fixture_id"] != fixture_id
                or not family
                or not human["英文題目"].strip()
            ):
                raise ValueError("Mismatched split, family, fixture or empty input")
            if family_splits.setdefault(family, split) != split:
                raise ValueError("Cross-split family leakage")
            fixture = fixture_rows.get(fixture_id)
            stage = truth["expected_workflow_stage"]
            if (
                not fixture
                or fixture["family_id"] != family
                or not stage
                or fixture["workflow_stage"] != stage
            ):
                raise ValueError("Missing or mismatched fixture reference")
            conditions = fixtures[fixture_id]["conditions"]
            if "stage" in conditions and conditions["stage"] != stage:
                raise ValueError("Conflicting fixture stage")
            decision = truth["decision"]
            if (
                decision not in {"Action", "Clarification", "No-call"}
                or not truth["expected_tool"].strip()
            ):
                raise ValueError("Invalid decision or expected tool")
            _json(truth["missing_fields_json"], list)
            _json(truth["explicit_info_json"], dict)
            parameters = (
                _json(truth["expected_parameters_json"], dict)
                if decision == "Action"
                else None
            )
            if (
                decision != "Action"
                and truth["expected_parameters_json"]
                != "N/A: message is free text; use parameter_rule"
            ):
                raise ValueError("Unexpected non-action parameter contract")
            cases.append(
                {
                    "case_id": case_id,
                    "family_id": family,
                    "split": split,
                    "input": human["英文題目"],
                    "decision": decision,
                    "expected_tool": truth["expected_tool"],
                    "expected_parameters": parameters,
                    "expected_workflow_stage": stage,
                    "fixture_id": fixture_id,
                    "metadata": {"ground_truth": truth, "human": human},
                }
            )
            seen.add(case_id)
            used_fixtures.add(fixture_id)
    if seen != set(truths) or used_fixtures != set(fixtures):
        raise ValueError("Unmatched oracle or fixture records")
    return cases, fixtures


def _read_bank(path: str | Path) -> tuple[bytes, dict]:
    """Read only one explicit DEV/VALID XLSX; reject unsafe or inconsistent inputs."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Expected an explicit XLSX file")
    with path.open("rb") as source:
        content = source.read(_MAX_FILE + 1)
    if len(content) > _MAX_FILE:
        raise ValueError("Workbook file limit exceeded")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(members) > 128 or len(names) != len(set(names)):
                raise ValueError("Archive member limit or duplicate member")
            if sum(member.file_size for member in members) > _MAX_TOTAL:
                raise ValueError("Archive expanded size limit exceeded")
            for member in members:
                name = member.filename
                if (
                    member.file_size > _MAX_MEMBER
                    or member.flag_bits & 1
                    or name.startswith("/")
                    or ".." in PurePosixPath(name).parts
                    or "\\" in name
                    or ":" in name
                ):
                    raise ValueError("Unsafe or oversized archive member")
            sheets = _sheets(archive)
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = [
                    "".join(t.text or "" for t in node.iter(f"{_NS}t"))
                    for node in _xml(archive, "xl/sharedStrings.xml").findall(
                        f"{_NS}si"
                    )
                ]
            tables = {
                name: _table(archive, sheets[name], shared, required)
                for name, required in (
                    ("DEV", _HUMAN),
                    ("VALID", _HUMAN),
                    ("ground_truth", _TRUTH),
                    ("情境定義", _FIXTURE),
                )
            }
            cases, fixtures = _normalize(tables)
    except (
        KeyError,
        ET.ParseError,
        UnicodeError,
        zipfile.BadZipFile,
        RecursionError,
    ) as error:
        raise ValueError("Invalid or incomplete non-Test workbook") from error
    return content, {
        "schema": SCHEMA,
        "source": {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(content).hexdigest(),
            "sheets": list(sheets),
        },
        "cases": cases,
        "fixtures": fixtures,
    }


def _without_review_status(content: bytes) -> bytes:
    """Remove one retired authoring column from an already validated workbook."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        sheets = _sheets(archive)
        name = sheets["ground_truth"]
        shared = (
            [
                "".join(t.text or "" for t in node.iter(f"{_NS}t"))
                for node in _xml(archive, "xl/sharedStrings.xml")
            ]
            if "xl/sharedStrings.xml" in archive.namelist()
            else []
        )
        headers = list(_table(archive, name, shared, _TRUTH)[0])
        if "review_status" not in headers:
            return content
        removed = headers.index("review_status") + 1
        root = _xml(archive, name)
        # Do not silently damage rich Excel constructs outside this export contract.
        if any(
            root.find(f"{_NS}{tag}") is not None
            for tag in (
                "tableParts",
                "mergeCells",
                "conditionalFormatting",
                "extLst",
                "hyperlinks",
            )
        ):
            raise ValueError(
                "review_status removal requires a plain ground_truth table"
            )
        for member in archive.namelist():
            if member == "xl/workbook.xml" or member in sheets.values():
                for node in _xml(archive, member).iter():
                    if (
                        node.tag in {f"{_NS}f", f"{_NS}definedName"}
                        and "ground_truth" in (node.text or "").lower()
                    ):
                        raise ValueError(
                            "review_status removal cannot update cross-sheet formulas"
                        )

        def bounds(reference: str) -> tuple[int, str]:
            match = re.fullmatch(r"([A-Z]+)([0-9]+)", reference)
            if match is None:
                raise ValueError(
                    "Unsupported worksheet reference during review_status removal"
                )
            column = 0
            for char in match[1]:
                column = column * 26 + ord(char) - 64
            return column, match[2]

        def address(column: int, row: str) -> str:
            letters = ""
            while column:
                column, rest = divmod(column - 1, 26)
                letters = chr(65 + rest) + letters
            return letters + row

        def shifted(reference: str) -> str:
            start, _, end = reference.partition(":")
            left, first = bounds(start)
            right, last = bounds(end or start)
            if left == right == removed:
                return ""
            left -= left > removed
            right -= right >= removed
            return address(left, first) + (":" + address(right, last) if end else "")

        for row in root.findall(f"{_NS}sheetData/{_NS}row"):
            row.attrib.pop("spans", None)
            for cell in list(row):
                reference = shifted(cell.attrib["r"])
                if reference:
                    cell.set("r", reference)
                else:
                    row.remove(cell)
        columns = root.find(f"{_NS}cols")
        if columns is not None:
            for col in list(columns):
                left, right = int(col.attrib["min"]), int(col.attrib["max"])
                if left == right == removed:
                    columns.remove(col)
                else:
                    col.set("min", str(left - (left > removed)))
                    col.set("max", str(right - (right >= removed)))
        for tag in ("dimension", "autoFilter"):
            node = root.find(f"{_NS}{tag}")
            if node is not None:
                start, _ = bounds(node.attrib["ref"].split(":")[0])
                for column in list(node):
                    if column.tag == f"{_NS}filterColumn":
                        absolute = start + int(column.attrib["colId"])
                        if absolute == removed:
                            node.remove(column)
                        elif start <= removed < absolute:
                            column.set("colId", str(int(column.attrib["colId"]) - 1))
                reference = shifted(node.attrib["ref"])
                if reference:
                    node.set("ref", reference)
                else:
                    root.remove(node)
        validations = root.find(f"{_NS}dataValidations")
        if validations is not None:
            for node in list(validations):
                refs = list(
                    filter(None, (shifted(ref) for ref in node.attrib["sqref"].split()))
                )
                if refs:
                    for formula in node:
                        if formula.tag in {
                            f"{_NS}formula1",
                            f"{_NS}formula2",
                        } and not re.fullmatch(
                            r'"[^"]*"|-?[0-9]+(?:\.[0-9]+)?', formula.text or ""
                        ):
                            raise ValueError(
                                "review_status removal cannot update validation formula references"
                            )
                    node.set("sqref", " ".join(refs))
                else:
                    validations.remove(node)
            if len(validations):
                validations.set("count", str(len(validations)))
            else:
                root.remove(validations)
        for node in root.iter():
            for attr in ("activeCell", "topLeftCell", "sqref", "ref"):
                # References already updated above must not be shifted twice.
                if (
                    node.tag
                    in {
                        f"{_NS}pane",
                        f"{_NS}selection",
                        f"{_NS}sortState",
                        f"{_NS}sortCondition",
                    }
                    and attr in node.attrib
                ):
                    refs = [shifted(ref) for ref in node.attrib[attr].split()]
                    node.set(attr, " ".join(filter(None, refs)) or "A1")
        # iterparse emits (event, (prefix, URI)); preserve even unused mc:Ignorable prefixes.
        namespaces = dict(
            item
            for _, item in ET.iterparse(  # noqa: S314 - same bytes passed bounded _xml DTD/entity checks
                io.BytesIO(archive.read(name)), events=["start-ns"]
            )
        )
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)
        xml = ET.tostring(root, encoding="unicode")
        extra = "".join(
            f" xmlns{':' + prefix if prefix else ''}={quoteattr(uri)}"
            for prefix, uri in namespaces.items()
            if f"xmlns{':' + prefix if prefix else ''}=" not in xml.split(">", 1)[0]
        )
        xml = xml.replace(">", extra + ">", 1)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            target.comment = archive.comment
            for member in archive.infolist():
                target.writestr(
                    copy(member),
                    xml.encode("utf-8")
                    if member.filename == name
                    else archive.read(member),
                )
        return output.getvalue()


def dev_bank_bytes(path: str | Path) -> bytes:
    """Validate first, then export without retired review metadata; never edit source."""
    content, _ = _read_bank(path)
    return _without_review_status(content)


def load_bank(path: str | Path, *, drop_review_status: bool = False) -> dict:
    """Historical intake stays byte-exact; new DEV hashes the exported workbook."""
    content, bank = _read_bank(path)
    if drop_review_status:
        exported = _without_review_status(content)
        bank["source"]["sha256"] = hashlib.sha256(exported).hexdigest()
        for case in bank["cases"]:
            case["metadata"]["ground_truth"].pop("review_status", None)
    return bank


def build_pilot_selection(bank: dict) -> dict:
    """Select the agreed DEV families/longest variants, independent of scores/order."""
    if not isinstance(bank, dict) or bank.get("schema") != SCHEMA:
        raise ValueError("Expected a normalized pilot bank")
    source = bank.get("source")
    digest = source.get("sha256") if isinstance(source, dict) else None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Missing or invalid bank source hash")
    cases = bank.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Missing bank cases")
    groups = {
        f"{category}{number:02}": {}
        for category, count in (("A", 18), ("C", 6), ("N", 3))
        for number in range(1, count + 1)
    }
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or case.get("split") not in {"DEV", "VALID"}:
            raise ValueError("Unsupported case split")
        split, identifier, family = (
            case["split"],
            case.get("case_id"),
            case.get("family_id"),
        )
        if not isinstance(identifier, str) or not isinstance(family, str):
            raise ValueError("Invalid case identity")
        match = re.fullmatch(
            r"(DEV|VALID)-([ACN][0-9]{2})-([0-9]{2})-V[0-9]+", identifier
        )
        if (
            not match
            or match[1] != split
            or identifier.rsplit("-", 1)[0] != family
            or identifier in seen
            or match[2] not in groups
        ):
            raise ValueError("Duplicate or mismatched case/family/group identity")
        seen.add(identifier)
        if split == "VALID":
            continue  # Selection never examines Validation input or oracle.
        group = match[2]
        decision = {"A": "Action", "C": "Clarification", "N": "No-call"}[group[0]]
        text, tool = case.get("input"), case.get("expected_tool")
        if (
            case.get("decision") != decision
            or not isinstance(text, str)
            or not text.strip()
            or not isinstance(tool, str)
            or not tool.strip()
            or (group[0] != "A" and tool != "respond_to_user")
        ):
            raise ValueError("Invalid DEV decision, input or expected tool")
        variants = groups[group].setdefault(family, [])
        if variants and variants[0]["expected_tool"] != tool:
            raise ValueError("Conflicting expected tools within a family")
        variants.append(case)
    selected, first_by_group = [], {}
    for group, families in groups.items():
        quota = 2 if group.startswith("N") else 1
        if len(families) < quota:
            raise ValueError("Insufficient Pilot family coverage")
        for family in sorted(families)[:quota]:
            case = min(
                families[family],
                key=lambda item: (-len(item["input"]), item["case_id"]),
            )
            selected.append(case)
            first_by_group.setdefault(group, case["case_id"])
    action_tools = [
        case["expected_tool"] for case in selected if case["decision"] == "Action"
    ]
    if len(set(action_tools)) != 18 or "respond_to_user" in action_tools:
        raise ValueError("Pilot must cover 18 distinct action tools")
    phase_one = [
        first_by_group[group] for group in ("A05", "A08", "C01", "C02", "N02", "N03")
    ]
    identifiers = [case["case_id"] for case in selected]
    return {
        "schema": "xbrainlab.assistant_pilot_selection.v1",
        "source_sha256": digest,
        "selection_rule": "DEV A01-A18/C01-C06 first lexicographic family; N01-N03 first two families; longest input per family, case_id ascending ties; phase one A05,A08,C01,C02,N02-first,N03-first",
        "case_ids": identifiers,
        "phase_one_case_ids": phase_one,
        "phase_two_case_ids": [
            identifier for identifier in identifiers if identifier not in phase_one
        ],
    }


def build_dev_selection(bank: dict) -> dict:
    """Select the complete reviewed DEV population, never score-select variants."""
    # Reuse established identity, decision and tool-family validation.
    build_pilot_selection(bank)
    cases = [case for case in bank["cases"] if case["split"] == "DEV"]
    counts = dict(Counter(case["decision"] for case in cases))
    families = Counter(case["family_id"] for case in cases)
    if counts != {"Action": 144, "Clarification": 48, "No-call": 72} or (
        len(families) != 66 or set(families.values()) != {4}
    ):
        raise ValueError("Full DEV requires 264 cases / 66 four-variant families")
    identifiers = sorted(case["case_id"] for case in cases)
    return {
        "schema": "xbrainlab.assistant_dev_selection.v1",
        "source_sha256": bank["source"]["sha256"],
        "selection_rule": "All reviewed DEV cases, case_id ascending; no VALID/TEST selection",
        "counts": counts,
        "case_ids": identifiers,
        "phase_one_case_ids": identifiers,
        "phase_two_case_ids": [],
    }
