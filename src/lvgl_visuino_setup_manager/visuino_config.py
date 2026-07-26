from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


DIRECTORIES_PATTERN = re.compile(r"^(?P<indent>[ \t]*)directories\s*:\s*(?:#.*)?$")
USER_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)user\s*:\s*(?P<value>.*)$"
)
TOP_LEVEL_PATTERN = re.compile(r"^[^\s#][^:]*:")


class ConfigurationError(RuntimeError):
    """Raised when Visuino configuration cannot be read, written, or verified."""


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def encode_yaml_scalar(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ConfigurationError("Configuration paths cannot contain line breaks.")
    return json.dumps(value, ensure_ascii=False)


def decode_yaml_scalar(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith('"'):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ConfigurationError(f"Invalid quoted YAML path: {error}") from error
        if not isinstance(parsed, str):
            raise ConfigurationError("YAML directories.user must be a string.")
        return parsed
    if stripped.startswith("'") and stripped.endswith("'"):
        return stripped[1:-1].replace("''", "'")
    return stripped


def replace_directories_user(text: str, new_value: str) -> str:
    newline = _newline_for(text)
    had_final_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    directories_index: int | None = None
    directories_indent = ""

    for index, line in enumerate(lines):
        match = DIRECTORIES_PATTERN.match(line)
        if match and not match.group("indent"):
            directories_index = index
            directories_indent = match.group("indent")
            break

    encoded_value = encode_yaml_scalar(new_value)
    if directories_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["directories:", f"    user: {encoded_value}"])
    else:
        block_end = len(lines)
        for index in range(directories_index + 1, len(lines)):
            line = lines[index]
            if line.strip() and TOP_LEVEL_PATTERN.match(line):
                block_end = index
                break

        user_index: int | None = None
        user_indent = f"{directories_indent}    "
        for index in range(directories_index + 1, block_end):
            match = USER_PATTERN.match(lines[index])
            if match and len(match.group("indent")) > len(directories_indent):
                user_index = index
                user_indent = match.group("indent")
                break

        replacement = f"{user_indent}user: {encoded_value}"
        if user_index is None:
            lines.insert(block_end, replacement)
        else:
            lines[user_index] = replacement

    rendered = newline.join(lines)
    if had_final_newline or not text:
        rendered += newline
    return rendered


def read_directories_user(text: str) -> str:
    lines = text.splitlines()
    directories_index: int | None = None
    for index, line in enumerate(lines):
        match = DIRECTORIES_PATTERN.match(line)
        if match and not match.group("indent"):
            directories_index = index
            break
    if directories_index is None:
        raise ConfigurationError("arduino-cli.yaml has no top-level directories section.")

    for line in lines[directories_index + 1 :]:
        if line.strip() and TOP_LEVEL_PATTERN.match(line):
            break
        match = USER_PATTERN.match(line)
        if match and match.group("indent"):
            return decode_yaml_scalar(match.group("value"))
    raise ConfigurationError("arduino-cli.yaml has no directories.user value.")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_directories_user(path: Path, new_value: str) -> None:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ConfigurationError(f"Cannot read {path}: {error}") from error

    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as error:
        raise ConfigurationError(f"{path} is not valid UTF-8 YAML.") from error
    rendered = replace_directories_user(text, new_value)
    atomic_write_bytes(path, rendered.encode(encoding))


@dataclass(frozen=True)
class RegistryValue:
    value: str | None
    kind: int | None


class VisuinoRegistryBackend(Protocol):
    def read(self) -> RegistryValue:
        ...

    def write(self, value: str, kind: int | None = None) -> None:
        ...

    def restore(self, original: RegistryValue) -> None:
        ...


class WindowsVisuinoRegistry:
    KEY_PATH = r"Software\Mitov\Visuino.Pro"
    VALUE_NAME = "ArduinoLibraryPath"

    def __init__(self) -> None:
        if os.name != "nt":
            raise ConfigurationError("The Visuino registry adapter requires Windows.")

    @staticmethod
    def _module():
        import winreg

        return winreg

    def read(self) -> RegistryValue:
        winreg = self._module()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.KEY_PATH,
                0,
                winreg.KEY_QUERY_VALUE,
            ) as key:
                value, kind = winreg.QueryValueEx(key, self.VALUE_NAME)
        except OSError as error:
            raise ConfigurationError(
                f"Cannot read HKCU\\{self.KEY_PATH}\\{self.VALUE_NAME}: {error}"
            ) from error
        return RegistryValue(str(value), int(kind))

    def write(self, value: str, kind: int | None = None) -> None:
        winreg = self._module()
        value_kind = winreg.REG_EXPAND_SZ if kind is None else kind
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                self.KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, self.VALUE_NAME, 0, value_kind, value)
        except OSError as error:
            raise ConfigurationError(
                f"Cannot write HKCU\\{self.KEY_PATH}\\{self.VALUE_NAME}: {error}"
            ) from error

    def restore(self, original: RegistryValue) -> None:
        winreg = self._module()
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                self.KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if original.value is None:
                    try:
                        winreg.DeleteValue(key, self.VALUE_NAME)
                    except FileNotFoundError:
                        pass
                else:
                    kind = original.kind or winreg.REG_EXPAND_SZ
                    winreg.SetValueEx(key, self.VALUE_NAME, 0, kind, original.value)
        except OSError as error:
            raise ConfigurationError(
                f"Cannot restore HKCU\\{self.KEY_PATH}\\{self.VALUE_NAME}: {error}"
            ) from error
