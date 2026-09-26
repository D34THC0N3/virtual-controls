import io
from contextlib import redirect_stdout

from vctrl.__main__ import main


def test_no_command_prints_help(capsys):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([])
    captured = capsys.readouterr()
    out = buf.getvalue() + captured.out
    assert rc == 0
    assert "usage" in out


def test_unimplemented_command_returns_2(capsys):
    rc = main(["run"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "not implemented" in out
