"""Simple watch-folder -> PhotoMesh Project Queue bridge.

Monitors a directory for new sub-folders and submits them to the PhotoMesh
REST Project Queue using a hard-coded preset. After submission the script
starts the build and prints progress via SSE.

This example avoids external dependencies by using polling for new folders
and the ``requests`` package for HTTP calls.
"""

from __future__ import annotations

import os
import time
import requests
from urllib.parse import quote

from photomesh_launcher import PRESET_NAME, install_embedded_preset

try:
    installed = install_embedded_preset()
    print(f"[CFG] Embedded preset installed to: {installed}")
except Exception as e:
    print(f"[WARN] Could not install embedded preset: {e}")
# Adjust these paths for your environment
WATCH_FOLDER = r"C:\\Temp\\Watch"
WORKING_FOLDER = r"C:\\Temp\\PhotoMeshWork"
BASE_URL = "http://localhost:56790"


class WatchFolderQueue:
    """Poll a folder for new subdirectories and queue builds."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        self.seen: set[str] = set()

    def run(self) -> None:
        os.makedirs(self.folder, exist_ok=True)
        while True:
            current = {e.path for e in os.scandir(self.folder) if e.is_dir()}
            for path in sorted(current - self.seen):
                self.seen.add(path)
                try:
                    self.process(path)
                except Exception as exc:  # pragma: no cover - runtime feedback
                    print(f"Error processing {path}: {exc}")
            time.sleep(5)

    # --- PhotoMesh REST helpers -------------------------------------------------
    def process(self, folder_path: str) -> None:
        folder_name = os.path.basename(folder_path)
        project_path = os.path.join(WORKING_FOLDER, folder_name)
        source_path = folder_path
        data = [
            {
                "comment": f"Auto project: {folder_name}",
                "action": 0,
                "projectPath": project_path,
                "buildFrom": 1,
                "buildUntil": 6,
                "inheritBuild": "",
                "preset": PRESET_NAME,
                "workingFolder": WORKING_FOLDER,
                "MaxLocalFusers": 10,
                "MaxAWSFusers": 0,
                "AWSFuserStartupScript": "script",
                "AWSBuildConfigurationName": "",
                "AWSBuildConfigurationJsonPath": "",
                "sourceType": 0,
                "sourcePath": source_path,
            }
        ]

        requests.post(f"{BASE_URL}/ProjectQueue/project/add", json=data)
        requests.post(f"{BASE_URL}/Build/Start")
        self.monitor_sse(WORKING_FOLDER)

    def monitor_sse(self, working_folder: str) -> None:
        """Connect to the SSE endpoint and print progress messages."""
        url = f"{BASE_URL}/SSE?path={quote(working_folder)}"
        try:
            with requests.get(url, stream=True) as resp:
                for line in resp.iter_lines():
                    if line:
                        print(line.decode("utf-8", "ignore"))
        except Exception as exc:  # pragma: no cover - runtime feedback
            print(f"SSE monitor error: {exc}")


if __name__ == "__main__":  # pragma: no cover - manual invocation
    WatchFolderQueue(WATCH_FOLDER).run()

