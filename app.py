import os
import sys
import json
import uuid
import hashlib
import threading
import time
import platform
import subprocess
import urllib.request
import shutil
import zipfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

APP_VERSION = "1.3.0"
LICENSE_SECRET = "VDL-2026-S3CR3T-K3Y"
UPDATE_URL = ""

app = Flask(__name__)

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
MUSIC_DIR = os.path.join(BASE_DIR, "music")
FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)


def find_ffmpeg():
    name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    search_dirs = [FFMPEG_DIR, BASE_DIR]
    # macOS .app bundle
    if platform.system() == "Darwin" and getattr(sys, "frozen", False):
        search_dirs.insert(0, os.path.join(os.path.dirname(BASE_DIR), "Resources", "ffmpeg"))
    for d in search_dirs:
        if os.path.isfile(os.path.join(d, name)):
            return d
    path = shutil.which("ffmpeg")
    if path:
        return os.path.dirname(path)
    return None

LICENSE_FILE = os.path.join(BASE_DIR, "license.key")
BROWSER_CHOICES = ["chrome", "firefox", "edge", "brave", "opera", "chromium"]


def validate_license(key):
    key = key.strip().upper()
    parts = key.split('-')
    if len(parts) != 4:
        return False
    base = '-'.join(parts[:3])
    check = parts[3]
    expected = hashlib.sha256((base + LICENSE_SECRET).encode()).hexdigest()[:5].upper()
    return check == expected


def is_licensed():
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        return validate_license(key)
    return False


def save_license(key):
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip().upper())

downloads = {}


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_to_history(entry):
    history = load_history()
    history.insert(0, entry)
    if len(history) > 200:
        history = history[:200]
    save_history(history)


def make_progress_hook(task_id):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            percent = (downloaded / total * 100) if total > 0 else 0
            downloads[task_id].update({
                "status": "downloading",
                "percent": round(percent, 1),
                "speed": format_speed(speed),
                "eta": format_eta(eta),
                "downloaded": format_size(downloaded),
                "total": format_size(total),
                "filename": d.get("filename", ""),
            })
        elif d["status"] == "finished":
            downloads[task_id].update({
                "status": "processing",
                "percent": 100,
                "message": "Conversion en cours...",
            })
    return hook


def format_speed(bps):
    if not bps:
        return "-- KB/s"
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps / 1024 / 1024:.1f} MB/s"


def format_eta(seconds):
    if not seconds:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(b):
    if not b:
        return "0 B"
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / 1024 / 1024:.1f} MB"
    return f"{b / 1024 / 1024 / 1024:.2f} GB"


def get_safe_filename(title):
    keepchars = (" ", ".", "_", "-")
    return "".join(c for c in title if c.isalnum() or c in keepchars).rstrip()


def get_user_agent():
    s = platform.system()
    if s == "Darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    if s == "Linux":
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def detect_site(url):
    url_lower = url.lower()
    sites = {
        "youtube": ["youtube.com", "youtu.be", "music.youtube.com"],
        "soundcloud": ["soundcloud.com"],
        "bandcamp": ["bandcamp.com"],
        "spotify": ["open.spotify.com"],
        "deezer": ["deezer.com"],
        "tiktok": ["tiktok.com"],
        "instagram": ["instagram.com"],
        "twitter": ["twitter.com", "x.com"],
        "facebook": ["facebook.com", "fb.watch"],
        "twitch": ["twitch.tv"],
        "dailymotion": ["dailymotion.com"],
        "vimeo": ["vimeo.com"],
        "reddit": ["reddit.com"],
        "pinterest": ["pinterest.com"],
        "bilibili": ["bilibili.com"],
    }
    for name, domains in sites.items():
        for domain in domains:
            if domain in url_lower:
                return name
    return "other"


def apply_anti_limit(ydl_opts, browser=None, url=""):
    ydl_opts.update({
        "extractor_retries": 5,
        "retries": 10,
        "file_access_retries": 5,
        "fragment_retries": 10,
        "retry_sleep_functions": {"extractor": lambda n: 2 ** n},
        "sleep_interval": 1,
        "max_sleep_interval": 5,
        "sleep_interval_requests": 1,
        "throttledratelimit": 100000,
        "http_headers": {
            "User-Agent": get_user_agent(),
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        "age_limit": None,
    })

    site = detect_site(url)
    if site == "youtube":
        ydl_opts["extractor_args"] = {
            "youtube": [
                "player_client=web,mediaconnect",
                "po_token=web+*",
            ],
        }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    elif browser and browser in BROWSER_CHOICES:
        try:
            test_opts = {"quiet": True, "no_warnings": True}
            test_opts["cookiesfrombrowser"] = (browser,)
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                ydl.cookiejar
            ydl_opts["cookiesfrombrowser"] = (browser,)
        except Exception:
            pass

    return ydl_opts


def download_media(task_id, url, format_type, quality, subtitles, browser=None, audio_quality="320", embed_thumb=True):
    try:
        is_music = format_type in ("mp3", "flac", "wav", "aac", "ogg")
        out_dir = MUSIC_DIR if is_music else DOWNLOAD_DIR

        downloads[task_id] = {
            "status": "starting",
            "percent": 0,
            "url": url,
            "title": "",
            "files": [],
            "site": detect_site(url),
        }

        outtmpl = os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [make_progress_hook(task_id)],
            "noplaylist": False,
            "ignoreerrors": True,
            "no_warnings": True,
            "quiet": True,
        }

        ffmpeg_path = find_ffmpeg()
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        apply_anti_limit(ydl_opts, browser, url)

        if is_music:
            ydl_opts["format"] = "bestaudio/best"
            postprocessors = []

            if format_type == "wav":
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                })
            elif format_type == "flac":
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "flac",
                })
            elif format_type == "aac":
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "aac",
                    "preferredquality": audio_quality,
                })
            elif format_type == "ogg":
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "vorbis",
                    "preferredquality": audio_quality,
                })
            else:
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": audio_quality,
                })

            postprocessors.append({"key": "FFmpegMetadata"})

            if embed_thumb:
                postprocessors.append({"key": "EmbedThumbnail"})
                ydl_opts["writethumbnail"] = True

            ydl_opts["postprocessors"] = postprocessors

        else:
            quality_map = {
                "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "720": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "480": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best",
                "360": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best",
            }
            ydl_opts["format"] = quality_map.get(quality, quality_map["best"])
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["postprocessor_args"] = {"merger": ["-c", "copy"]}

        if subtitles:
            ydl_opts.update({
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["fr", "en"],
                "subtitlesformat": "srt",
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                downloads[task_id]["status"] = "error"
                downloads[task_id]["message"] = "Impossible d'extraire les informations de cette URL"
                return

            entries = []
            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
                downloads[task_id]["title"] = info.get("title", "Playlist")
                downloads[task_id]["total_videos"] = len(entries)
                downloads[task_id]["current_video"] = 0
            else:
                entries = [info]
                downloads[task_id]["title"] = info.get("title", "Media")
                downloads[task_id]["total_videos"] = 1
                downloads[task_id]["current_video"] = 0

            for i, entry in enumerate(entries):
                if entry is None:
                    continue
                downloads[task_id]["current_video"] = i + 1
                downloads[task_id]["current_title"] = entry.get("title", f"Media {i+1}")
                downloads[task_id]["status"] = "downloading"
                downloads[task_id]["percent"] = 0

                ydl.download([entry.get("webpage_url") or entry.get("url") or entry.get("id")])

                ext = format_type if is_music else "mp4"
                if format_type == "ogg":
                    ext = "ogg"
                vid_id = entry.get("id", "")

                found_file = None
                for f in os.listdir(out_dir):
                    if vid_id in f and not f.endswith((".jpg", ".png", ".webp", ".part")):
                        found_file = f
                        break

                if found_file:
                    filepath = os.path.join(out_dir, found_file)
                    file_size = os.path.getsize(filepath)
                    downloads[task_id]["files"].append({
                        "filename": found_file,
                        "size": format_size(file_size),
                        "title": entry.get("title", ""),
                        "is_music": is_music,
                    })
                    add_to_history({
                        "title": entry.get("title", ""),
                        "url": entry.get("webpage_url", url),
                        "filename": found_file,
                        "format": format_type,
                        "quality": quality if not is_music else audio_quality + "kbps",
                        "size": format_size(file_size),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "thumbnail": entry.get("thumbnail", ""),
                        "duration": entry.get("duration", 0),
                        "site": detect_site(url),
                        "is_music": is_music,
                    })

        downloads[task_id]["status"] = "completed"
        downloads[task_id]["message"] = "Telechargement termine"

    except Exception as e:
        msg = str(e)
        if "cookie" in msg.lower():
            msg = "Erreur cookies: fermez le navigateur ou placez un cookies.txt a cote de l'app"
        elif "Unsupported URL" in msg:
            msg = "Site non supporte pour cette URL"
        downloads[task_id]["status"] = "error"
        downloads[task_id]["message"] = msg


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    browser = data.get("browser", "")
    if not url:
        return jsonify({"error": "URL manquante"}), 400

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
        }
        apply_anti_limit(ydl_opts, browser, url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return jsonify({"error": "Impossible d'extraire les informations"}), 400

            site = detect_site(url)

            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
                return jsonify({
                    "type": "playlist",
                    "site": site,
                    "title": info.get("title", "Playlist"),
                    "count": len(entries),
                    "thumbnail": info.get("thumbnails", [{}])[-1].get("url", "") if info.get("thumbnails") else "",
                    "entries": [{
                        "title": e.get("title", f"Media {i+1}"),
                        "url": e.get("url", ""),
                        "duration": e.get("duration", 0),
                    } for i, e in enumerate(entries[:50])]
                })

            return jsonify({
                "type": "video",
                "site": site,
                "title": info.get("title", ""),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "channel": info.get("channel", info.get("uploader", "")),
            })
    except Exception as e:
        msg = str(e)
        if "cookie" in msg.lower():
            msg += " | Fermez le navigateur ou exportez un fichier cookies.txt"
        return jsonify({"error": msg}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json
    urls = data.get("urls", [])
    if isinstance(urls, str):
        urls = [urls]
    urls = [u.strip() for u in urls if u.strip()]

    if not urls:
        return jsonify({"error": "Aucune URL fournie"}), 400

    format_type = data.get("format", "mp4")
    quality = data.get("quality", "best")
    subtitles = data.get("subtitles", False)
    browser = data.get("browser", "")
    audio_quality = data.get("audio_quality", "320")
    embed_thumb = data.get("embed_thumb", True)

    task_ids = []
    for url in urls:
        task_id = str(uuid.uuid4())[:8]
        task_ids.append(task_id)
        thread = threading.Thread(
            target=download_media,
            args=(task_id, url, format_type, quality, subtitles, browser, audio_quality, embed_thumb),
            daemon=True,
        )
        thread.start()

    return jsonify({"task_ids": task_ids})


@app.route("/api/progress_poll/<task_id>")
def get_progress_poll(task_id):
    if task_id in downloads:
        return jsonify(downloads[task_id])
    return jsonify({"status": "waiting"})


@app.route("/api/download_file/<path:filename>")
def download_file(filename):
    for d in (DOWNLOAD_DIR, MUSIC_DIR):
        filepath = os.path.join(d, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
    return jsonify({"error": "Fichier non trouve"}), 404


@app.route("/api/open_folder")
def open_folder():
    folder = request.args.get("type", "video")
    target = MUSIC_DIR if folder == "music" else DOWNLOAD_DIR
    if platform.system() == "Windows":
        os.startfile(target)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
    return jsonify({"status": "ok"})


@app.route("/api/open_file/<path:filename>")
def open_file(filename):
    for d in (DOWNLOAD_DIR, MUSIC_DIR):
        filepath = os.path.join(d, filename)
        if os.path.exists(filepath):
            if platform.system() == "Windows":
                os.startfile(filepath)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", filepath])
            else:
                subprocess.Popen(["xdg-open", filepath])
            return jsonify({"status": "ok"})
    return jsonify({"error": "Fichier non trouve"}), 404


@app.route("/api/search", methods=["POST"])
def search():
    data = request.json
    query = data.get("query", "").strip()
    source = data.get("source", "youtube")
    count = min(int(data.get("count", 10)), 20)
    browser = data.get("browser", "")

    if not query:
        return jsonify({"error": "Recherche vide"}), 400

    search_prefixes = {
        "youtube": f"ytsearch{count}:",
        "soundcloud": f"scsearch{count}:",
        "youtube_music": f"https://music.youtube.com/search?q=",
    }

    search_url = search_prefixes.get(source, f"ytsearch{count}:") + query

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "noplaylist": False,
        }
        apply_anti_limit(ydl_opts, browser, search_url)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
            if info is None:
                return jsonify({"results": []})

            entries = info.get("entries") or []
            results = []
            for e in entries:
                if e is None:
                    continue
                results.append({
                    "title": e.get("title", ""),
                    "url": e.get("url") or e.get("webpage_url", ""),
                    "thumbnail": e.get("thumbnail") or e.get("thumbnails", [{}])[0].get("url", "") if e.get("thumbnails") else "",
                    "duration": e.get("duration", 0),
                    "channel": e.get("channel") or e.get("uploader", ""),
                    "view_count": e.get("view_count", 0),
                })

            return jsonify({"results": results, "query": query, "source": source})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/history")
def get_history():
    return jsonify(load_history())


@app.route("/api/history/clear", methods=["POST"])
def clear_history():
    save_history([])
    return jsonify({"status": "ok"})


@app.route("/api/files")
def list_files():
    file_type = request.args.get("type", "all")
    files = []
    dirs = []
    if file_type == "music":
        dirs = [MUSIC_DIR]
    elif file_type == "video":
        dirs = [DOWNLOAD_DIR]
    else:
        dirs = [DOWNLOAD_DIR, MUSIC_DIR]

    for d in dirs:
        for f in os.listdir(d):
            filepath = os.path.join(d, f)
            if os.path.isfile(filepath) and not f.endswith((".jpg", ".png", ".webp", ".part")):
                is_music = d == MUSIC_DIR
                files.append({
                    "filename": f,
                    "size": format_size(os.path.getsize(filepath)),
                    "date": datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M"),
                    "is_music": is_music,
                })
    files.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(files)


@app.route("/api/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    for d in (DOWNLOAD_DIR, MUSIC_DIR):
        filepath = os.path.join(d, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"status": "ok"})
    return jsonify({"error": "Fichier non trouve"}), 404


@app.route("/api/test_cookies", methods=["POST"])
def test_cookies():
    data = request.json
    browser = data.get("browser", "chrome")
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        apply_anti_limit(ydl_opts, browser, "https://www.youtube.com")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
            if info and info.get("title"):
                return jsonify({"status": "ok", "browser": browser, "title": info["title"]})
            return jsonify({"status": "error", "message": "Extraction echouee"}), 400
    except Exception as e:
        msg = str(e)
        if "cookie" in msg.lower():
            msg = "Impossible de lire les cookies " + browser + ". Fermez " + browser + " et reessayez."
        return jsonify({"status": "error", "message": msg}), 400


@app.route("/api/check_ffmpeg")
def check_ffmpeg():
    path = find_ffmpeg()
    return jsonify({"installed": path is not None, "path": path or ""})


@app.route("/api/install_ffmpeg", methods=["POST"])
def install_ffmpeg():
    if platform.system() != "Windows":
        return jsonify({"status": "error", "message": "Installez ffmpeg via votre gestionnaire de paquets (apt, brew, pacman)"}), 400

    try:
        os.makedirs(FFMPEG_DIR, exist_ok=True)
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = os.path.join(FFMPEG_DIR, "ffmpeg.zip")

        req = urllib.request.Request(url, headers={"User-Agent": "VideoDownloader/" + APP_VERSION})
        with urllib.request.urlopen(req, timeout=120) as resp, open(zip_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.namelist():
                basename = os.path.basename(member)
                if basename in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(member) as src, open(os.path.join(FFMPEG_DIR, basename), "wb") as dst:
                        dst.write(src.read())

        os.remove(zip_path)

        if os.path.isfile(os.path.join(FFMPEG_DIR, "ffmpeg.exe")):
            return jsonify({"status": "ok", "path": FFMPEG_DIR})
        return jsonify({"status": "error", "message": "ffmpeg.exe non trouve dans l'archive"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/cookies_status")
def cookies_status():
    has_file = os.path.exists(COOKIES_FILE)
    ffmpeg_path = find_ffmpeg()
    return jsonify({
        "has_cookies_file": has_file,
        "browsers": BROWSER_CHOICES,
        "yt_dlp_version": yt_dlp.version.__version__,
        "ffmpeg_installed": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path or "",
    })


@app.route("/api/update_ytdlp", methods=["POST"])
def update_ytdlp():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return jsonify({"status": "ok", "message": "yt-dlp mis a jour. Relancez l'application."})
        return jsonify({"status": "error", "message": result.stderr}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/license_status")
def license_status():
    return jsonify({"licensed": is_licensed()})


@app.route("/api/activate", methods=["POST"])
def activate_license():
    data = request.json
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"status": "error", "message": "Veuillez entrer une cle"}), 400
    if validate_license(key):
        save_license(key)
        return jsonify({"status": "ok", "message": "Licence activee avec succes !"})
    return jsonify({"status": "error", "message": "Cle invalide. Verifiez et reessayez."}), 400


@app.route("/api/version")
def get_version():
    return jsonify({"version": APP_VERSION})


@app.route("/api/check_update")
def check_update():
    if not UPDATE_URL:
        return jsonify({"update_available": False, "current": APP_VERSION, "message": "Aucune URL de mise a jour configuree"})
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "VideoDownloader/" + APP_VERSION})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = data.get("version", "")
        if latest and latest != APP_VERSION:
            return jsonify({
                "update_available": True,
                "current": APP_VERSION,
                "latest": latest,
                "download_url": data.get("download_url", ""),
                "changelog": data.get("changelog", ""),
            })
        return jsonify({"update_available": False, "current": APP_VERSION, "latest": latest})
    except Exception as e:
        return jsonify({"update_available": False, "current": APP_VERSION, "error": str(e)})


@app.route("/api/set_update_url", methods=["POST"])
def set_update_url():
    global UPDATE_URL
    data = request.json
    url = data.get("url", "").strip()
    UPDATE_URL = url
    config_path = os.path.join(BASE_DIR, "config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    config["update_url"] = url
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return jsonify({"status": "ok", "url": url})


def load_config():
    global UPDATE_URL
    config_path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        UPDATE_URL = config.get("update_url", "")


load_config()


def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)


def main():
    import webview

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    time.sleep(1)

    icon_path = None
    for d in (BASE_DIR, getattr(sys, "_MEIPASS", "")):
        p = os.path.join(d, "icon.ico")
        if os.path.isfile(p):
            icon_path = p
            break

    window_kwargs = {
        "width": 960,
        "height": 750,
        "min_size": (700, 500),
        "resizable": True,
        "text_select": True,
    }

    webview.create_window(
        "Video Downloader",
        "http://127.0.0.1:5000",
        **window_kwargs,
    )
    webview.start(icon=icon_path)


if __name__ == "__main__":
    if "--web" in sys.argv:
        print("=" * 50)
        print("  Video Downloader - http://localhost:5000")
        print("=" * 50)
        app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
    else:
        main()
