#!/usr/bin/env python3
"""Capture a Windows MCP Inspector GUI click-through artifact.

The official Inspector GUI and Chrome run on Windows. The MCP server they
connect to is still the prepared XBrainLab WSL runtime from the generated client
configuration, so PyQt, EEG, PyTorch, and local LLM dependencies stay out of the
external client process.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "mcp"
DEFAULT_CONFIG = Path("artifacts/mcp/xbrainlab-mcp.json")
DEFAULT_SERVER_NAME = "xbrainlab-windows-wsl"
WINDOWS_NPX = Path("/mnt/c/Program Files/nodejs/npx")
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
WINDOWS_CHROME = Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
JSON_ARTIFACT = "inspector-gui-walkthrough.json"
MD_ARTIFACT = "inspector-gui-walkthrough.md"
SCREENSHOT_ARTIFACT = "inspector-gui-connected.png"
PROFILE_DIRNAME = "_chrome-inspector-gui-profile"
EXPECTED_VISIBLE_TOOLS = (
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
)
EXPECTED_VISIBLE_TOOL_LABELS = {
    "scan_source": "Scan Source",
    "preview_interpretation": "Preview Interpretation",
    "validate_interpretation": "Validate Interpretation",
    "apply_interpretation": "Apply Interpretation",
}
TOKEN_RE = re.compile(r"MCP_PROXY_AUTH_TOKEN=[^\s\"']+")
INSPECTOR_URL_RE = re.compile(
    r"http://localhost:\d+/\?MCP_PROXY_AUTH_TOKEN=[^\s\"']+",
)

NODE_CDP_SCRIPT = r"""
const fs = require('fs');
const port = process.argv[1];
const screenshotPath = process.argv[2];
const timeoutMs = Number(process.argv[3] || '90000');
const expectedTools = JSON.parse(process.argv[4] || '[]');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function toolVisible(tool, text) {
  return text.includes(tool.name) || text.includes(tool.label);
}

async function tabs() {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://localhost:${port}/json`);
      const payload = await response.json();
      if (Array.isArray(payload) && payload.length) {
        return payload;
      }
    } catch (error) {}
    await sleep(500);
  }
  throw new Error('No Chrome DevTools Protocol tab became available.');
}

function connect(webSocketDebuggerUrl) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(webSocketDebuggerUrl);
    const pending = new Map();
    let nextId = 0;
    const openTimer = setTimeout(
      () => reject(new Error('Chrome DevTools websocket open timeout.')),
      15000,
    );

    socket.addEventListener('open', () => {
      clearTimeout(openTimer);
      resolve({
        command(method, params = {}) {
          nextId += 1;
          const id = nextId;
          socket.send(JSON.stringify({ id, method, params }));
          return new Promise((resolveCommand, rejectCommand) => {
            pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
            setTimeout(() => {
              if (pending.has(id)) {
                pending.delete(id);
                rejectCommand(new Error(`CDP command timeout: ${method}`));
              }
            }, 15000);
          });
        },
        close() {
          socket.close();
        },
      });
    });

    socket.addEventListener('error', (event) => {
      reject(new Error(`Chrome DevTools websocket error: ${event.message || event.type}`));
    });
    socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      if (payload.id && pending.has(payload.id)) {
        pending.get(payload.id).resolve(payload);
        pending.delete(payload.id);
      }
    });
  });
}

async function main() {
  const browserTabs = await tabs();
  const tab =
    browserTabs.find((item) => (item.url || '').includes('localhost:6274')) ||
    browserTabs[0];
  const cdp = await connect(tab.webSocketDebuggerUrl);
  const command = cdp.command.bind(cdp);

  async function evaluate(expression) {
    const response = await command('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    const result = response.result && response.result.result;
    if (!result) {
      return null;
    }
    if (Object.prototype.hasOwnProperty.call(result, 'value')) {
      return result.value;
    }
    return result.description || null;
  }

  const snapshotExpression = `(() => ({
    title: document.title,
    text: document.body.innerText,
    buttons: [...document.querySelectorAll('button')]
      .map((button) => button.textContent.trim())
      .filter(Boolean),
    inputs: [...document.querySelectorAll('input,textarea')]
      .map((input) => ({
        value: input.value,
        placeholder: input.placeholder,
        aria: input.getAttribute('aria-label'),
      })),
  }))()`;
  const clickByLabelExpression = (labels) => `(() => {
    const labels = ${JSON.stringify(labels)};
    const controls = [...document.querySelectorAll('button,[role=tab]')];
    for (const label of labels) {
      const control = controls.find((item) =>
        item.textContent.trim().includes(label)
      );
      if (control) {
        control.click();
        return 'clicked ' + label + ': ' + control.textContent.trim();
      }
    }
    return 'not found: ' + labels.join(', ');
  })()`;

  await command('Page.enable');
  await command('Runtime.enable');
  await command('Page.bringToFront');

  const deadline = Date.now() + timeoutMs;
  let before = null;
  while (Date.now() < deadline) {
    before = await evaluate(snapshotExpression);
    if (before && before.text && before.text.includes('Connect')) {
      break;
    }
    await sleep(500);
  }

  const click = await evaluate(clickByLabelExpression(['Connect']));
  const actions = [{ step: 'connect', result: click }];
  const poll = [];
  let after = null;
  while (Date.now() < deadline) {
    after = await evaluate(snapshotExpression);
    const text = (after && after.text) || '';
    if (
      poll.length < 8 ||
      text.includes('scan_source') ||
      text.includes('Connected') ||
      text.includes('Disconnect')
    ) {
      poll.push({ index: poll.length, text: text.slice(0, 1000) });
    }
    if (text.includes('Connected') || text.includes('Disconnect')) {
      const toolClick = await evaluate(clickByLabelExpression(['List Tools', 'Tools']));
      actions.push({ step: 'tools', result: toolClick });
    }
    if (expectedTools.every((tool) => toolVisible(tool, text))) {
      break;
    }
    await sleep(750);
  }

  const screenshot = await command('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  });
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.result.data, 'base64'));
  cdp.close();

  const finalText = (after && after.text) || '';
  const inputs = (after && after.inputs) || [];
  const inputValues = inputs.map((input) => input.value || '');
  console.log(JSON.stringify({
    tabTitle: tab.title || '',
    tabUrl: tab.url || '',
    click,
    actions,
    before,
    after,
    poll,
    connected: finalText.includes('Connected') || finalText.includes('Disconnect'),
    serverNameVisible: finalText.includes('xbrainlab'),
    commandValue: inputValues.find((value) => value === 'wsl.exe') || '',
    argumentsValue:
      inputValues.find((value) => value.includes('run_mcp_server_for_client.sh')) ||
      '',
    toolsVisible: Object.fromEntries(
      expectedTools.map((tool) => [tool.name, toolVisible(tool, finalText)]),
    ),
    toolLabelsVisible: Object.fromEntries(
      expectedTools.map((tool) => [tool.name, finalText.includes(tool.label)]),
    ),
    screenshotPath,
  }));
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for MCP Inspector GUI artifacts.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Inspector MCP servers config path, relative to repo root by default.",
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER_NAME,
        help="MCP server entry name to select in the Inspector.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Maximum time for Inspector startup and GUI interaction.",
    )
    parser.add_argument("--npx-path", default=str(WINDOWS_NPX))
    parser.add_argument("--node-path", default=str(WINDOWS_NODE))
    parser.add_argument("--chrome-path", default=str(WINDOWS_CHROME))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = capture_walkthrough(
        output_dir=output_dir,
        config_path=Path(args.config),
        server_name=args.server,
        timeout_seconds=args.timeout_seconds,
        npx_path=Path(args.npx_path),
        node_path=Path(args.node_path),
        chrome_path=Path(args.chrome_path),
    )
    write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    print(f"Wrote {output_dir / SCREENSHOT_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def capture_walkthrough(
    *,
    output_dir: Path,
    config_path: Path,
    server_name: str,
    timeout_seconds: int,
    npx_path: Path,
    node_path: Path,
    chrome_path: Path,
) -> dict[str, Any]:
    """Run the Inspector GUI and return a structured evidence payload."""
    screenshot_path = output_dir / SCREENSHOT_ARTIFACT
    profile_dir = output_dir / PROFILE_DIRNAME
    payload: dict[str, Any] = {
        "status": "failed",
        "failure_reason": "",
        "claim_boundary": (
            "Automated MCP Inspector GUI click-through against the Windows WSL "
            "client entry; not a human GUI session, full MCP client "
            "certification, or packaging release approval."
        ),
        "server_name": server_name,
        "config_path": str(config_path),
        "inspector_url": "",
        "client_dependency_boundary": (
            "The Inspector and Chrome run as external Windows client processes; "
            "the selected server entry launches the prepared XBrainLab WSL "
            "runtime wrapper."
        ),
        "screenshot": str(screenshot_path),
        "inspector_stdout": [],
        "node_result": {},
        "checks": {},
    }
    inspector: subprocess.Popen[str] | None = None
    chrome: subprocess.Popen[str] | None = None
    try:
        _preflight_paths(npx_path, node_path, chrome_path)
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        line_queue: queue.Queue[str] = queue.Queue()
        inspector = _start_inspector(
            npx_path=npx_path,
            config_path=config_path,
            server_name=server_name,
        )
        threading.Thread(
            target=_pump_process_lines,
            args=(inspector, line_queue),
            daemon=True,
        ).start()
        url, stdout_lines = _wait_for_inspector_url(
            inspector,
            line_queue,
            timeout_seconds,
        )
        payload["inspector_stdout"] = [_sanitize_value(line) for line in stdout_lines]
        payload["inspector_url"] = sanitize_text(url)

        remote_debugging_port = _free_tcp_port()
        chrome = _start_chrome(
            chrome_path=chrome_path,
            remote_debugging_port=remote_debugging_port,
            profile_dir=profile_dir,
            inspector_url=url,
        )
        node_result = _run_node_cdp_walkthrough(
            node_path=node_path,
            remote_debugging_port=remote_debugging_port,
            screenshot_path=screenshot_path,
            timeout_seconds=timeout_seconds,
        )
        payload["node_result"] = _sanitize_value(node_result)
    except Exception as exc:
        payload["failure_reason"] = str(exc)
    finally:
        _terminate_process(chrome)
        _stop_windows_processes(
            process_name="chrome.exe",
            commandline_patterns=[f"*{wsl_path_to_windows(profile_dir)}*"],
        )
        _terminate_process(inspector)
        _stop_windows_processes(
            process_name="node.exe",
            commandline_patterns=[
                "*xbrainlab-mcp.json*",
                "*run_mcp_server_for_client.sh*",
            ],
        )
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)

    checks = build_checks(payload)
    payload["checks"] = checks
    ok, reason = validate_mcp_inspector_payload(payload)
    payload["status"] = "passed" if ok else "failed"
    payload["failure_reason"] = "" if ok else (payload["failure_reason"] or reason)
    return payload


def _preflight_paths(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing Windows runtime path(s): {', '.join(missing)}")


def _start_inspector(
    *,
    npx_path: Path,
    config_path: Path,
    server_name: str,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["BROWSER"] = "none"
    env["CI"] = "1"
    return subprocess.Popen(  # noqa: S603 - fixed validation executable path.
        [
            str(npx_path),
            "-y",
            "@modelcontextprotocol/inspector",
            "--config",
            str(config_path),
            "--server",
            server_name,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _start_chrome(
    *,
    chrome_path: Path,
    remote_debugging_port: int,
    profile_dir: Path,
    inspector_url: str,
) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603 - fixed validation executable path.
        [
            str(chrome_path),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={remote_debugging_port}",
            f"--user-data-dir={wsl_path_to_windows(profile_dir)}",
            "--window-size=1440,1000",
            inspector_url,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_node_cdp_walkthrough(
    *,
    node_path: Path,
    remote_debugging_port: int,
    screenshot_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603 - fixed validation executable path.
        [
            str(node_path),
            "-e",
            NODE_CDP_SCRIPT,
            str(remote_debugging_port),
            wsl_path_to_windows(screenshot_path),
            str(timeout_seconds * 1000),
            json.dumps(
                [
                    {"name": name, "label": EXPECTED_VISIBLE_TOOL_LABELS[name]}
                    for name in EXPECTED_VISIBLE_TOOLS
                ],
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds + 30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Chrome DevTools walkthrough failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}",
        )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Chrome DevTools walkthrough returned no JSON payload.")
    result = json.loads(stdout.splitlines()[-1])
    if not isinstance(result, dict):
        raise RuntimeError("Chrome DevTools walkthrough returned invalid JSON.")
    return cast(dict[str, Any], result)


def _pump_process_lines(
    proc: subprocess.Popen[str],
    line_queue: queue.Queue[str],
) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        line_queue.put(line.rstrip())


def _wait_for_inspector_url(
    proc: subprocess.Popen[str],
    line_queue: queue.Queue[str],
    timeout_seconds: int,
) -> tuple[str, list[str]]:
    lines: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            line = line_queue.get(timeout=1)
        except queue.Empty:
            if proc.poll() is not None:
                raise RuntimeError(
                    "MCP Inspector exited before the GUI URL appeared.",
                ) from None
            continue
        lines.append(line)
        url = extract_inspector_url(line)
        if url:
            return url, lines
    raise RuntimeError("Timed out waiting for MCP Inspector GUI URL.")


def extract_inspector_url(text: str) -> str:
    """Extract the authenticated Inspector GUI URL from stdout."""
    match = INSPECTOR_URL_RE.search(text)
    return match.group(0) if match else ""


def sanitize_text(text: str) -> str:
    """Redact transient Inspector auth tokens from committed artifacts."""
    return TOKEN_RE.sub("MCP_PROXY_AUTH_TOKEN=<redacted>", text)


def wsl_path_to_windows(path: Path) -> str:
    """Convert /mnt/<drive>/... paths for Windows executables."""
    resolved = str(path.resolve())
    if resolved.startswith("/mnt/") and len(resolved) > 6 and resolved[6] == "/":
        drive = resolved[5].upper()
        suffix = resolved[6:].replace("/", "\\")
        return f"{drive}:{suffix}"
    return resolved


def build_checks(payload: dict[str, Any]) -> dict[str, bool]:
    """Return evidence checks for a completed Inspector GUI payload."""
    node_result = _dict(payload.get("node_result"))
    after = _dict(node_result.get("after"))
    after_text = str(after.get("text", ""))
    buttons = [str(item) for item in after.get("buttons", []) if isinstance(item, str)]
    tools_visible = _dict(node_result.get("toolsVisible"))
    screenshot = Path(str(payload.get("screenshot", "")))
    checks = {
        "inspector_url_seen": "localhost:6274" in str(payload.get("inspector_url", "")),
        "connect_clicked": str(node_result.get("click", "")).startswith(
            "clicked Connect",
        ),
        "connected_visible": bool(node_result.get("connected"))
        and "Connected" in after_text,
        "disconnect_visible": "Disconnect" in buttons or "Disconnect" in after_text,
        "server_name_visible": bool(node_result.get("serverNameVisible"))
        and "xbrainlab" in after_text,
        "tools_panel_visible": "Tools" in after_text and "List Tools" in after_text,
        "command_prepopulated": node_result.get("commandValue") == "wsl.exe",
        "wrapper_argument_prepopulated": "run_mcp_server_for_client.sh"
        in str(node_result.get("argumentsValue", "")),
        "screenshot_written": screenshot.exists() and screenshot.stat().st_size > 4096,
    }
    for tool_name in EXPECTED_VISIBLE_TOOLS:
        checks[f"tool_visible_{tool_name}"] = bool(
            tools_visible.get(tool_name),
        ) and _tool_text_visible(tool_name, after_text)
    return checks


def validate_mcp_inspector_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate the GUI evidence is strong enough to support its claim."""
    checks = build_checks(payload)
    for name, passed in checks.items():
        if not passed:
            if name.startswith("tool_visible_"):
                return (
                    False,
                    f"Expected tool was not visible: {name.removeprefix('tool_visible_')}",
                )
            return False, f"MCP Inspector GUI check failed: {name}"
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact human-readable Inspector GUI evidence summary."""
    node_result = _dict(payload.get("node_result"))
    after = _dict(node_result.get("after"))
    lines = [
        "# MCP Inspector GUI Walkthrough",
        "",
        f"- status: `{payload.get('status', 'unknown')}`",
        f"- claim boundary: {payload.get('claim_boundary', '')}",
        f"- client dependency boundary: {payload.get('client_dependency_boundary', '')}",
        f"- server: `{payload.get('server_name', '')}`",
        f"- inspector URL: `{payload.get('inspector_url', '')}`",
        f"- screenshot: `{payload.get('screenshot', '')}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in build_checks(payload).items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend(["", "## Visible Tool Evidence", ""])
    tools_visible = _dict(node_result.get("toolsVisible"))
    for tool_name in EXPECTED_VISIBLE_TOOLS:
        label = EXPECTED_VISIBLE_TOOL_LABELS[tool_name]
        lines.append(
            f"- `{tool_name}` / `{label}`: `{bool(tools_visible.get(tool_name))}`",
        )
    lines.extend(
        [
            "",
            "## Visible Text",
            "",
            "```text",
            str(after.get("text", "")).strip()[:3000],
            "```",
            "",
        ],
    )
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    """Write JSON and Markdown walkthrough artifacts."""
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in value.items()}
    return value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_text_visible(tool_name: str, text: str) -> bool:
    label = EXPECTED_VISIBLE_TOOL_LABELS[tool_name]
    return tool_name in text or label in text


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _terminate_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _stop_windows_processes(
    *,
    process_name: str,
    commandline_patterns: list[str],
) -> None:
    patterns_json = json.dumps(commandline_patterns)
    command = (
        f"$patterns = ConvertFrom-Json @'\n{patterns_json}\n'@; "
        f"Get-CimInstance Win32_Process -Filter \"name='{process_name}'\" | "
        "Where-Object { "
        "$cmd = $_.CommandLine; "
        "$patterns | Where-Object { $cmd -like $_ } "
        "} | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue "
        "}"
    )
    subprocess.run(  # noqa: S603 - fixed PowerShell cleanup command.
        ["powershell.exe", "-NoProfile", "-Command", command],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


if __name__ == "__main__":
    raise SystemExit(main())
