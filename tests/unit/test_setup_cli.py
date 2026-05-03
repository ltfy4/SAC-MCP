"""Unit tests for the interactive setup CLI."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sac_mcp.setup_cli import _check_region_match, _extract_region, main


class TestRegionExtraction:
    def test_extracts_eu10(self) -> None:
        assert _extract_region("https://company.eu10.hcs.cloud.sap") == "eu10"

    def test_extracts_us10(self) -> None:
        assert _extract_region("https://company.authentication.us10.hana.ondemand.com") == "us10"

    def test_returns_none_for_no_region(self) -> None:
        assert _extract_region("https://example.com") is None


class TestRegionMismatchWarning:
    def test_warns_on_mismatch(self, capsys: pytest.CaptureFixture[str]) -> None:
        _check_region_match(
            "https://company.eu10.hcs.cloud.sap",
            "https://company.authentication.us10.hana.ondemand.com",
        )
        captured = capsys.readouterr()
        assert "Region mismatch" in captured.err
        assert "eu10" in captured.err
        assert "us10" in captured.err

    def test_no_warning_when_matching(self, capsys: pytest.CaptureFixture[str]) -> None:
        _check_region_match(
            "https://company.eu10.hcs.cloud.sap",
            "https://company.authentication.eu10.hana.ondemand.com",
        )
        captured = capsys.readouterr()
        assert "Region mismatch" not in captured.err


class TestEnvFileWritten:
    def test_writes_env_with_expected_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        user_input = io.StringIO(
            "https://company.eu10.hcs.cloud.sap\n"
            "https://company.authentication.eu10.hana.ondemand.com\n"
            "my-client-id\n"
            "my-secret\n"
            "\n"  # oauth scope (skip)
            "stdio\n"  # transport
        )
        main(_input=user_input)

        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        assert "SAC_TENANT_URL=https://company.eu10.hcs.cloud.sap" in content
        assert "SAC_AUTH_URL=https://company.authentication.eu10.hana.ondemand.com" in content
        assert "SAC_CLIENT_ID=my-client-id" in content
        assert "SAC_CLIENT_SECRET=my-secret" in content

    def test_existing_env_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / ".env"
        existing.write_text("EXISTING=keep\n")

        user_input = io.StringIO(
            "https://company.eu10.hcs.cloud.sap\n"
            "https://company.authentication.eu10.hana.ondemand.com\n"
            "cid\n"
            "secret\n"
            "\n"
            "stdio\n"
        )
        main(_input=user_input)

        assert existing.read_text() == "EXISTING=keep\n"
        generated = tmp_path / ".env.generated"
        assert generated.exists()
        assert "SAC_TENANT_URL" in generated.read_text()


class TestClaudeDesktopSnippet:
    def test_snippet_is_valid_json_with_required_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        user_input = io.StringIO(
            "https://company.eu10.hcs.cloud.sap\n"
            "https://company.authentication.eu10.hana.ondemand.com\n"
            "my-client-id\n"
            "my-secret\n"
            "\n"
            "stdio\n"
        )
        main(_input=user_input)

        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{"))
        json_end = next(
            i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("}")
        )
        json_text = "\n".join(lines[json_start : json_end + 1])
        parsed = json.loads(json_text)

        assert "mcpServers" in parsed
        sac_env = parsed["mcpServers"]["sac"]["env"]
        assert "SAC_TENANT_URL" in sac_env
        assert "SAC_AUTH_URL" in sac_env
        assert "SAC_CLIENT_ID" in sac_env
        assert "SAC_CLIENT_SECRET" in sac_env


class TestHttpTransport:
    def test_http_transport_generates_bearer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        user_input = io.StringIO(
            "https://company.eu10.hcs.cloud.sap\n"
            "https://company.authentication.eu10.hana.ondemand.com\n"
            "cid\n"
            "secret\n"
            "\n"
            "http\n"
            "0.0.0.0\n"
            "9090\n"
        )
        main(_input=user_input)

        content = (tmp_path / ".env").read_text()
        assert "MCP_TRANSPORT=http" in content
        assert "MCP_HTTP_HOST=0.0.0.0" in content
        assert "MCP_HTTP_PORT=9090" in content
        assert "MCP_HTTP_BEARER=" in content
        bearer_line = next(x for x in content.split("\n") if x.startswith("MCP_HTTP_BEARER="))
        assert len(bearer_line.split("=")[1]) == 64
