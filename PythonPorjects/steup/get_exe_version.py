import sys
import win32api


def get_exe_file_version(exe_path: str) -> str:
    """Return the FileVersion field from an executable."""
    try:
        info = win32api.GetFileVersionInfo(exe_path, '\\')
        ms = info['FileVersionMS']
        ls = info['FileVersionLS']
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return "Unknown"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python get_exe_version.py <path_to_exe>")
        sys.exit(1)
    exe_path = sys.argv[1]
    print(get_exe_file_version(exe_path))


if __name__ == "__main__":
    main()
