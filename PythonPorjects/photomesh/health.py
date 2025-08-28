import socket, subprocess, os


def _is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def photomesh_stack_ok() -> tuple[bool, dict]:
    """Check Web API (8086) and Node (8087). Return (ok, details)."""
    ok_api = _is_port_open(8086)
    ok_node = _is_port_open(8087)
    return (ok_api and ok_node), {"api8086": ok_api, "node8087": ok_node}


def show_port_diagnostics() -> str:
    """Return a short text with who binds 8086 (best effort, no admin required)."""
    lines = []
    try:
        out = subprocess.check_output("netstat -ano", shell=True).decode(errors="ignore")
        culled = [l for l in out.splitlines() if ":8086" in l]
        lines.append("netstat -ano (8086):")
        lines.extend(culled or ["  (no matching lines)"])
    except Exception as e:
        lines.append(f"netstat failed: {e}")

    # URL ACL listing (no admin needed to read)
    try:
        out = subprocess.check_output("netsh http show urlacl", shell=True).decode(errors="ignore")
        culled = [l for l in out.splitlines() if "8086" in l or "http://+:" in l]
        lines.append("\nurlacl:")
        lines.extend(culled or ["  (no relevant reservations found)"])
    except Exception as e:
        lines.append(f"netsh urlacl failed: {e}")

    return "\n".join(lines)


REMediation_TEXT = (
    "PhotoMesh Web API must bind to http://localhost:8086/ and Node to 8087.\n"
    "If 8086 is in use or reserved, run PowerShell as Administrator and clear the reservation:\n\n"
    "  netsh http show urlacl | findstr 8086\n"
    "  netsh http delete urlacl url=http://+:8086/\n\n"
    "Or stop the conflicting process shown by:  netstat -ano | findstr :8086"
)


def preflight_or_report(log_fn=print, show_dialog=None) -> bool:
    """
    Return True if healthy; otherwise log actionable steps.
    Optionally call show_dialog(title, message) for GUI apps.
    """
    ok, d = photomesh_stack_ok()
    if ok:
        log_fn("Preflight OK: Web API(8086) and Node(8087) responding.")
        return True

    log_fn("Preflight FAILED.")
    if not d.get("api8086"):
        log_fn(" - Web API (8086): DOWN or blocked.")
    if not d.get("node8087"):
        log_fn(" - Node (8087): DOWN or blocked.")

    diag = show_port_diagnostics()
    log_fn(diag)
    log_fn(REMediation_TEXT)

    if show_dialog:
        show_dialog(
            "PhotoMesh Preflight",
            f"Web API(8086)/Node(8087) not reachable.\n\n{REMediation_TEXT}\n\nDetails:\n{diag}"
        )
    return False
