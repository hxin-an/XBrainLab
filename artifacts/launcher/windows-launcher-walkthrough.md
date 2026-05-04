# Windows Launcher Walkthrough

- status: `passed`
- claim boundary: Automated Windows launcher command walkthrough; not a human desktop click-through or packaging release approval.
- desktop command: `C:\Users\Administrator\Desktop\XBrainLab.cmd`
- PowerShell launcher: `D:\workspace_v2\projects\lab\XBrainLab\scripts\launchers\xbrainlab_wsl_launcher.ps1`
- active WSL repo: `/mnt/d/workspace_v2/projects/lab/XBrainLab`

## Checks

- `desktop_points_to_active_repo`: `True`
- `desktop_smoke_skipped_wsl`: `True`
- `wsl_stdout_mirrored`: `True`
- `wsl_stderr_mirrored`: `True`
- `startup_saw_main_window`: `True`
- `startup_bounded`: `True`
- `wsl_log_exists`: `True`
- `startup_log_exists`: `True`

## Logs

- `wsl`: `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/launcher-20260504-112540.log`
- `startup`: `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/launcher-20260504-112540.log`

## Command Summary

- `desktop_cmd_smoke`: return `0`, markers `WSL launch skipped`
- `powershell_wsl_smoke`: return `0`, markers `WSL_launcher_smoke_stdout, WSL_launcher_smoke_stderr`
- `powershell_startup_smoke`: return `0`, markers `MainWindow initialized, GUI kept running until timeout`
