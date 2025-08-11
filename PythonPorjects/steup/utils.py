import logging
import logging.handlers
import os
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path
from typing import Iterable
import threading
from tkinter import messagebox

APP_NAME = "VBS4CustomLauncher"
CONFIG_PATH: Path | None = None


def get_appdata_dir(app_name: str, *, roaming: bool = True) -> Path:
    """Return the application data directory for the given app name."""
    base_var = 'APPDATA' if roaming else 'LOCALAPPDATA'
    base = Path(os.getenv(base_var) or Path.home())
    path = base / app_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def set_config_path(app_name: str) -> Path:
    """Initialize and return the config path for the app."""
    global CONFIG_PATH
    CONFIG_PATH = get_appdata_dir(app_name) / 'config.ini'
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return CONFIG_PATH


def write_config_atomic(path: Path, config: ConfigParser) -> None:
    """Write config to *path* atomically."""
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        config.write(fh)
    tmp.replace(path)


def setup_logging(app_name: str, *, console: bool = False) -> logging.Logger:
    """Configure logging and return the root logger."""
    logs_dir = get_appdata_dir(app_name, roaming=False) / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f'{app_name}.log'

    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def normalize_path(path: str | Path) -> Path:
    """Return a normalized Path instance."""
    return Path(os.path.expandvars(str(path))).expanduser()


def resolve_asset_path(name: str) -> Path:
    """Resolve asset path, supporting PyInstaller."""
    base = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)
    return (Path(base) / name)


def tk_call(widget, func, *args, **kwargs):
    """Invoke *func* on Tk main thread."""
    if threading.current_thread() is threading.main_thread():
        return func(*args, **kwargs)
    widget.after(0, lambda: func(*args, **kwargs))


def tk_message(widget, kind: str, title: str, message: str) -> None:
    """Thread-safe messagebox helper."""
    func = getattr(messagebox, kind)
    tk_call(widget, func, title, message)


def safe_popen(args: Iterable[str], *, capture_output: bool = False) -> subprocess.Popen:
    """Launch subprocess without a console window on Windows."""
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.STDOUT if capture_output else None
    return subprocess.Popen(list(args), shell=False, stdout=stdout, stderr=stderr, startupinfo=startupinfo)

