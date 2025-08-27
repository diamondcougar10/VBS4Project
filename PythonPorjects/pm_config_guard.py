import json, os, shutil, time
from typing import Any, Dict, Tuple

PM_CFG = r"C:\\Program Files\\Skyline\\PhotoMeshWizard\\config.json"

# The ONLY fields we’re allowed to change:
ALLOWED_TARGETS = {
    ("DefaultPhotoMeshWizardUI", "OutputProducts", "Model3D"): True,
    ("DefaultPhotoMeshWizardUI", "OutputProducts", "Ortho"): False,
    # Uncomment if you also want them forced off:
    ("DefaultPhotoMeshWizardUI", "OutputProducts", "DSM"): False,
    ("DefaultPhotoMeshWizardUI", "OutputProducts", "DTM"): False,
    ("DefaultPhotoMeshWizardUI", "OutputProducts", "LAS"): False,
}

def _ensure_path(root: Dict[str, Any], path: Tuple[str, ...]) -> Dict[str, Any]:
    """Create intermediate dicts for the given path and return the parent dict."""
    d = root
    for key in path[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    return d

def _get(root: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    d = root
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d

def _set(root: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    parent = _ensure_path(root, path)
    parent[path[-1]] = value

def patch_photomesh_config(cfg_path: str = PM_CFG) -> bool:
    """
    Apply minimal, whitelisted toggles to PhotoMesh config.
    Returns True if a write occurred.
    """
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f"PhotoMesh config not found: {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Config is not valid JSON: {e}")

    changed = False
    before_after = []

    for path, desired in ALLOWED_TARGETS.items():
        current = _get(data, path)
        before_after.append((".".join(path), current, desired))
        if current is not desired:
            _set(data, path, desired)
            changed = True

    if changed:
        # Make a timestamped backup once per run
        ts = time.strftime("%Y%m%d_%H%M%S")
        bak = f"{cfg_path}.{ts}.bak"
        shutil.copy2(cfg_path, bak)

        with open(cfg_path, "w", encoding="utf-8") as f:
            # Use indent=2 for readability; this does not touch unrelated keys
            json.dump(data, f, indent=2)

    # Print a quick report
    print("\n[PhotoMesh config guard]")
    for key, cur, want in before_after:
        print(f"  {key:45} current={cur!r}  ->  required={want!r}")
    print("  wrote_changes:", changed)
    return changed
