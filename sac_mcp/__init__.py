"""SAC-MCP: SAP Analytics Cloud Model Context Protocol server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sac-mcp")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+unknown"
