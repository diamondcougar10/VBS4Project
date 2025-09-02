import os
import shutil
import logging
import xml.etree.ElementTree as ET

LOG = logging.getLogger("pm_preset")

APPDATA_PRESETS = os.path.join(os.environ.get("APPDATA", ""), r"Skyline\PhotoMesh\Presets")
INSTALL_PRESETS = r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets"


def _ensure_dirs() -> None:
    os.makedirs(APPDATA_PRESETS, exist_ok=True)
    try:
        os.makedirs(INSTALL_PRESETS, exist_ok=True)
    except PermissionError:
        pass


def _normalize_to_name_only(preset: str) -> str:
    """Return the bare preset name (no extension, no path)."""
    v = (preset or "").strip().strip('"').strip("'")
    base = os.path.basename(v)
    name, _ext = os.path.splitext(base)
    return name if name else v


def _maybe_normalize_xml(preset_path: str, enforce_obj_only: bool, log=LOG.info) -> None:
    if not enforce_obj_only:
        return
    try:
        arr = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
        ET.register_namespace("d3p1", arr)
        tree = ET.parse(preset_path)
        root = tree.getroot()
        bp = root.find("./BuildParameters") or ET.SubElement(root, "BuildParameters")

        ofs = bp.find("OutputFormats") or ET.SubElement(bp, "OutputFormats")
        for c in list(ofs):
            ofs.remove(c)
        ET.SubElement(ofs, f"{{{arr}}}string").text = "OBJ"

        (bp.find("CenterModelsToProject") or ET.SubElement(bp, "CenterModelsToProject")).text = "true"
        (bp.find("CesiumReprojectZ") or ET.SubElement(bp, "CesiumReprojectZ")).text = "true"

        for tag in ("IsDefault", "IsLastUsed"):
            (root.find(tag) or ET.SubElement(root, tag)).text = "true"

        tree.write(preset_path, encoding="utf-8", xml_declaration=True)
        log(f"[preset] normalized to OBJ-only + center/ellipsoid: {preset_path}")
    except Exception as e:  # pragma: no cover - best effort
        log(f"⚠️ preset normalization skipped ({e})")


def stage_preset(preset_input: str, enforce_obj_only: bool = False, log=LOG.info) -> str:
    """
    Accepts either a preset NAME (e.g. 'OECPP') or a .PMPreset FILE path.
    If a path is given, copies it into a Presets folder and returns the NAME-ONLY.
    If a name is given, just returns the cleaned name (assumes it exists in a Presets folder).
    """
    _ensure_dirs()
    if not preset_input:
        raise ValueError("preset_input is empty")

    if os.path.isfile(preset_input):
        name = _normalize_to_name_only(preset_input)
        dest_pf = os.path.join(INSTALL_PRESETS, f"{name}.PMPreset")
        dest_ad = os.path.join(APPDATA_PRESETS, f"{name}.PMPreset")
        try:
            shutil.copy2(preset_input, dest_pf)
            preset_path = dest_pf
            log(f"[preset] staged to Program Files: {preset_path}")
        except PermissionError:
            shutil.copy2(preset_input, dest_ad)
            preset_path = dest_ad
            log(f"[preset] staged to AppData: {preset_path}")

        _maybe_normalize_xml(preset_path, enforce_obj_only, log)
        return name

    name_only = _normalize_to_name_only(preset_input)
    return name_only

__all__ = ["stage_preset"]
