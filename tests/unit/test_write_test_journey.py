"""The required journey argument on write_test.  python -m pytest tests/unit"""

import pytest

from agent import tools
from agent.harness import SCHEMAS_BY_NAME, validate_args

SCHEMA = SCHEMAS_BY_NAME["write_test"]
CODE = "def test_x():\n    assert True\n"


def test_harness_requires_a_journey_from_the_fixed_list():
    assert validate_args(SCHEMA, {"filename": "test_x.py", "code": CODE}) == "missing required argument(s): journey"
    assert "must be one of" in validate_args(SCHEMA, {"filename": "test_x.py", "code": CODE, "journey": "checkout"})
    for journey in tools.JOURNEY_KEYS:
        assert validate_args(SCHEMA, {"filename": "test_x.py", "code": CODE, "journey": journey}) is None


def test_tool_rejects_unknown_journey_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "GENERATED_TESTS_DIR", tmp_path)
    with pytest.raises(ValueError, match="journey must be one of"):
        tools.write_test("test_x.py", CODE, "checkout")
    assert not (tmp_path / "test_x.py").exists()
    monkeypatch.setattr(tools, "REPO_ROOT", tmp_path)
    assert tools.write_test("test_x.py", CODE, "download_pdf")["journey"] == "download_pdf"
