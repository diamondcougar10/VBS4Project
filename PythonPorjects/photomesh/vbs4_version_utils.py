import logging
import os
import shutil
from pathlib import Path
from typing import Optional

try:
    import win32api  # type: ignore
except Exception:  # pragma: no cover - best effort on non-Windows systems
    win32api = None  # type: ignore


def find_vbs4_dir_for_version(required_version: str = "24.2") -> Optional[str]:
    """Locate the VBS4 installation directory for the required version.

    The function searches recursively under several common root directories for
    a VBS4 install containing ``VBS4.exe``.  When possible, the executable's
    ``FileVersion`` metadata is inspected via ``win32api`` and installations
    whose version string starts with ``required_version`` are preferred.  If the
    version information is unavailable, directory names containing the required
    version string are used as a fallback.

    Args:
        required_version: Major.minor version string, default ``"24.2"``.

    Returns:
        The path to the directory containing ``VBS4.exe`` for the requested
        version, or ``None`` if it cannot be found.
    """
    roots = [
        r"C:\\BISIM\\VBS4",
        r"C:\\Builds\\VBS4",
        r"C:\\Builds",
        r"C:\\Bohemia Interactive Simulations",
    ]

    name_match = None

    for root in roots:
        if not os.path.isdir(root):
            logging.debug("Root not found: %s", root)
            continue
        for dirpath, _, filenames in os.walk(root):
            if "VBS4.exe" not in filenames:
                continue
            exe_path = os.path.join(dirpath, "VBS4.exe")
            version = None
            if win32api:
                try:
                    info = win32api.GetFileVersionInfo(exe_path, "\\")
                    # Attempt to read the first translation table entry
                    trans = win32api.VerQueryValue(info, r"\\VarFileInfo\\Translation")
                    if trans:
                        lang, codepage = trans[0]
                        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileVersion"
                        version_str = win32api.VerQueryValue(info, key)
                    else:  # Fallback to US-English
                        version_str = win32api.VerQueryValue(
                            info, r"\\StringFileInfo\\040904B0\\FileVersion"
                        )
                    version = str(version_str).split()[0]
                except Exception as exc:  # pragma: no cover - Windows-specific
                    logging.debug("Failed to read version for %s: %s", exe_path, exc)
            if version and version.startswith(required_version):
                logging.info("Found VBS4 %s at %s", version, dirpath)
                return dirpath
            if version is None and required_version in dirpath:
                # Remember first directory name match in case no versioned install exists
                name_match = name_match or dirpath

    if name_match:
        logging.info("Using directory name match for VBS4 %s: %s", required_version, name_match)
        return name_match

    logging.error("VBS4 version %s not found", required_version)
    return None


def update_realitymesh_settings(
    settings_path: str, vbs4_dir: str, required_version: str = "24.2"
) -> bool:
    """Update Reality Mesh system settings with the required VBS4 configuration.

    The function ensures the ``override_Path_VBS4`` and ``vbs4_version`` keys are
    present with the exact values required.  All unrelated lines are preserved
    and ordering is maintained.  The file is updated atomically and a backup is
    created before replacement.

    Args:
        settings_path: Path to ``RealityMeshSystemSettings.txt``.
        vbs4_dir: Directory containing the desired ``VBS4.exe``.
        required_version: Version string to record, default ``"24.2"``.

    Returns:
        ``True`` on success, ``False`` otherwise.
    """
    path = Path(settings_path)
    if not path.exists():
        logging.error("Settings file not found: %s", settings_path)
        return False

    try:
        original_text = path.read_text(encoding="utf-8")
        lines = original_text.splitlines()
        has_trailing_newline = original_text.endswith("\n")

        norm_dir = os.path.normpath(vbs4_dir).replace("/", "\\")

        new_lines = []
        found_path = False
        found_version = False
        for line in lines:
            if line.startswith("override_Path_VBS4="):
                new_lines.append(f"override_Path_VBS4={norm_dir}")
                found_path = True
            elif line.startswith("vbs4_version="):
                new_lines.append(f"vbs4_version={required_version}")
                found_version = True
            else:
                new_lines.append(line)

        if not found_path:
            new_lines.append(f"override_Path_VBS4={norm_dir}")
        if not found_version:
            new_lines.append(f"vbs4_version={required_version}")

        tmp_path = path.with_suffix(path.suffix + ".tmp")
        bak_path = path.with_suffix(path.suffix + ".bak")

        tmp_path.write_text(
            "\n".join(new_lines) + ("\n" if has_trailing_newline else ""),
            encoding="utf-8",
        )
        shutil.copy2(path, bak_path)
        tmp_path.replace(path)
        logging.info(
            "Updated Reality Mesh settings: override_Path_VBS4=%s, vbs4_version=%s",
            norm_dir,
            required_version,
        )
        return True
    except Exception as exc:
        logging.error("Failed to update settings: %s", exc)
        return False


def ensure_required_vbs4_version(
    settings_path: str, required_version: str = "24.2"
) -> bool:
    """Ensure Reality Mesh settings target the required VBS4 version.

    This convenience function locates the appropriate VBS4 installation and
    updates the settings file.  Logging records both success and failure cases.

    Args:
        settings_path: Path to ``RealityMeshSystemSettings.txt``.
        required_version: Version string to enforce, default ``"24.2"``.

    Returns:
        ``True`` if the settings were updated, ``False`` otherwise.
    """
    vbs4_dir = find_vbs4_dir_for_version(required_version)
    if not vbs4_dir:
        logging.error(
            "Required VBS4 version %s not located; settings unchanged", required_version
        )
        return False

    success = update_realitymesh_settings(settings_path, vbs4_dir, required_version)
    if success:
        logging.info(
            "Reality Mesh configuration updated to use VBS4 %s at %s", required_version, vbs4_dir
        )
    else:
        logging.error("Failed to update Reality Mesh configuration")
    return success
