# STE Toolkit - Installed Build Testing Guide

This guide helps you validate the packaged STE Toolkit build on a target machine and confirm fuser auto-start, host grouping, and diagnostics.

## What to run

- Launch: dist/STE_Toolkit/STE_Toolkit.exe
- Run as Administrator is recommended for best reliability (UAC is requested by the build).

## Expected behavior

1) Startup sequence
- Splash screen displays, then the main UI opens.
- A toast/message appears indicating fusers will start (e.g., "(fusers starting ~6 seconds)").

2) Readiness gate
- Before launching fusers, the app checks readiness (fuser exe present, WorkingFuser path writeable, SeedFuser not running, loopback checks, etc.).
- Gate progress and outcomes are logged.

3) Fuser launch
- Missing fusers are launched in parallel, with a sequential retry for any that fail.
- Console/logs show green ✓ for success and red ✗ for failures, with PC name prefixes.

4) UI counts
- Settings shows live counts (e.g., "Local fusers: R/D").
- When enforcement completes, you should see a summary like "Fuser 3/3 started".

5) Host grouping
- Fuser working folders follow: PC(IP)_LocalFuserN
- Host/One-Click grouping uses this pattern so multiple fusers from the same PC are grouped together.

## Where to look for logs

- Main app log: dist/STE_Toolkit/ste_toolkit.log
- Per-fuser diagnostics: <WorkingFuser>\\PC(IP)_LocalFuserN\\_launch_debug\\launch_diag_N.txt
  - Example: \\\\192.168.10.201\\SharedMeshDrive\\WorkingFuser\\KIT2-3-1(192.168.10.22)_LocalFuser1\\_launch_debug\\launch_diag_1.txt

These per-ID files include command-line, current directory, admin/thread info, disk space, write probe results, and any Windows error codes interpreted.

## Common issues and checks

- Fuser exe not found:
  - Check ste_toolkit.log for "find_fuser_exe" entries.
  - Ensure the PhotoMesh Fuser is installed and accessible.

- UNC write probe failure:
  - Verify the WorkingFuser path exists and is writable from this machine.
  - Confirm credentials and that no policy blocks writes.

- SeedFuser overlap:
  - The app attempts to terminate any conflicting SeedFuser processes. If it can’t, kill manually and retry.

- Loopback/local path mixing:
  - Ensure clients use the UNC WorkingFuser; hosts may use local drive mappings, but all fusers must land in the same shared WorkingFuser path.

- Security products:
  - AV/EDR tools may block process launches. Add allow-list entries for STE_Toolkit.exe and PhotoMesh executables if needed.

## Interpreting the summary

- The enforcement summary (also in ste_toolkit.log) lists:
  - Total attempted, successes, failures
  - IDs retried sequentially
  - Durations

If a fuser fails, open its corresponding launch_diag_N.txt and share its contents for rapid triage.

## Reset tips

- If you previously created LocalFuser folders locally (not on the UNC), the app can migrate them to the WorkingFuser share.
- You can remove stale PC(IP)_LocalFuserN folders from the WorkingFuser if they belong to decommissioned machines.

## Support bundle (optional)

If something fails, collect:
- dist/STE_Toolkit/ste_toolkit.log
- The entire folder: <WorkingFuser>\\PC(IP)_LocalFuserN\\_launch_debug
- A screenshot of the Settings counts and Host/One-Click breakdown

