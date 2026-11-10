"""Install a per-user Windows copy and manage its Start menu shortcuts."""

import argparse
import os
import shutil
import subprocess
import venv
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3]
MARKER = "circle-to-search-windows-source-v1\n"
SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @('Programs', 'Startup')) {
    $link = Join-Path $shell.SpecialFolders.Item($folder) 'Circle to Search.lnk'
    if ($env:CTS_SHORTCUT_REMOVE -eq '1' -or ($folder -eq 'Startup' -and $env:CTS_SHORTCUT_STARTUP -ne '1')) {
        if (Test-Path -LiteralPath $link) {
            $existing = $shell.CreateShortcut($link)
            if ($existing.TargetPath -eq $env:CTS_SHORTCUT_TARGET -and $existing.Arguments.StartsWith($env:CTS_SHORTCUT_ARGS)) {
                Remove-Item -LiteralPath $link
            }
        }
        continue
    }
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = $env:CTS_SHORTCUT_TARGET
    $shortcut.Arguments = $env:CTS_SHORTCUT_ARGS
    if ($folder -eq 'Startup') { $shortcut.Arguments += ' --background' }
    $shortcut.WorkingDirectory = Split-Path -Parent $shortcut.TargetPath
    $shortcut.Description = 'Circle to Search'
    $shortcut.Save()
}
"""


def shortcuts(target, arguments, *, startup=False, remove=False):
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SHORTCUT_SCRIPT],
        check=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={
            **os.environ,
            "CTS_SHORTCUT_TARGET": str(target),
            "CTS_SHORTCUT_ARGS": subprocess.list2cmdline(arguments),
            "CTS_SHORTCUT_STARTUP": str(int(startup)),
            "CTS_SHORTCUT_REMOVE": str(int(remove)),
        },
    )


def installation_root(prefix=None):
    parent = Path(prefix) if prefix else Path(os.environ["LOCALAPPDATA"]) / "CircleToSearch"
    parent = parent.expanduser().resolve()
    target = parent / "Application"
    if target.resolve().parent != parent or target.is_symlink():
        raise RuntimeError("The CtS installation folder points outside its expected location.")
    if SOURCE.is_relative_to(target.resolve()) or target.resolve().is_relative_to(SOURCE):
        raise RuntimeError("Choose an installation prefix outside the source repository.")
    return target


def install(prefix=None, startup=False):
    from tools.fetch_models import fetch_models

    target = installation_root(prefix)
    marker = target / "cts-install.txt"
    if target.exists() and (not marker.is_file() or marker.read_text() != MARKER):
        raise RuntimeError("The target folder already exists and is not a CtS installation.")
    target.mkdir(parents=True, exist_ok=True)
    marker.write_text(MARKER)
    runtime = target / "runtime"
    python = runtime / "Scripts/python.exe"
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(runtime)
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "PySide6>=6.8",
            str(SOURCE / "server"),
        ],
        check=True,
        timeout=600,
    )
    shutil.copytree(
        SOURCE / "circle_to_search",
        target / "circle_to_search",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.part"),
    )
    for name in ("LICENSE", "THIRD_PARTY.md"):
        shutil.copyfile(SOURCE / name, target / name)
    (target / "server").mkdir(exist_ok=True)
    shutil.copyfile(SOURCE / "server/THIRD_PARTY.md", target / "server/THIRD_PARTY.md")
    shutil.copyfile(SOURCE / "server/LICENSE", target / "server/LICENSE")
    shutil.copytree(SOURCE / "server/licenses", target / "server/licenses", dirs_exist_ok=True)
    fetch_models(target / "circle_to_search/tessdata")
    launcher = target / "launch.pyw"
    launcher.write_text(
        "import sys\nfrom circle_to_search.app import main\nraise SystemExit(main(['--resident', *sys.argv[1:]]))\n",
        encoding="utf-8",
    )
    if not prefix:
        shortcuts(python.with_name("pythonw.exe"), [str(launcher), "--resident"], startup=startup)
    print("Installed Circle to Search:", launcher)
    return launcher


def uninstall(prefix=None):
    target = installation_root(prefix)
    marker = target / "cts-install.txt"
    if not marker.is_file() or marker.read_text() != MARKER:
        raise RuntimeError("No managed Windows CtS installation was found.")
    if not prefix:
        shortcuts(
            target / "runtime/Scripts/pythonw.exe",
            [str(target / "launch.pyw"), "--resident"],
            remove=True,
        )
    shutil.rmtree(target)
    print("Removed Circle to Search. Settings and browser data were preserved.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix", type=Path, help="Stage the install without creating system shortcuts"
    )
    parser.add_argument("--startup", action="store_true", help="Start the tray at sign-in")
    parser.add_argument(
        "--uninstall", action="store_true", help="Remove the managed application and shortcuts"
    )
    args = parser.parse_args(argv)
    try:
        if args.uninstall:
            uninstall(args.prefix)
        else:
            install(args.prefix, args.startup)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.error(str(error))
