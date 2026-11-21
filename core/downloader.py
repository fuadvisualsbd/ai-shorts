import os
import re
import time
import shutil
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple
import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

try:
    from pytubefix import YouTube as PyTubeFixYouTube
except ImportError:
    PyTubeFixYouTube = None


class VideoDownloader:
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extracts standard 11-char YouTube ID from URL."""
        pattern = r"(?:v=|\/|youtu\.be\/|embed\/|watch\?v=|\&v=)([a-zA-Z0-9_-]{11})"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Strips playlist/radio query params (e.g. &list=RD...) so only the single video is processed."""
        video_id = cls.extract_video_id(url)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return url.strip()

    def _get_cookiefile(self) -> Optional[str]:
        """Writes YOUTUBE_COOKIES env var (e.g. from Streamlit Secrets) to a temp file if provided."""
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "").strip()
        if not cookies_content:
            return None
        cookie_path = os.path.join(self.temp_dir, "yt_cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookies_content)
        return cookie_path

    @staticmethod
    def _get_proxy() -> Optional[str]:
        """Returns optional YOUTUBE_PROXY URL from environment / Streamlit Secrets."""
        proxy = os.environ.get("YOUTUBE_PROXY", "").strip()
        return proxy or None

    @staticmethod
    def _requests_proxies() -> Optional[Dict[str, str]]:
        proxy = VideoDownloader._get_proxy()
        if not proxy:
            return None
        return {"http": proxy, "https": proxy}

    def _base_ydl_opts(self, num_connections: int = 8) -> Dict:
        """Common yt-dlp options including EJS runtime, parallel fragments, and optional proxy."""
        opts: Dict = {
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 3,
            'concurrent_fragment_downloads': max(1, min(int(num_connections), 16)),
            'http_chunk_size': 10 * 1024 * 1024,
            'remote_components': ['ejs:github'],
        }
        proxy = self._get_proxy()
        if proxy:
            opts['proxy'] = proxy

        runtimes = {}
        deno_path = shutil.which("deno")
        if not deno_path:
            try:
                import deno
                deno_path = deno.find_deno_bin()
            except Exception:
                pass
        if deno_path:
            runtimes['deno'] = {'path': deno_path}
        node_path = shutil.which("node")
        if node_path:
            runtimes['node'] = {'path': node_path}
        if runtimes:
            opts['js_runtimes'] = runtimes
        return opts

    def get_info(self, url: str) -> Dict:
        """Fetches video metadata (title, duration, thumbnail, author) without downloading."""
        clean_url = self.normalize_url(url)
        ydl_opts = {
            **self._base_ydl_opts(),
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'ignore_no_formats_error': True,
        }
        cookiefile = self._get_cookiefile()
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'channel': info.get('uploader') or info.get('channel'),
                    'description': (info.get('description') or '')[:500],
                }
        except Exception:
            if PyTubeFixYouTube is not None:
                yt = PyTubeFixYouTube(clean_url, client='WEB', proxies=self._requests_proxies())
                return {
                    'id': self.extract_video_id(clean_url),
                    'title': yt.title,
                    'duration': getattr(yt, 'length', 0) or 0,
                    'thumbnail': yt.thumbnail_url,
                    'channel': yt.author,
                    'description': (yt.description or '')[:500],
                }
            raise

    def list_available_formats(self, url: str) -> Dict:
        """
        IDM-style format grabber: inspects video metadata and available download qualities.
        Tries yt-dlp first and falls back to pytubefix (WEB/IOS).
        """
        clean_url = self.normalize_url(url)
        title = "YouTube Video"
        duration = 0
        channel = ""
        size_by_height: Dict[int, float] = {}
        audio_size_mb: Optional[float] = None

        # 1) Try yt-dlp format inspection
        try:
            ydl_opts = {
                **self._base_ydl_opts(),
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'ignore_no_formats_error': True,
            }
            cookiefile = self._get_cookiefile()
            if cookiefile:
                ydl_opts['cookiefile'] = cookiefile
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                title = info.get('title') or title
                duration = info.get('duration') or 0
                channel = info.get('uploader') or info.get('channel') or ""
                formats = info.get('formats') or []

                best_audio_bytes = 0
                for fmt in formats:
                    if fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
                        fsize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                        if fsize > best_audio_bytes:
                            best_audio_bytes = fsize
                if best_audio_bytes > 0:
                    audio_size_mb = round(best_audio_bytes / (1024 * 1024), 1)

                for fmt in formats:
                    h = fmt.get('height')
                    if not h or fmt.get('vcodec') == 'none':
                        continue
                    fsize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                    if fsize <= 0 and fmt.get('tbr') and duration:
                        fsize = int((fmt['tbr'] * 1000 / 8) * duration)
                    total_bytes = fsize + (best_audio_bytes if fmt.get('acodec') == 'none' and fsize > 0 else 0)
                    if total_bytes > 0:
                        mb = round(total_bytes / (1024 * 1024), 1)
                        if h not in size_by_height or mb > size_by_height[h]:
                            size_by_height[h] = mb
        except Exception as e:
            print(f"[Notice] yt-dlp format inspection fallback: {e}")

        # 2) Fallback to pytubefix if needed
        if not size_by_height and PyTubeFixYouTube is not None:
            for client in ('WEB', 'IOS', 'ANDROID'):
                try:
                    yt = PyTubeFixYouTube(clean_url, client=client, proxies=self._requests_proxies())
                    title = yt.title or title
                    duration = getattr(yt, 'length', 0) or duration
                    channel = yt.author or channel
                    audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    a_bytes = (audio_stream.filesize or 0) if audio_stream else 0
                    if a_bytes > 0:
                        audio_size_mb = round(a_bytes / (1024 * 1024), 1)
                    for s in yt.streams.filter(type='video'):
                        if not s.resolution:
                            continue
                        try:
                            h = int(s.resolution.replace('p', ''))
                        except ValueError:
                            continue
                        v_bytes = s.filesize or 0
                        if v_bytes > 0:
                            tot = v_bytes + (0 if s.is_progressive else a_bytes)
                            mb = round(tot / (1024 * 1024), 1)
                            if h not in size_by_height or mb > size_by_height[h]:
                                size_by_height[h] = mb
                    if size_by_height:
                        break
                except Exception:
                    continue

        standard_heights = [
            (1080, "🎬 1080p Full HD (MP4)"),
            (720, "🎬 720p HD (MP4) — প্রস্তাবিত"),
            (480, "📱 480p SD (MP4)"),
            (360, "⚡ 360p Compact (MP4)"),
        ]
        choices: List[Dict] = []
        for h, base_label in standard_heights:
            # Find nearest known height within +/- 20px
            matched_mb = size_by_height.get(h)
            if matched_mb is None:
                for kh, kmb in size_by_height.items():
                    if abs(kh - h) <= 20:
                        matched_mb = kmb
                        break
            size_txt = f" — ~{matched_mb} MB" if matched_mb else ""
            choices.append({
                'key': f"{h}p",
                'label': f"{base_label}{size_txt}",
                'height': h,
                'audio_only': False,
                'ext': 'mp4',
                'size_mb': matched_mb,
            })

        audio_txt = f" — ~{audio_size_mb} MB" if audio_size_mb else ""
        choices.append({
            'key': "audio",
            'label': f"🎵 Audio Only (M4A){audio_txt}",
            'height': 0,
            'audio_only': True,
            'ext': 'm4a',
            'size_mb': audio_size_mb,
        })

        return {
            'title': title,
            'duration': duration,
            'channel': channel,
            'formats': choices,
        }

    def fetch_native_transcript(self, url: str) -> Optional[List[Dict]]:
        """
        Tries to fetch native or auto-generated YouTube transcripts instantly.
        Supports both youtube-transcript-api >= 1.0 and legacy 0.6.x.
        Returns list of {'start': float, 'end': float, 'text': str} if found.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return None

        try:
            if hasattr(YouTubeTranscriptApi, "list_transcripts"):
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            else:
                transcript_list = YouTubeTranscriptApi().list(video_id)

            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en', 'bn', 'hi'])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'bn', 'hi'])
                except Exception:
                    for t in transcript_list:
                        transcript = t
                        break

            if transcript:
                raw_data = transcript.fetch()
                clean_segments = []
                for item in raw_data:
                    if isinstance(item, dict):
                        start = float(item['start'])
                        duration = float(item['duration'])
                        text = item['text']
                    else:
                        start = float(item.start)
                        duration = float(item.duration)
                        text = item.text
                    clean_segments.append({
                        'start': round(start, 2),
                        'end': round(start + duration, 2),
                        'text': text.replace('\n', ' ').strip()
                    })
                if clean_segments:
                    return clean_segments
        except Exception as e:
            print(f"[Notice] Native YouTube transcript not available: {e}")

        return None

    def idm_segmented_download(
        self,
        stream_url: str,
        dest_path: str,
        num_connections: int = 8,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        label: str = "ডাউনলোড হচ্ছে"
    ) -> str:
        """
        IDM-style multi-connection segmented HTTP downloader.
        Splits large files across N parallel byte-range connections and merges them cleanly.
        """
        req_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
        }
        if headers:
            req_headers.update(headers)
        proxies = self._requests_proxies()

        total_bytes = 0
        supports_ranges = False

        # Probe content-length and byte-range support
        try:
            probe_headers = {**req_headers, "Range": "bytes=0-0"}
            with requests.get(stream_url, headers=probe_headers, proxies=proxies, stream=True, timeout=20) as r:
                if r.status_code == 206:
                    supports_ranges = True
                    cr = r.headers.get("Content-Range", "")
                    if "/" in cr:
                        total_str = cr.split("/")[-1].strip()
                        if total_str.isdigit():
                            total_bytes = int(total_str)
                elif r.status_code == 200:
                    cl = r.headers.get("Content-Length", "")
                    if cl.isdigit():
                        total_bytes = int(cl)
                    supports_ranges = "bytes" in (r.headers.get("Accept-Ranges", "")).lower()
                elif r.status_code >= 400:
                    r.raise_for_status()
        except Exception:
            supports_ranges = False

        num_connections = max(1, min(int(num_connections), 16))
        start_time = time.time()

        # Segmented parallel download if supported and > 1 MB
        if supports_ranges and total_bytes > 1024 * 1024 and num_connections > 1:
            part_paths = [f"{dest_path}.seg_{i}" for i in range(num_connections)]
            chunk_size = total_bytes // num_connections
            ranges = []
            for i in range(num_connections):
                s_byte = i * chunk_size
                e_byte = (total_bytes - 1) if i == num_connections - 1 else ((i + 1) * chunk_size - 1)
                ranges.append((i, s_byte, e_byte, part_paths[i]))

            lock = threading.Lock()
            downloaded_counter = [0]
            last_report = [0.0]

            def download_segment(idx: int, start_b: int, end_b: int, part_file: str):
                seg_headers = {**req_headers, "Range": f"bytes={start_b}-{end_b}"}
                with requests.get(stream_url, headers=seg_headers, proxies=proxies, stream=True, timeout=45) as resp:
                    resp.raise_for_status()
                    with open(part_file, "wb") as pf:
                        for chunk in resp.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                pf.write(chunk)
                                with lock:
                                    downloaded_counter[0] += len(chunk)
                                    now = time.time()
                                    if progress_callback and (now - last_report[0] >= 0.25 or downloaded_counter[0] >= total_bytes):
                                        last_report[0] = now
                                        frac = min(0.99, downloaded_counter[0] / total_bytes)
                                        elapsed = max(0.1, now - start_time)
                                        speed_mb = (downloaded_counter[0] / (1024 * 1024)) / elapsed
                                        done_mb = downloaded_counter[0] / (1024 * 1024)
                                        tot_mb = total_bytes / (1024 * 1024)
                                        progress_callback(
                                            frac,
                                            f"{label} ({num_connections}x কানেকশন): {done_mb:.1f} / {tot_mb:.1f} MB ({speed_mb:.2f} MB/s)"
                                        )

            try:
                with ThreadPoolExecutor(max_workers=num_connections) as pool:
                    futures = [pool.submit(download_segment, i, sb, eb, pp) for i, sb, eb, pp in ranges]
                    for fut in as_completed(futures):
                        fut.result()

                with open(dest_path, "wb") as out_f:
                    for pp in part_paths:
                        with open(pp, "rb") as pf:
                            shutil.copyfileobj(pf, out_f, length=1024 * 1024)
            finally:
                for pp in part_paths:
                    if os.path.exists(pp):
                        try:
                            os.remove(pp)
                        except OSError:
                            pass

            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
                return dest_path

        # Single-stream fallback
        downloaded = 0
        last_rep = 0.0
        with requests.get(stream_url, headers=req_headers, proxies=proxies, stream=True, timeout=60) as r:
            r.raise_for_status()
            if not total_bytes:
                cl = r.headers.get("Content-Length", "")
                if cl.isdigit():
                    total_bytes = int(cl)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if progress_callback and (now - last_rep >= 0.25):
                            last_rep = now
                            elapsed = max(0.1, now - start_time)
                            speed_mb = (downloaded / (1024 * 1024)) / elapsed
                            done_mb = downloaded / (1024 * 1024)
                            if total_bytes > 0:
                                frac = min(0.99, downloaded / total_bytes)
                                tot_mb = total_bytes / (1024 * 1024)
                                progress_callback(frac, f"{label}: {done_mb:.1f} / {tot_mb:.1f} MB ({speed_mb:.2f} MB/s)")
                            else:
                                progress_callback(0.5, f"{label}: {done_mb:.1f} MB ({speed_mb:.2f} MB/s)")
        if not os.path.exists(dest_path) or os.path.getsize(dest_path) <= 1024:
            raise RuntimeError("ডাউনলোড করা স্ট্রিমটি খালি (0 bytes)।")
        return dest_path

    def _download_pt_stream(
        self,
        stream,
        dest_path: str,
        num_connections: int,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        label: str = "ডাউনলোড হচ্ছে",
    ) -> str:
        """Downloads a pytubefix stream via IDM segmented downloader with client-native fallback."""
        try:
            return self.idm_segmented_download(
                stream_url=stream.url,
                dest_path=dest_path,
                num_connections=num_connections,
                progress_callback=progress_callback,
                label=label,
            )
        except Exception:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            if progress_callback:
                progress_callback(0.35, f"{label} (Client Stream Fallback)...")
            stream.download(output_path=os.path.dirname(dest_path), filename=os.path.basename(dest_path))
            if not os.path.exists(dest_path) or os.path.getsize(dest_path) <= 1024:
                raise RuntimeError("pytubefix স্ট্রিম ডাউনলোড খালি হয়েছে।")
            return dest_path

    def _cleanup_partial_files(self, prefix: str):
        """Removes leftover empty/partial files for a video ID before retrying."""
        for f in os.listdir(self.temp_dir):
            if f.startswith(prefix) and (
                f.endswith(('.part', '.ytdl', '.seg_0'))
                or '.seg_' in f
                or f.endswith(('.mp4', '.mkv', '.webm', '.m4a'))
            ):
                fpath = os.path.join(self.temp_dir, f)
                if os.path.isfile(fpath) and (
                    f.endswith(('.part', '.ytdl')) or '.seg_' in f or os.path.getsize(fpath) < 1024
                ):
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass

    def _download_with_ytdlp(
        self,
        clean_url: str,
        video_id: str,
        target_height: int,
        audio_only: bool,
        num_connections: int,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Attempts multi-client download via yt-dlp with parallel fragment connections."""
        cookiefile = self._get_cookiefile()
        ext = "m4a" if audio_only else "mp4"
        file_tag = "audio" if audio_only else f"{target_height}p"
        file_stem = f"{video_id}_{file_tag}"
        output_template = os.path.join(self.temp_dir, f"{file_stem}.%(ext)s")

        if audio_only:
            default_fmt = "bestaudio[ext=m4a]/bestaudio/best"
            client_attempts = [
                (None, True, default_fmt),
                (['tv_simply'], True, default_fmt),
                (['android'], False, default_fmt),
                (['android_vr'], False, default_fmt),
            ]
        else:
            default_fmt = (
                f"bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={target_height}]+bestaudio/"
                f"best[height<={target_height}]/bestvideo+bestaudio/best"
            )
            hls_fmt = (
                f"bestvideo[protocol^=m3u8][height<={target_height}]+bestaudio/"
                f"best[protocol^=m3u8][height<={target_height}]/best[protocol^=m3u8]"
            )
            client_attempts = [
                (None, True, default_fmt),
                (None, True, hls_fmt),
                (None, False, hls_fmt),
                (['tv_simply'], True, f'best[height<={target_height}]/best'),
                (['tv_simply'], False, f'best[height<={target_height}]/best'),
                (['android'], False, f'best[height<={target_height}]/best'),
                (['android_vr'], False, f'best[height<={target_height}]/best'),
            ]

        def ydl_hook(d: Dict):
            if not progress_callback:
                return
            if d.get('status') == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                speed = d.get('speed') or 0
                speed_mb = speed / (1024 * 1024) if speed else 0.0
                done_mb = downloaded / (1024 * 1024)
                if total > 0:
                    frac = min(0.95, downloaded / total)
                    tot_mb = total / (1024 * 1024)
                    progress_callback(
                        frac,
                        f"IDM ইঞ্জিন ডাউনলোড ({num_connections}x): {done_mb:.1f} / {tot_mb:.1f} MB ({speed_mb:.2f} MB/s)"
                    )
                else:
                    progress_callback(0.4, f"ডাউনলোড হচ্ছে: {done_mb:.1f} MB ({speed_mb:.2f} MB/s)")

        errors: List[str] = []
        title: Optional[str] = None

        for clients, use_cookies, fmt in client_attempts:
            self._cleanup_partial_files(file_stem)
            ydl_opts = {
                **self._base_ydl_opts(num_connections=num_connections),
                'format': fmt,
                'outtmpl': output_template,
                'overwrites': True,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [ydl_hook],
            }
            if not audio_only:
                ydl_opts['merge_output_format'] = 'mp4'
            if clients:
                ydl_opts['extractor_args'] = {'youtube': {'player_client': clients}}
            if use_cookies and cookiefile:
                ydl_opts['cookiefile'] = cookiefile

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    if info:
                        title = info.get('title') or title

                candidate = os.path.join(self.temp_dir, f"{file_stem}.{ext}")
                if not os.path.exists(candidate):
                    valid_exts = ('.m4a', '.mp3', '.webm', '.opus') if audio_only else ('.mp4', '.mkv', '.webm')
                    for f in os.listdir(self.temp_dir):
                        if f.startswith(file_stem) and f.endswith(valid_exts):
                            candidate = os.path.join(self.temp_dir, f)
                            break

                if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
                    return candidate, title, errors
                errors.append(f"yt-dlp({clients}): empty file")
            except Exception as e:
                errors.append(f"yt-dlp({clients}): {e}")
                print(f"[Notice] yt-dlp attempt with client {clients} failed: {e}")

        return None, title, errors

    def _download_with_pytubefix(
        self,
        clean_url: str,
        video_id: str,
        target_height: int,
        audio_only: bool,
        num_connections: int,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Engine 2: Uses pytubefix (with automatic PO Token via WEB/IOS/ANDROID clients)
        and downloads stream URLs via IDM 8-connection segmented downloader.
        """
        if PyTubeFixYouTube is None:
            return None, None, ["pytubefix not installed"]

        errors: List[str] = []
        proxies = self._requests_proxies()
        clients_to_try = ['WEB', 'WEB_EMBED', 'IOS', 'ANDROID']
        file_tag = "audio" if audio_only else f"{target_height}p"
        file_stem = f"{video_id}_{file_tag}"

        for client in clients_to_try:
            self._cleanup_partial_files(file_stem)
            try:
                if progress_callback:
                    progress_callback(0.10, f"PO-Token ইঞ্জিন ({client}) দিয়ে স্ট্রিম খোঁজা হচ্ছে...")

                yt = PyTubeFixYouTube(clean_url, client=client, proxies=proxies)
                title = yt.title or video_id

                if audio_only:
                    a_stream = (
                        yt.streams.filter(only_audio=True, file_extension='mp4').order_by('abr').desc().first()
                        or yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    )
                    if not a_stream:
                        errors.append(f"pytubefix({client}): no audio stream")
                        continue
                    out_audio = os.path.join(self.temp_dir, f"{file_stem}.m4a")
                    self._download_pt_stream(
                        stream=a_stream,
                        dest_path=out_audio,
                        num_connections=num_connections,
                        progress_callback=progress_callback,
                        label="অডিও ডাউনলোড"
                    )
                    if os.path.exists(out_audio) and os.path.getsize(out_audio) > 1024:
                        return out_audio, title, errors
                    continue

                # Prefer progressive MP4 if target_height <= 720 and exact/matching res exists
                prog_streams = list(yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc())
                chosen_prog = None
                for ps in prog_streams:
                    try:
                        h = int((ps.resolution or "0p").replace("p", ""))
                    except ValueError:
                        h = 0
                    if h <= target_height:
                        chosen_prog = ps
                        break

                # Check if an adaptive stream gives better/requested resolution (e.g. 1080p or 720p when progressive is only 360p)
                adap_videos = list(yt.streams.filter(adaptive=True, file_extension='mp4', type='video').order_by('resolution').desc())
                chosen_adap = None
                for av in adap_videos:
                    try:
                        h = int((av.resolution or "0p").replace("p", ""))
                    except ValueError:
                        h = 0
                    if h <= target_height:
                        chosen_adap = av
                        break

                prog_h = int((chosen_prog.resolution or "0p").replace("p", "")) if chosen_prog and chosen_prog.resolution else 0
                adap_h = int((chosen_adap.resolution or "0p").replace("p", "")) if chosen_adap and chosen_adap.resolution else 0

                out_mp4 = os.path.join(self.temp_dir, f"{file_stem}.mp4")

                if chosen_prog and (prog_h >= target_height or prog_h >= adap_h):
                    self._download_pt_stream(
                        stream=chosen_prog,
                        dest_path=out_mp4,
                        num_connections=num_connections,
                        progress_callback=progress_callback,
                        label=f"ভিডিও ডাউনলোড ({chosen_prog.resolution})"
                    )
                    if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 1024:
                        return out_mp4, title, errors

                if chosen_adap:
                    a_stream = (
                        yt.streams.filter(only_audio=True, file_extension='mp4').order_by('abr').desc().first()
                        or yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    )
                    if not a_stream:
                        errors.append(f"pytubefix({client}): no audio track for muxing")
                        continue

                    v_part = os.path.join(self.temp_dir, f"{video_id}_vid.mp4")
                    a_part = os.path.join(self.temp_dir, f"{video_id}_aud.m4a")
                    try:
                        self._download_pt_stream(
                            stream=chosen_adap,
                            dest_path=v_part,
                            num_connections=num_connections,
                            progress_callback=lambda f, m: progress_callback(f * 0.75, m) if progress_callback else None,
                            label=f"ভিডিও ট্র্যাক ({chosen_adap.resolution})"
                        )
                        self._download_pt_stream(
                            stream=a_stream,
                            dest_path=a_part,
                            num_connections=num_connections,
                            progress_callback=lambda f, m: progress_callback(0.75 + f * 0.20, m) if progress_callback else None,
                            label="অডিও ট্র্যাক"
                        )
                        if progress_callback:
                            progress_callback(0.96, "FFmpeg দিয়ে ভিডিও ও অডিও মার্জ করা হচ্ছে...")
                        cmd = [
                            "ffmpeg", "-y", "-i", v_part, "-i", a_part,
                            "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
                            out_mp4
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    finally:
                        for tmp in (v_part, a_part):
                            if os.path.exists(tmp):
                                try:
                                    os.remove(tmp)
                                except OSError:
                                    pass
                    if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 1024:
                        return out_mp4, title, errors

            except Exception as e:
                errors.append(f"pytubefix({client}): {e}")
                print(f"[Notice] pytubefix attempt with client {client} failed: {e}")

        return None, None, errors

    def download_media(
        self,
        url: str,
        target_height: int = 720,
        audio_only: bool = False,
        num_connections: int = 8,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict:
        """
        IDM-style built-in media downloader combining yt-dlp (multi-fragment)
        and pytubefix (PO-Token + 8-connection segmented HTTP downloader).
        Returns dict with file_path, title, ext, size_mb, engine.
        """
        clean_url = self.normalize_url(url)
        video_id = self.extract_video_id(clean_url) or "video"

        if progress_callback:
            progress_callback(0.05, "স্ট্রিমিং সার্ভারের সাথে সংযোগ স্থাপন করা হচ্ছে...")

        file_path, title, ytdlp_errors = self._download_with_ytdlp(
            clean_url=clean_url,
            video_id=video_id,
            target_height=target_height,
            audio_only=audio_only,
            num_connections=num_connections,
            progress_callback=progress_callback,
        )
        engine = "yt-dlp"

        if not file_path:
            file_path, pt_title, pt_errors = self._download_with_pytubefix(
                clean_url=clean_url,
                video_id=video_id,
                target_height=target_height,
                audio_only=audio_only,
                num_connections=num_connections,
                progress_callback=progress_callback,
            )
            title = pt_title or title
            engine = "pytubefix-idm"
            all_errors = ytdlp_errors + pt_errors
        else:
            all_errors = ytdlp_errors

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError(f"ভিডিও ডাউনলোড করা যায়নি: {' | '.join(all_errors)}")

        if progress_callback:
            progress_callback(1.0, "ডাউনলোড সম্পূর্ণ হয়েছে!")

        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        ext = os.path.splitext(file_path)[1].lstrip(".") or ("m4a" if audio_only else "mp4")
        return {
            "file_path": file_path,
            "title": title or video_id,
            "ext": ext,
            "size_mb": size_mb,
            "engine": engine,
        }

    def download_video(self, url: str, output_path: Optional[str] = None) -> Tuple[str, str]:
        """
        Downloads the video (up to 720p MP4) using the built-in multi-engine downloader
        and extracts 16kHz mono WAV audio for Whisper transcription.
        Returns (video_filepath, audio_filepath).
        """
        clean_url = self.normalize_url(url)
        video_id = self.extract_video_id(clean_url) or "video"
        res = self.download_media(clean_url, target_height=720, audio_only=False, num_connections=8)
        final_video_path = res["file_path"]
        if output_path and os.path.abspath(output_path) != os.path.abspath(final_video_path):
            shutil.move(final_video_path, output_path)
            final_video_path = output_path
        audio_path = self.extract_audio(final_video_path, prefix=video_id)
        return final_video_path, audio_path

    def extract_audio(self, video_path: str, prefix: str = "uploaded") -> str:
        """Extracts 16kHz mono WAV audio from a video file for Whisper transcription."""
        audio_path = os.path.join(self.temp_dir, f"{prefix}_audio.wav")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            audio_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return audio_path

    def download_direct_url(self, url: str, max_mb: int = 400) -> str:
        """Downloads a direct MP4/video URL to temp_dir using IDM segmented downloader."""
        video_path = os.path.join(self.temp_dir, "direct_video.mp4")
        self.idm_segmented_download(url.strip(), video_path, num_connections=8)
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
            raise RuntimeError("ডাউনলোড করা ভিডিও ফাইলটি খালি।")
        if os.path.getsize(video_path) > max_mb * 1024 * 1024:
            raise RuntimeError(f"ভিডিও ফাইলটি {max_mb} MB-এর চেয়ে বড়।")
        return video_path
