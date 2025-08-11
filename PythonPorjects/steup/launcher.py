import os
import tkinter as tk
from configparser import ConfigParser
from threading import Thread

from utils import (
    APP_NAME,
    setup_logging,
    tk_message,
    normalize_path,
    resolve_asset_path,
    safe_popen,
    set_config_path,
    write_config_atomic,
)

logger = setup_logging(APP_NAME, console=bool(os.getenv('DEBUG')))
CONFIG_PATH = set_config_path(APP_NAME)

DEFAULTS = {
    'paths': {
        'bypass': r"C:\\Bohemia Interactive Simulations\\VBS4 24.1 YYMEA_General\\VBS4.exe",
        'regular': r"C:\\Bohemia Interactive Simulations\\VBS4 24.1 YYMEA_General\\VBSLauncher.exe",
    }
}

config = ConfigParser()
config.read_dict(DEFAULTS)
if CONFIG_PATH.exists():
    config.read(CONFIG_PATH)
else:
    write_config_atomic(CONFIG_PATH, config)

bypass_launcher_path = normalize_path(config.get('paths', 'bypass'))
regular_launcher_path = normalize_path(config.get('paths', 'regular'))

root = tk.Tk()

ICON_PATH = resolve_asset_path('icon.ico')
if ICON_PATH.exists():
    root.iconbitmap(ICON_PATH)
else:
    logger.warning('Icon file not found: %s', ICON_PATH)

root.title('VBS4 Custom Launcher')
root.geometry('400x300')


def launch_bypass() -> None:
    def worker() -> None:
        if bypass_launcher_path.exists():
            try:
                safe_popen([str(bypass_launcher_path)])
                logger.info('Launched bypass: %s', bypass_launcher_path)
                tk_message(root, 'info', 'Launcher', 'VBS4 launched in bypass mode!')
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to launch bypass: %s', exc)
                tk_message(root, 'error', 'Error', f'Failed to launch in bypass mode.\n{exc}')
        else:
            logger.error('Bypass application path does not exist: %s', bypass_launcher_path)
            tk_message(root, 'error', 'Error', 'Bypass application path does not exist.')
    Thread(target=worker, name='bypass-launch', daemon=True).start()


def launch_regular() -> None:
    def worker() -> None:
        if regular_launcher_path.exists():
            try:
                safe_popen([str(regular_launcher_path)])
                logger.info('Launched regular: %s', regular_launcher_path)
                tk_message(root, 'info', 'Launcher', 'VBS4 launched with the regular startup window!')
            except Exception as exc:  # noqa: BLE001
                logger.exception('Failed to launch regular: %s', exc)
                tk_message(root, 'error', 'Error', f'Failed to launch with the regular startup window.\n{exc}')
        else:
            logger.error('Regular application path does not exist: %s', regular_launcher_path)
            tk_message(root, 'error', 'Error', 'Regular application path does not exist.')
    Thread(target=worker, name='regular-launch', daemon=True).start()


def exit_application() -> None:
    logger.info('Application exiting')
    root.destroy()


label = tk.Label(root, text='VBS4 Custom Launcher', font=('Helvetica', 16))
label.pack(pady=20)

bypass_button = tk.Button(root, text='Launch VBS4', command=launch_bypass, font=('Helvetica', 12), bg='blue', fg='white')
bypass_button.pack(pady=10)

regular_button = tk.Button(root, text='Launch VBS4 Setup', command=launch_regular, font=('Helvetica', 12), bg='green', fg='white')
regular_button.pack(pady=10)

exit_button = tk.Button(root, text='Exit', command=exit_application, font=('Helvetica', 12), bg='red', fg='white')
exit_button.pack(pady=10)

root.mainloop()
