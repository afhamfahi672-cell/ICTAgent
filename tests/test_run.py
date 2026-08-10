import os
import sys
from pathlib import Path

# run.py lives at the repo root, not inside the ictagent package — add the
# root to sys.path so it's importable as a plain module in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import load_dotenv  # noqa: E402


def test_load_dotenv_sets_unset_variables(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAZ", raising=False)

    load_dotenv(str(env_file))

    assert os.environ["FOO"] == "bar"
    assert os.environ["BAZ"] == "qux"


def test_load_dotenv_does_not_override_real_env_vars(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=from_file\n")
    monkeypatch.setenv("FOO", "from_real_env")

    load_dotenv(str(env_file))

    assert os.environ["FOO"] == "from_real_env"


def test_load_dotenv_skips_comments_and_blank_lines(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\n\nFOO=bar\n   \n# ICTAGENT_PHASE=autonomous (still a comment)\n")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("ICTAGENT_PHASE", raising=False)

    load_dotenv(str(env_file))

    assert os.environ["FOO"] == "bar"
    assert "ICTAGENT_PHASE" not in os.environ


def test_load_dotenv_strips_quotes():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text('QUOTED="hello world"\nSINGLE=\'single quoted\'\n')
        os.environ.pop("QUOTED", None)
        os.environ.pop("SINGLE", None)

        load_dotenv(str(env_file))

        assert os.environ["QUOTED"] == "hello world"
        assert os.environ["SINGLE"] == "single quoted"

        del os.environ["QUOTED"]
        del os.environ["SINGLE"]


def test_load_dotenv_missing_file_is_a_noop():
    load_dotenv("/nonexistent/path/.env")  # should not raise


def test_run_without_credentials_fails_with_a_friendly_message_not_a_traceback():
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OANDA_", "TWELVEDATA_", "ANTHROPIC_", "ICTAGENT_"))
    }

    result = subprocess.run(
        ["python3", "run.py"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "Twelve Data isn't set up yet" in result.stderr


def test_run_with_oanda_provider_without_credentials_fails_with_a_friendly_message():
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OANDA_", "TWELVEDATA_", "ANTHROPIC_", "ICTAGENT_"))
    }

    result = subprocess.run(
        ["python3", "run.py", "--provider", "oanda"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "OANDA isn't set up yet" in result.stderr
