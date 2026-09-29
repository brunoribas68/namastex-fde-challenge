import io
from contextlib import redirect_stdout
from datetime import date

from autoseguro import cli
from autoseguro.bootstrap import build_agent
from autoseguro.config import Settings
from autoseguro.extractor import LLMExtractor, RegexExtractor


def test_settings_from_env_casts_and_defaults():
    s = Settings.from_env({"QUOTE_MAX_ATTEMPTS": "7", "QUOTE_TIMEOUT_S": "1.5", "TRACE_FILE": "-"})
    assert (s.quote_max_attempts, s.quote_timeout_s, s.trace_file) == (7, 1.5, "-")
    assert Settings.from_env({}).quote_api_url == "http://localhost:8000"


def test_build_agent_picks_extractor_by_api_key(tmp_path):
    trace = str(tmp_path / "logs" / "t.jsonl")
    plain = build_agent(Settings(trace_file=trace))
    with_llm = build_agent(Settings(trace_file=trace, anthropic_api_key="k"))
    assert isinstance(plain.extractor, RegexExtractor)
    assert isinstance(with_llm.extractor, LLMExtractor)
    assert (tmp_path / "logs").is_dir()


def test_build_agent_can_log_to_stdout():
    assert build_agent(Settings(trace_file="-")).tracer is not None


def test_demo_script_ends_with_future_start_date():
    script = cli.demo_script(date(2026, 7, 1))
    assert "08/07/2026" in script[-1] and len(script) == 3


def test_cli_demo_runs(monkeypatch, make_agent):
    agent, _ = make_agent()
    monkeypatch.setattr(cli, "build_agent", lambda _settings: agent)
    monkeypatch.setattr("sys.argv", ["cli", "--demo"])
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main()
    assert "stage=quoted" in out.getvalue()
