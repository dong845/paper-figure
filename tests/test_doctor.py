import subprocess
import sys

from paperfig import doctor


def test_doctor_reports_each_requirement():
    rep = doctor.check()
    names = {r["name"] for r in rep}
    assert {"python", "Pillow", "jsonschema", "pdftotext", "pdftoppm", "pdfinfo", "draw.io"} <= names
    for r in rep:
        assert isinstance(r["ok"], bool) and r["detail"]


def test_doctor_flags_missing_tool(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    rep = {r["name"]: r for r in doctor.check()}
    assert not rep["pdftotext"]["ok"] and "poppler" in rep["pdftotext"]["detail"]


def test_doctor_cli_exit_code():
    r = subprocess.run([sys.executable, "-m", "paperfig", "doctor"], capture_output=True, text=True)
    assert r.returncode in (0, 1) and "draw.io" in r.stdout
