"""Shared fixtures: a synthetic CompuTax tree that reproduces the real data's quirks."""

import json
from pathlib import Path

import pytest


def filed_json(form: str, name: dict, org: bool = False) -> dict:
    """Return a minimal FiledJson document with ``AssesseeName`` where ``form`` puts it."""
    if form in ("ITR1", "ITR4"):
        body = {"PersonalInfo": {"AssesseeName": name, "PAN": "XXXXX0000X"}}
    else:
        section = "OrgFirmInfo" if org else "PersonalInfo"
        body = {"PartA_GEN1": {section: {"AssesseeName": name}}}
    return {"ITR": {form: {f"Form_{form}": {"AssessmentYear": "2024"}, **body}}}


def write(path: Path, content: str | bytes = b"%PDF-1.4 test") -> Path:
    """Create ``path`` (and its parents) with ``content``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


@pytest.fixture
def computax(tmp_path: Path) -> Path:
    """Build a fake CompuTax folder covering every quirk seen in the real data."""
    root = tmp_path / "CompuTax"
    # Plain client across years; name changes between 2021 and 2024.
    for year in (2020, 2021, 2024):
        write(root / f"{year}/1/ITRV_1.pdf")
        write(root / f"{year}/1/Computation_1_{year}_1.pdf")
        write(root / f"{year}/1/ComputationCompare_{year}_1.pdf")
        write(root / f"{year}/1/1_{year}_TIS.pdf_")
    write(root / "2021/1/FiledJson_1_1.json", json.dumps(filed_json("ITR1", {"FirstName": "ASHA", "SurNameOrOrgName": "VERMA"})))
    write(root / "2024/1/FiledJson_1_1.json", json.dumps(filed_json("ITR3", {"FirstName": "OLD", "SurNameOrOrgName": "NAME"})))
    write(root / "2024/1/FiledJson_1_2.json", json.dumps(filed_json("ITR3", {"FirstName": "ASHA", "MiddleName": " ", "SurNameOrOrgName": "SHARMA"})))
    # Mixed-case folder and filenames across years, revised ITRV, multiple computations.
    write(root / "2020/7d/ITRV_7D.pdf")
    write(root / "2020/7d/Computation_7D_2020_1.pdf")
    write(root / "2022/7D/ITRV_7D.pdf")
    write(root / "2022/7D/ITRV_7D_Revised.pdf")
    write(root / "2022/7D/Computation_7D_2022_1.pdf")
    write(root / "2022/7D/Computation_7D_2022_10.pdf")
    write(root / "2022/7D/Computation_7D_2022_2.pdf")
    write(root / "2023/7D/7D_2023_26AS.pdf")
    # A firm (ITR-5), BOM-prefixed JSON.
    write(root / "2022/42/ITRV_42.pdf")
    firm = json.dumps(filed_json("ITR5", {"SurNameOrOrgName": "SHARMA  TRADERS"}, org=True))
    write(root / "2022/42/FiledJson_42_1.json", "﻿" + firm)
    # Misfiled folder: 264B holds client 274's files in 2021.
    write(root / "2021/264B/ITRV_274.pdf")
    write(root / "2021/264B/Computation_274_2021_1.pdf")
    write(root / "2021/264B/FiledJson_274_1.json", json.dumps(filed_json("ITR1", {"FirstName": "WRONG", "SurNameOrOrgName": "PERSON"})))
    write(root / "2022/264B/ITRV_264B.pdf")
    # Malformed JSON and a file that is not in any year folder.
    write(root / "2022/99/FiledJson_99_1.json", "{not json")
    write(root / "notes.txt", "ignore me")
    (root / "misc").mkdir()
    (root / "2012" / "EMPTY").mkdir(parents=True)
    return root
