# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The ``x12-tidy-web`` command-line entry point."""

from __future__ import annotations

import pytest

from x12_tidy_web import cli


def test_default_port_is_8000_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    assert cli._default_port() == 8000


def test_default_port_follows_PORT_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "8080")
    assert cli._default_port() == 8080


@pytest.mark.parametrize("bad", ["", "abc", "80a0", "-1"])
def test_default_port_ignores_non_numeric_env(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("PORT", bad)
    assert cli._default_port() == 8000


def test_repair_subcommand_reports_and_sets_exit_code(tmp_path, capsys) -> None:
    edi = tmp_path / "broken.edi"
    edi.write_text(
        "Subject: x\r\n\r\n"
        "ISA*00*   *00*   *ZZ*ACME*ZZ*WIDGETCO*240101*1200*U*00401*000000001*0*P*:~"
        "GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~"
        "ST*850*0001~BEG*00*NE*PO123**20240101~SE*3*0001~GE*1*1~IEA*2*000000001~",
        encoding="latin-1",
    )
    code = cli.main(["repair", str(edi), "--format", "text"])
    out = capsys.readouterr().out
    assert code == 1  # residual findings remain (control-count mismatch)
    assert "EDI VALIDATION REPORT" in out
    assert "x12-tidy 0.1.0 (git " in out
