import subprocess
import sys
import platform
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "VideoDownloader"


def check_linux_deps():
    missing = []
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
    except (ImportError, ValueError):
        missing.append("gi / WebKit2")

    if missing:
        print("=" * 55)
        print("  Dependances Linux manquantes")
        print("=" * 55)
        print()
        print("  Installez les paquets systeme suivants :")
        print()
        print("  # Debian / Ubuntu")
        print("  sudo apt install python3-gi python3-gi-cairo \\")
        print("    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \\")
        print("    libgirepository1.0-dev gcc libcairo2-dev \\")
        print("    pkg-config python3-dev")
        print()
        print("  # Fedora")
        print("  sudo dnf install python3-gobject gtk3 \\")
        print("    webkit2gtk4.1 gobject-introspection-devel \\")
        print("    cairo-gobject-devel pkg-config python3-devel")
        print()
        print("  # Arch")
        print("  sudo pacman -S python-gobject gtk3 webkit2gtk-4.1")
        print()
        print("  Puis: pip install pywebview[gtk]")
        print()
        return False
    return True


def build():
    system = platform.system()

    if system == "Linux" and not check_linux_deps():
        print("Corrigez les dependances puis relancez le build.")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"icon.ico{os.pathsep}.",
        "--add-data", f"icon.png{os.pathsep}.",
        "--hidden-import", "webview",
        "--hidden-import", "bottle",
        "--hidden-import", "proxy_tools",
        "--collect-all", "webview",
        "--collect-all", "yt_dlp",
        "--noconfirm",
    ]

    if system == "Windows":
        cmd.extend([
            "--hidden-import", "webview.platforms.edgechromium",
            "--hidden-import", "webview.platforms.cef",
            "--hidden-import", "webview.platforms.winforms",
            "--hidden-import", "clr",
            "--hidden-import", "pythonnet",
        ])
        icon = os.path.join(BASE_DIR, "icon.ico")
        if os.path.exists(icon):
            cmd.extend(["--icon", icon])

    elif system == "Darwin":
        cmd.extend([
            "--hidden-import", "webview.platforms.cocoa",
            "--osx-bundle-identifier", "com.videodownloader.app",
        ])
        icon = os.path.join(BASE_DIR, "icon.icns")
        if os.path.exists(icon):
            cmd.extend(["--icon", icon])

    elif system == "Linux":
        cmd.extend([
            "--hidden-import", "webview.platforms.gtk",
            "--hidden-import", "gi",
            "--hidden-import", "gi.repository.Gtk",
            "--hidden-import", "gi.repository.Gdk",
            "--hidden-import", "gi.repository.GLib",
            "--hidden-import", "gi.repository.WebKit2",
        ])
        icon = os.path.join(BASE_DIR, "icon.png")
        if os.path.exists(icon):
            cmd.extend(["--icon", icon])

    cmd.append("app.py")

    print(f"Building {APP_NAME} for {system}...")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=BASE_DIR)

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    if system == "Windows":
        exe_path = os.path.join(BASE_DIR, "dist", f"{APP_NAME}.exe")
    else:
        exe_path = os.path.join(BASE_DIR, "dist", APP_NAME)

    if system == "Linux":
        os.chmod(exe_path, 0o755)
        create_desktop_file(exe_path)

    print()
    print("=" * 55)
    print(f"  Build OK! ({system})")
    print(f"  -> {exe_path}")
    if system == "Linux":
        print(f"  -> VideoDownloader.desktop cree")
    print("=" * 55)


def create_desktop_file(exe_path):
    icon_path = os.path.join(BASE_DIR, "icon.png")
    desktop = f"""[Desktop Entry]
Name=Video Downloader
Comment=Telecharger des videos depuis n'importe quelle URL
Exec={exe_path}
Icon={icon_path if os.path.exists(icon_path) else "video-display"}
Type=Application
Categories=Network;AudioVideo;
Terminal=false
StartupNotify=true
"""
    desktop_path = os.path.join(BASE_DIR, "dist", "VideoDownloader.desktop")
    with open(desktop_path, "w") as f:
        f.write(desktop)

    local_apps = os.path.expanduser("~/.local/share/applications")
    if os.path.isdir(local_apps):
        dest = os.path.join(local_apps, "VideoDownloader.desktop")
        shutil.copy2(desktop_path, dest)
        print(f"  Desktop entry installe: {dest}")


if __name__ == "__main__":
    build()
