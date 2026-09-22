"""Real small XLSX files protect the explicit non-Test bank intake contract."""

from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile
from copy import deepcopy
from xml.sax.saxutils import escape

import pytest

from scripts.dev.assistant_pilot_bank import SCHEMA, build_pilot_selection, load_bank

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _rows():
    humans, truths, fixtures = [], [], []
    for split in ("DEV", "VALID"):
        family = f"{split}-A01-01"
        case_id = family + "-V0"
        fixture_id = "FX-" + family
        humans.append(
            {
                "題號": case_id,
                "Family": family,
                "英文題目": "Open import.",
                "情境編號": fixture_id,
                "情境": "Empty workspace",
                "版本": "Human original",
            }
        )
        truths.append(
            {
                "case_id": case_id,
                "family_id": family,
                "split": split,
                "decision": "Action",
                "expected_tool": "import_eeg_data",
                "expected_parameters_json": "{}",
                "missing_fields_json": "[]",
                "explicit_info_json": "{}",
                "expected_workflow_stage": "empty",
                "fixture_id": fixture_id,
                "review_status": "待人工複核",
                "source_sha": "old-evidence",
                "parameter_rule": "exact {}",
            }
        )
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "family_id": family,
                "workflow_stage": "empty",
                "起始情境": "Empty workspace",
                "結構化條件_JSON": '{"stage":"empty"}',
            }
        )
    return {
        "DEV": [humans[0]],
        "VALID": [humans[1]],
        "ground_truth": truths,
        "情境定義": fixtures,
    }


def _column(index):
    out = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(65 + remainder) + out
    return out


def _workbook(
    tmp_path,
    rows=None,
    *,
    sheet_name=None,
    target=None,
    formula=False,
    entity=False,
    corrupt_shared=False,
    huge=False,
):
    rows = _rows() if rows is None else rows
    sheets = list(rows)
    if sheet_name:
        sheets.append(sheet_name)
    entries = {}
    entries["xl/workbook.xml"] = (
        f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>'
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, name in enumerate(sheets, 1)
        )
        + "</sheets></workbook>"
    )
    entries["xl/_rels/workbook.xml.rels"] = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="{REL}/worksheet" '
            f'Target="{target if i == 1 and target else f"worksheets/sheet{i}.xml"}"/>'
            for i in range(1, len(sheets) + 1)
        )
        + "</Relationships>"
    )
    for i, name in enumerate(sheets, 1):
        records = rows.get(name, [])
        headers = list(records[0]) if records else []
        values = [headers] + [[row.get(h, "") for h in headers] for row in records]
        xmlrows = []
        for r, vals in enumerate(values, 1):
            cells = "".join(
                f'<c r="{_column(c)}{r}" t="inlineStr">'
                + ("<f>1+1</f>" if formula and i == 1 and r == 2 and c == 1 else "")
                + f"<is><t>{escape(str(value))}</t></is></c>"
                for c, value in enumerate(vals, 1)
            )
            xmlrows.append(f'<row r="{r}">{cells}</row>')
        entries[f"xl/worksheets/sheet{i}.xml"] = (
            f'<worksheet xmlns="{NS}"><sheetData>{"".join(xmlrows)}</sheetData></worksheet>'
        )
    if entity:
        entries["xl/worksheets/sheet1.xml"] = (
            '<!DOCTYPE x [<!ENTITY a "secret">]>' + entries["xl/worksheets/sheet1.xml"]
        )
    if corrupt_shared:
        entries["xl/sharedStrings.xml"] = "not XML"
    if huge:
        entries["xl/worksheets/sheet1.xml"] = "x" * (5 * 1024 * 1024)
    path = tmp_path / "bank.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def test_reads_normalized_cases_and_preserves_original_evidence(tmp_path):
    path = _workbook(tmp_path)
    bank = load_bank(path)
    assert bank["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(bank["cases"]) == 2
    case = bank["cases"][0]
    assert case["case_id"] == "DEV-A01-01-V0"
    assert case["input"] == "Open import."
    assert case["expected_parameters"] == {}
    assert case["metadata"]["ground_truth"]["review_status"] == "待人工複核"
    assert case["metadata"]["ground_truth"]["source_sha"] == "old-evidence"
    assert case["metadata"]["human"]["版本"] == "Human original"
    fixture = bank["fixtures"][case["fixture_id"]]
    assert fixture["conditions"] == {"stage": "empty"}
    assert fixture["metadata"]["起始情境"] == "Empty workspace"


def test_dev_export_removes_review_status_without_changing_other_values(tmp_path):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    source = _workbook(tmp_path)
    original = source.read_bytes()
    expected = load_bank(source)
    exported = dev_bank_bytes(source)
    target = tmp_path / "exported.xlsx"
    target.write_bytes(exported)
    actual = load_bank(target)
    for case in expected["cases"]:
        case["metadata"]["ground_truth"].pop("review_status")
    assert actual["cases"] == expected["cases"]
    assert actual["fixtures"] == expected["fixtures"]
    assert actual["source"]["sheets"] == expected["source"]["sheets"]
    assert source.read_bytes() == original
    assert dev_bank_bytes(target) == exported
    assert (
        load_bank(source, drop_review_status=True)["source"]["sha256"]
        == actual["source"]["sha256"]
    )
    assert load_bank(source, drop_review_status=True)["cases"] == actual["cases"]


def test_dev_export_without_review_status_preserves_exact_bytes(tmp_path):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    rows = _rows()
    for row in rows["ground_truth"]:
        row.pop("review_status")
    source = _workbook(tmp_path, rows)
    assert dev_bank_bytes(source) == source.read_bytes()


def test_dev_export_validates_original_before_removing_a_column(tmp_path):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    source = _workbook(tmp_path, formula=True)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="formula"):
        dev_bank_bytes(source)
    assert source.read_bytes() == original


def test_dev_export_updates_excel_layout_and_keeps_other_sheets(tmp_path):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    source = _workbook(tmp_path)
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    name = "xl/worksheets/sheet3.xml"
    xml = (
        entries[name]
        .decode()
        .replace(
            "<sheetData>",
            '<dimension ref="A1:M3"/><cols>'
            '<col min="11" max="11" width="20"/>'
            '<col min="12" max="13" width="45"/></cols><sheetData>',
        )
        .replace(
            "</worksheet>",
            '<autoFilter ref="A1:M3"><filterColumn colId="10"/>'
            '<filterColumn colId="11"/></autoFilter>'
            '<dataValidations count="2">'
            '<dataValidation sqref="K2:K3"><formula1>"pending,done"</formula1></dataValidation>'
            '<dataValidation sqref="L2:L3"><formula1>"old-evidence"</formula1></dataValidation>'
            "</dataValidations></worksheet>",
        )
        .replace(
            f'xmlns="{NS}"',
            f'xmlns="{NS}" xmlns:mc="urn:mc" xmlns:xr="urn:revision" mc:Ignorable="xr"',
        )
    )
    entries[name] = xml.encode()
    with zipfile.ZipFile(source, "w") as archive:
        for member, content in entries.items():
            archive.writestr(member, content)
    exported = dev_bank_bytes(source)
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        for member, content in entries.items():
            if member != name:
                assert archive.read(member) == content
        result = ET.fromstring(archive.read(name))  # noqa: S314 - generated test fixture
        assert b'xmlns:xr="urn:revision"' in archive.read(name)
    ns = "{" + NS + "}"
    assert result.find(ns + "dimension").get("ref") == "A1:L3"
    columns = result.find(ns + "cols")
    assert len(columns) == 1
    assert columns[0].attrib == {"min": "11", "max": "12", "width": "45"}
    filters = result.find(ns + "autoFilter")
    assert filters.get("ref") == "A1:L3"
    assert [c.get("colId") for c in filters] == ["10"]
    validation = result.find(ns + "dataValidations")
    assert validation.get("count") == "1"
    assert validation[0].get("sqref") == "K2:K3"


@pytest.mark.parametrize("formula", ["L2", "'ground_truth'!L2:L3"])
def test_dev_export_rejects_surviving_validation_formula_references(tmp_path, formula):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    source = _workbook(tmp_path)
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    name = "xl/worksheets/sheet3.xml"
    entries[name] = entries[name].replace(
        b"</worksheet>",
        (
            '<dataValidations count="1"><dataValidation sqref="L2:L3">'
            f"<formula1>{formula}</formula1></dataValidation></dataValidations></worksheet>"
        ).encode(),
    )
    with zipfile.ZipFile(source, "w") as archive:
        for member, content in entries.items():
            archive.writestr(member, content)
    with pytest.raises(ValueError, match="validation formula"):
        dev_bank_bytes(source)


def test_dev_export_removes_filter_on_deleted_column(tmp_path):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    source = _workbook(tmp_path)
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    name = "xl/worksheets/sheet3.xml"
    entries[name] = entries[name].replace(
        b"</worksheet>", b'<autoFilter ref="K1:K3"/></worksheet>'
    )
    with zipfile.ZipFile(source, "w") as archive:
        for member, content in entries.items():
            archive.writestr(member, content)
    with zipfile.ZipFile(io.BytesIO(dev_bank_bytes(source))) as archive:
        result = ET.fromstring(archive.read(name))  # noqa: S314 - generated test fixture
        assert result.find("{" + NS + "}autoFilter") is None


@pytest.mark.parametrize("position", [0, 5, 12])
def test_dev_export_locates_review_column_by_header_not_fixed_letter(
    tmp_path, position
):
    from scripts.dev.assistant_pilot_bank import dev_bank_bytes

    rows = _rows()
    for i, row in enumerate(rows["ground_truth"]):
        status = row.pop("review_status")
        pairs = list(row.items())
        pairs.insert(position, ("review_status", status))
        rows["ground_truth"][i] = dict(pairs)
    source = _workbook(tmp_path, rows)
    exported = tmp_path / "exported.xlsx"
    exported.write_bytes(dev_bank_bytes(source))
    assert (
        load_bank(exported)["cases"]
        == load_bank(source, drop_review_status=True)["cases"]
    )


@pytest.mark.parametrize("decision", ["Clarification", "No-call"])
def test_free_text_nonaction_parameters_are_not_parsed_as_json(tmp_path, decision):
    rows = _rows()
    truth = rows["ground_truth"][0]
    truth.update(
        decision=decision,
        expected_tool="respond_to_user",
        expected_parameters_json="N/A: message is free text; use parameter_rule",
    )
    case = load_bank(_workbook(tmp_path, rows))["cases"][0]
    assert case["expected_parameters"] is None
    assert case["decision"] == decision


@pytest.mark.parametrize(
    "field,value",
    [
        ("split", "TEST"),
        ("split", "OTHER"),
        ("family_id", "VALID-A01-01"),
        ("fixture_id", "missing"),
        ("expected_workflow_stage", "trained"),
        ("decision", "Other"),
        ("expected_tool", ""),
        ("expected_parameters_json", '{"x":NaN}'),
        ("expected_parameters_json", '{"x":1,"x":2}'),
        ("expected_parameters_json", '{"x":1e999}'),
        ("expected_parameters_json", "[]"),
        ("missing_fields_json", "{}"),
        ("explicit_info_json", "[]"),
    ],
)
def test_rejects_invalid_or_mismatched_oracles(tmp_path, field, value):
    rows = _rows()
    rows["ground_truth"][0][field] = value
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


@pytest.mark.parametrize("sheet", ["DEV", "ground_truth", "情境定義"])
def test_rejects_duplicate_ids(tmp_path, sheet):
    rows = _rows()
    rows[sheet].append(rows[sheet][0].copy())
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


def test_rejects_missing_truth(tmp_path):
    rows = _rows()
    rows["ground_truth"].pop()
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


def test_rejects_cross_split_family_even_when_references_match(tmp_path):
    rows = _rows()
    rows["VALID"][0]["Family"] = rows["DEV"][0]["Family"]
    rows["ground_truth"][1]["family_id"] = rows["DEV"][0]["Family"]
    rows["情境定義"][1]["family_id"] = rows["DEV"][0]["Family"]
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


@pytest.mark.parametrize("sheet_name", ["TEST", "sealed_test", "OTHER"])
def test_rejects_sheet_metadata_before_reading_shared_question_content(
    tmp_path, sheet_name
):
    path = _workbook(tmp_path, sheet_name=sheet_name, corrupt_shared=True)
    with pytest.raises(ValueError, match="sheet"):
        load_bank(path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target": "../../secret.xml"},
        {"target": "https://example.com/a"},
        {"target": "/xl/worksheets/sheet1.xml"},
        {"formula": True},
        {"entity": True},
        {"huge": True},
    ],
)
def test_rejects_unsafe_archive_or_selected_cells(tmp_path, kwargs):
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, **kwargs))


def test_rejects_invalid_fixture_json(tmp_path):
    rows = _rows()
    rows["情境定義"][0]["結構化條件_JSON"] = '{"x":1,"x":2}'
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


def _replace_member(path, name, content):
    with zipfile.ZipFile(path) as archive:
        members = {
            item.filename: archive.read(item.filename) for item in archive.infolist()
        }
    members[name] = content
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, value in members.items():
            archive.writestr(member, value)


@pytest.mark.parametrize(
    "replacement",
    [
        '<worksheet><!ENTITY a "secret"></worksheet>',
        '<!DOCTYPE x [<!ENTITY a "secret">]><worksheet/>'.encode("utf-16"),
    ],
)
def test_rejects_entity_encoding_variants(tmp_path, replacement):
    path = _workbook(tmp_path)
    _replace_member(path, "xl/worksheets/sheet1.xml", replacement)
    with pytest.raises(ValueError):
        load_bank(path)


def test_shared_strings_and_sparse_cells(tmp_path):
    path = _workbook(tmp_path)
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml").decode()
    xml = xml.replace(
        '<c r="C2" t="inlineStr"><is><t>Open import.</t></is></c>',
        '<c r="C2" t="s"><v>0</v></c>',
    )
    xml = xml.replace('<c r="F2" t="inlineStr"><is><t>Human original</t></is></c>', "")
    _replace_member(path, "xl/worksheets/sheet1.xml", xml)
    _replace_member(
        path,
        "xl/sharedStrings.xml",
        f'<sst xmlns="{NS}"><si><r><t>Open </t></r><r><t>import.</t></r></si></sst>',
    )
    case = load_bank(path)["cases"][0]
    assert case["input"] == "Open import."
    assert case["metadata"]["human"]["版本"] == ""


def test_rejects_duplicate_archive_members(tmp_path):
    path = _workbook(tmp_path)
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(path, "a") as archive,
    ):
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(ValueError, match="duplicate"):
        load_bank(path)


def test_rejects_conflicting_human_fixture_and_empty_input(tmp_path):
    rows = _rows()
    rows["DEV"][0]["英文題目"] = " "
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))
    rows = _rows()
    rows["DEV"][0]["情境編號"] = "FX-VALID-A01-01"
    with pytest.raises(ValueError):
        load_bank(_workbook(tmp_path, rows))


def _selection_bank():
    cases = []
    for category, count, decision in (
        ("A", 18, "Action"),
        ("C", 6, "Clarification"),
        ("N", 3, "No-call"),
    ):
        for number in range(1, count + 1):
            for family_number in (1, 2, 3):
                family = f"DEV-{category}{number:02}-{family_number:02}"
                for variant, text in (
                    (0, "short"),
                    (1, "longer input"),
                    (2, "same length!"),
                ):
                    cases.append(
                        {
                            "case_id": f"{family}-V{variant}",
                            "family_id": family,
                            "split": "DEV",
                            "input": text,
                            "decision": decision,
                            "expected_tool": f"tool_{number}"
                            if category == "A"
                            else "respond_to_user",
                        }
                    )
    cases.append(
        {"case_id": "VALID-A01-01-V0", "family_id": "VALID-A01-01", "split": "VALID"}
    )
    return {"schema": SCHEMA, "source": {"sha256": "a" * 64}, "cases": cases}


def test_selection_is_stable_quota_bound_and_contains_ids_only():
    bank = _selection_bank()
    original = deepcopy(bank)
    selection = build_pilot_selection(bank)
    assert bank == original
    assert len(selection["case_ids"]) == 30
    assert (
        len({identifier.rsplit("-", 1)[0] for identifier in selection["case_ids"]})
        == 30
    )
    assert all(
        identifier.startswith("DEV-") and identifier.endswith("-V1")
        for identifier in selection["case_ids"]
    )
    assert selection["phase_one_case_ids"] == [
        "DEV-A05-01-V1",
        "DEV-A08-01-V1",
        "DEV-C01-01-V1",
        "DEV-C02-01-V1",
        "DEV-N02-01-V1",
        "DEV-N03-01-V1",
    ]
    assert len(selection["phase_two_case_ids"]) == 24
    assert set(selection["phase_one_case_ids"]).isdisjoint(
        selection["phase_two_case_ids"]
    )
    assert set(
        selection["phase_one_case_ids"] + selection["phase_two_case_ids"]
    ) == set(selection["case_ids"])
    assert set(selection) == {
        "schema",
        "source_sha256",
        "selection_rule",
        "case_ids",
        "phase_one_case_ids",
        "phase_two_case_ids",
    }
    bank["cases"].reverse()
    assert build_pilot_selection(bank) == selection
    bank["source"]["sha256"] = "b" * 64
    assert build_pilot_selection(bank)["source_sha256"] == "b" * 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_id", "TEST-A01-01-V0"),
        ("family_id", "DEV-A02-01"),
        ("split", "TEST"),
        ("decision", "No-call"),
        ("input", " "),
        ("expected_tool", ""),
    ],
)
def test_selection_rejects_invalid_dev_identity_or_contract(field, value):
    bank = _selection_bank()
    bank["cases"][0][field] = value
    with pytest.raises(ValueError):
        build_pilot_selection(bank)


def test_selection_rejects_missing_group_duplicate_id_and_tool():
    bank = _selection_bank()
    bank["cases"] = [
        case for case in bank["cases"] if not case["case_id"].startswith("DEV-C06")
    ]
    with pytest.raises(ValueError):
        build_pilot_selection(bank)
    bank = _selection_bank()
    bank["cases"].append(bank["cases"][0].copy())
    with pytest.raises(ValueError):
        build_pilot_selection(bank)
    bank = _selection_bank()
    for case in bank["cases"]:
        if case["case_id"].startswith("DEV-A02"):
            case["expected_tool"] = "tool_1"
    with pytest.raises(ValueError):
        build_pilot_selection(bank)


def test_selection_rejects_insufficient_no_call_families():
    bank = _selection_bank()
    bank["cases"] = [
        case
        for case in bank["cases"]
        if not case["case_id"].startswith(("DEV-N03-02", "DEV-N03-03"))
    ]
    with pytest.raises(ValueError):
        build_pilot_selection(bank)


def test_selection_uses_available_family_order_not_fixed_question_ids():
    bank = _selection_bank()
    bank["cases"] = [
        case for case in bank["cases"] if case["family_id"] != "DEV-A05-01"
    ]
    result = build_pilot_selection(bank)
    assert result["phase_one_case_ids"][0] == "DEV-A05-02-V1"
    assert "DEV-A05-01-V1" not in result["case_ids"]


def test_selection_rejects_invalid_source_hash():
    bank = _selection_bank()
    bank["source"]["sha256"] = "not-a-hash"
    with pytest.raises(ValueError):
        build_pilot_selection(bank)
