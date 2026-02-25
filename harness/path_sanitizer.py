"""
Path sanitizer: strip local paths, usernames, and computer names from logs
before saving to disk (privacy / reproducibility).
"""
import re
import os
import platform
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class PathSanitizer:
    """Remove identifying path information from strings."""

    def __init__(self, workspace_root: Path = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.computer_name = platform.node()
        self.username = os.environ.get('USERNAME') or os.environ.get('USER')
        self.home_dir = str(Path.home())
        self._build_rules()

    def _build_rules(self):
        self.rules = []

        if self.computer_name:
            self.rules.append((re.compile(re.escape(self.computer_name), re.IGNORECASE), '<COMPUTER>'))

        if self.username:
            self.rules.append((re.compile(re.escape(self.username), re.IGNORECASE), '<USER>'))

        if self.home_dir:
            self.rules.append((re.compile(re.escape(self.home_dir), re.IGNORECASE), '<HOME>'))
            self.rules.append((re.compile(re.escape(self.home_dir.replace('\\', '/')), re.IGNORECASE), '<HOME>'))

        ws = str(self.workspace_root)
        if ws:
            self.rules.append((re.compile(re.escape(ws), re.IGNORECASE), '<WORKSPACE>'))
            self.rules.append((re.compile(re.escape(ws.replace('\\', '/')), re.IGNORECASE), '<WORKSPACE>'))

        self.rules.append((re.compile(r'[A-Za-z]:\\[^\\:\*\?"<>\|]+', re.IGNORECASE), self._replace_windows_path))
        self.rules.append((re.compile(r'/(?:home|Users)/[^/\s]+', re.IGNORECASE), '<HOME>'))
        self.rules.append((re.compile(r'file:///[^\s]+', re.IGNORECASE), 'file:///<REDACTED>'))

    def _replace_windows_path(self, match):
        return f"{match.group(0)[0]}:/<REDACTED>"

    def sanitize(self, text: str) -> str:
        if not text:
            return text
        result = text
        for pattern, replacement in self.rules:
            result = pattern.sub(replacement if not callable(replacement) else replacement, result)
        return result

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize all string values in a dict."""
        if not isinstance(data, dict):
            return data
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [self.sanitize(v) if isinstance(v, str) else v for v in value]
            else:
                result[key] = value
        return result

    def sanitize_path(self, path: Path) -> str:
        """Convert to workspace-relative path or sanitize."""
        try:
            return str(path.relative_to(self.workspace_root)).replace('\\', '/')
        except ValueError:
            return self.sanitize(str(path))


class SanitizedLogger:
    """Wrapper around Python logger that sanitizes messages before writing."""

    def __init__(self, logger_name: str, sanitizer: PathSanitizer = None):
        self.logger = logging.getLogger(logger_name)
        self.sanitizer = sanitizer or PathSanitizer()

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(self.sanitizer.sanitize(msg), *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(self.sanitizer.sanitize(msg), *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self.logger.error(self.sanitizer.sanitize(msg), *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(self.sanitizer.sanitize(msg), *args, **kwargs)
