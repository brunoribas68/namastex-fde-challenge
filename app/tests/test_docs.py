"""Guarda de documentação: código novo sem doc correspondente quebra o CI."""

from pathlib import Path

from autoseguro.config import ENV_VARS
from autoseguro.models import HandoffReason
from autoseguro.policy import HANDOFF_RULES

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DECISIONS = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")


def test_every_env_var_is_in_readme():
    assert [v for v in ENV_VARS if v not in README] == []


def test_every_handoff_reason_is_documented():
    assert [r.value for r in HandoffReason if r.value not in DECISIONS] == []


def test_every_handoff_reason_has_a_rule():
    assert set(HANDOFF_RULES) == set(HandoffReason)
