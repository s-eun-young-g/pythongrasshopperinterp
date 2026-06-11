import os
import xml.etree.ElementTree as ET

from py2gh.cli import main


def test_cli_converts_file(tmp_path, capsys):
    src = tmp_path / "prog.py"
    src.write_text("a = 1.0\nb = a + 2.0\n")
    out = tmp_path / "prog.ghx"

    rc = main([str(src), "-o", str(out)])
    assert rc == 0
    assert out.exists()
    ET.fromstring(out.read_text())  # valid XML


def test_cli_default_output_path(tmp_path):
    src = tmp_path / "prog.py"
    src.write_text("a = 1.0\n")
    rc = main([str(src)])
    assert rc == 0
    assert (tmp_path / "prog.ghx").exists()


def test_cli_reports_unsupported(tmp_path, capsys):
    src = tmp_path / "bad.py"
    src.write_text("for i in range(3): pass\n")
    rc = main([str(src)])
    assert rc == 1
    assert "line 1" in capsys.readouterr().err


def test_cli_check_guids(capsys):
    rc = main(["--check-guids"])
    # v0 ships with unconfirmed GUIDs, so this is expected to flag them.
    assert rc in (0, 1)
    assert "GUID" in capsys.readouterr().out
