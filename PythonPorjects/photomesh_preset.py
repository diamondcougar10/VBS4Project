import os, shutil, xml.etree.ElementTree as ET

APPDATA_PRESETS = os.path.join(os.environ.get("APPDATA", ""), r"Skyline\PhotoMesh\Presets")
INSTALL_PRESETS = r"C:\\Program Files\\Skyline\\PhotoMesh\\Presets"


def _ensure_dirs() -> None:
    os.makedirs(APPDATA_PRESETS, exist_ok=True)
    try:
        os.makedirs(INSTALL_PRESETS, exist_ok=True)
    except PermissionError:
        pass


def _name_only(preset: str) -> str:
    v = (preset or "").strip().strip('"').strip("'")
    base = os.path.basename(v)
    name, _ = os.path.splitext(base)
    return name or v


def stage_preset(preset_input: str) -> str:
    """
    Accept a NAME ('STEPRESET') or a .PMPreset path.
    If path: copy to Program Files Presets (or AppData fallback).
    Return the NAME-ONLY for API/Wizard calls.
    (No normalization needed — your STEPRESET already enforces OBJ + center/ellipsoid.)
    """
    _ensure_dirs()
    if os.path.isfile(preset_input):
        name = _name_only(preset_input)
        pf = os.path.join(INSTALL_PRESETS, f"{name}.PMPreset")
        ad = os.path.join(APPDATA_PRESETS, f"{name}.PMPreset")
        try:
            shutil.copy2(preset_input, pf)
        except PermissionError:
            shutil.copy2(preset_input, ad)
        return name
    return _name_only(preset_input)


__all__ = ["stage_preset"]

