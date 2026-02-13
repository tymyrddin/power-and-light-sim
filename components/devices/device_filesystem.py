# components/devices/device_filesystem.py
"""
Lightweight filesystem simulation for devices.

Not a real filesystem. A dict of paths to file entries that supports
directory listing, file reading, and content searching. Devices populate
their filesystem in __init__ with realistic artefacts.

Windows devices get case-insensitive path matching.
Some files are dynamic (updated during simulation, e.g. log files).
"""

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileEntry:
    """A single file in the simulated filesystem."""

    contents: str
    modified: str = "1998-01-15"
    size: int | None = None  # Auto-calculated from contents if None
    file_type: str = "file"  # 'file' or 'directory'
    security_relevant: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.size is None and self.file_type == "file":
            self.size = len(self.contents.encode("utf-8"))


class DeviceFilesystem:
    """
    Simulated filesystem for a device.

    Provides directory listing, file reading, and content searching.
    Paths are stored normalised (forward slashes). Case sensitivity
    is configurable (Windows devices use case-insensitive).

    Example:
        >>> fs = DeviceFilesystem(case_sensitive=False)
        >>> fs.add_file("C:/TURBINE/config.ini", "[TurbineLink]\\nServer=10.10.1.10")
        >>> fs.read_file("c:/turbine/CONFIG.INI")
        '[TurbineLink]\\nServer=10.10.1.10'
    """

    def __init__(self, case_sensitive: bool = True) -> None:
        self.case_sensitive = case_sensitive
        self._files: dict[str, FileEntry] = {}

    @staticmethod
    def _normalise_path(path: str) -> str:
        """Normalise path separators to forward slashes, strip trailing slash."""
        path = path.replace("\\", "/")
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def _lookup_key(self, path: str) -> str:
        """Get the lookup key for a path (lowered if case-insensitive)."""
        path = self._normalise_path(path)
        if not self.case_sensitive:
            return path.lower()
        return path

    def _store_key(self, path: str) -> tuple[str, str]:
        """Return (lookup_key, display_path) for storage."""
        normalised = self._normalise_path(path)
        lookup = normalised.lower() if not self.case_sensitive else normalised
        return lookup, normalised

    def add_file(
        self,
        path: str,
        contents: str,
        modified: str = "1998-01-15",
        security_relevant: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a file to the filesystem."""
        lookup, display = self._store_key(path)
        self._files[lookup] = FileEntry(
            contents=contents,
            modified=modified,
            security_relevant=security_relevant,
            metadata=metadata or {},
        )
        # Store display path in metadata for case-insensitive retrieval
        self._files[lookup].metadata["_display_path"] = display

        # Ensure parent directories exist
        self._ensure_parents(display)

    def add_directory(
        self,
        path: str,
        modified: str = "1998-01-15",
    ) -> None:
        """Add a directory to the filesystem."""
        lookup, display = self._store_key(path)
        self._files[lookup] = FileEntry(
            contents="",
            modified=modified,
            file_type="directory",
            metadata={"_display_path": display},
        )

    def _ensure_parents(self, path: str) -> None:
        """Create parent directories if they don't exist."""
        parts = self._normalise_path(path).split("/")
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i])
            if not parent:
                continue
            parent_key = parent.lower() if not self.case_sensitive else parent
            if parent_key not in self._files:
                self._files[parent_key] = FileEntry(
                    contents="",
                    file_type="directory",
                    metadata={"_display_path": parent},
                )

    def read_file(self, path: str) -> str | None:
        """Read file contents. Returns None if not found."""
        key = self._lookup_key(path)
        entry = self._files.get(key)
        if entry and entry.file_type == "file":
            return entry.contents
        return None

    def get_entry(self, path: str) -> FileEntry | None:
        """Get the full FileEntry for a path."""
        key = self._lookup_key(path)
        return self._files.get(key)

    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        return self._lookup_key(path) in self._files

    def is_directory(self, path: str) -> bool:
        """Check if a path is a directory."""
        entry = self.get_entry(path)
        return entry is not None and entry.file_type == "directory"

    def list_dir(self, path: str) -> list[dict[str, Any]]:
        """
        List contents of a directory.

        Returns list of dicts with name, type, size, modified.
        Returns empty list if path is not a directory or doesn't exist.
        """
        norm_path = self._normalise_path(path)
        lookup_path = norm_path.lower() if not self.case_sensitive else norm_path

        results = []
        seen = set()

        for key, entry in self._files.items():
            display = entry.metadata.get("_display_path", key)
            compare_display = display.lower() if not self.case_sensitive else display
            compare_parent = lookup_path

            # Check if this entry is a direct child of the target path
            if not compare_display.startswith(compare_parent + "/"):
                continue

            # Get the relative part after the parent path
            relative = display[len(norm_path) + 1 :]

            # Direct child has no further slashes
            if "/" in relative:
                # This is a deeper entry - extract the immediate subdirectory name
                subdir_name = relative.split("/")[0]
                subdir_key = subdir_name.lower() if not self.case_sensitive else subdir_name
                if subdir_key not in seen:
                    seen.add(subdir_key)
                    # Look up the subdirectory entry
                    subdir_path = f"{norm_path}/{subdir_name}"
                    subdir_lookup = subdir_path.lower() if not self.case_sensitive else subdir_path
                    subdir_entry = self._files.get(subdir_lookup)
                    results.append({
                        "name": subdir_name,
                        "type": "directory",
                        "size": 0,
                        "modified": subdir_entry.modified if subdir_entry else "",
                    })
            else:
                name = relative
                name_key = name.lower() if not self.case_sensitive else name
                if name_key not in seen:
                    seen.add(name_key)
                    results.append({
                        "name": name,
                        "type": entry.file_type,
                        "size": entry.size or 0,
                        "modified": entry.modified,
                    })

        # Sort: directories first, then alphabetical
        results.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"]))
        return results

    def search_contents(self, pattern: str) -> list[dict[str, str]]:
        """
        Search file contents for a pattern (case-insensitive regex).

        Returns list of dicts with path, line, match.
        """
        results = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return results

        for _key, entry in self._files.items():
            if entry.file_type != "file" or not entry.contents:
                continue
            display = entry.metadata.get("_display_path", _key)
            for i, line in enumerate(entry.contents.splitlines(), 1):
                if regex.search(line):
                    results.append({
                        "path": display,
                        "line_number": str(i),
                        "line": line.strip(),
                    })
        return results

    def find_files(self, pattern: str) -> list[str]:
        """
        Find files matching a glob pattern.

        Returns list of matching paths.
        """
        results = []
        for _key, entry in self._files.items():
            if entry.file_type != "file":
                continue
            display = entry.metadata.get("_display_path", _key)
            name = display.rsplit("/", 1)[-1] if "/" in display else display
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                results.append(display)
        return sorted(results)

    def get_security_relevant_files(self) -> list[str]:
        """Return paths of all security-relevant files."""
        results = []
        for _key, entry in self._files.items():
            if entry.security_relevant:
                display = entry.metadata.get("_display_path", _key)
                results.append(display)
        return sorted(results)

    def append_to_file(self, path: str, content: str) -> bool:
        """Append content to an existing file. Returns False if not found."""
        key = self._lookup_key(path)
        entry = self._files.get(key)
        if entry and entry.file_type == "file":
            entry.contents += content
            entry.size = len(entry.contents.encode("utf-8"))
            return True
        return False