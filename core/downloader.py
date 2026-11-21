import os
import re
import json
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple
import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import webvtt

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

    def _base_ydl_opts(self) -> Dict:
        """Common yt-dlp options including Deno / Node.js EJS runtime when available."""
        opts: Dict = {
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 3,
            'remote_components': ['ejs:github'],
        }
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
            # Support both youtube-transcript-api >= 1.0 (.list) and legacy 0.6.x (.list_transcripts)
            if hasattr(YouTubeTranscriptApi, "list_transcripts"):
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            else:
                transcript_list = YouTubeTranscriptApi().list(video_id)
            
            # Try English, Bengali, or manually created transcripts first
            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en', 'bn', 'hi'])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'bn', 'hi'])
                except Exception:
                    # Fallback to whatever first transcript exists
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

    def download_video(self, url: str, output_path: Optional[str] = None) -> Tuple[str, str]:
        """
        Downloads the video (up to 720p MP4 for fast cloud processing) and extracts audio.
        Retries across multiple YouTube player clients if a stream returns an empty file.
        Returns (video_filepath, audio_filepath).
        """
        clean_url = self.normalize_url(url)
        video_id = self.extract_video_id(clean_url) or "video"
        if not output_path:
            output_template = os.path.join(self.temp_dir, f"{video_id}.%(ext)s")
        else:
            output_template = output_path

        cookiefile = self._get_cookiefile()
        default_fmt = (
            'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/'
            'bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best'
        )
        hls_fmt = (
            'bestvideo[protocol^=m3u8][height<=720]+bestaudio/'
            'best[protocol^=m3u8][height<=720]/best[protocol^=m3u8]'
        )
        # Try standard MP4 first, then HLS (with & without cookies), then tv_simply/mobile clients
        client_attempts = [
            (None, True, default_fmt),
            (None, True, hls_fmt),
            (None, False, hls_fmt),
            (['tv_simply'], True, 'best[height<=720]/best'),
            (['tv_simply'], False, 'best[height<=720]/best'),
            (['android'], False, 'best[height<=720]/best'),
            (['android_vr'], False, 'best[height<=720]/best'),
        ]

        attempt_errors = []
        final_video_path = None

        for clients, use_cookies, fmt in client_attempts:
            # Clean any leftover empty or partial files for this video before retrying
            for f in os.listdir(self.temp_dir):
                if f.startswith(video_id) and (f.endswith(('.part', '.ytdl', '.mp4', '.mkv', '.webm'))):
                    fpath = os.path.join(self.temp_dir, f)
                    if os.path.isfile(fpath) and (f.endswith(('.part', '.ytdl')) or os.path.getsize(fpath) < 1024):
                        try:
                            os.remove(fpath)
                        except OSError:
                            pass

            ydl_opts = {
                **self._base_ydl_opts(),
                'format': fmt,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'quiet': False,
                'no_warnings': True,
            }
            if clients:
                ydl_opts['extractor_args'] = {'youtube': {'player_client': clients}}
            if use_cookies and cookiefile:
                ydl_opts['cookiefile'] = cookiefile

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([clean_url])

                candidate = os.path.join(self.temp_dir, f"{video_id}.mp4")
                if not os.path.exists(candidate):
                    for f in os.listdir(self.temp_dir):
                        if f.startswith(video_id) and f.endswith(('.mp4', '.mkv', '.webm')):
                            candidate = os.path.join(self.temp_dir, f)
                            break

                if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
                    final_video_path = candidate
                    break
                else:
                    attempt_errors.append(f"{clients}: Downloaded file was empty")
            except Exception as e:
                attempt_errors.append(f"{clients}: {e}")
                print(f"[Notice] yt-dlp attempt with client {clients} failed: {e}")

        if not final_video_path:
            raise RuntimeError(f"ভিডিও ডাউনলোড করা যায়নি: {' | '.join(attempt_errors)}")

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
        """Downloads a direct MP4/video URL to temp_dir with streaming and size guard."""
        video_path = os.path.join(self.temp_dir, "direct_video.mp4")
        with requests.get(url.strip(), stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            content_type = (r.headers.get("Content-Type") or "").lower()
            if "text/html" in content_type:
                raise RuntimeError("এটি সরাসরি ভিডিও ফাইল (MP4) লিংক নয়, একটি ওয়েবপেজ লিংক।")
            total = 0
            limit = max_mb * 1024 * 1024
            with open(video_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        total += len(chunk)
                        if total > limit:
                            raise RuntimeError(f"ভিডিও ফাইলটি {max_mb} MB-এর চেয়ে বড়।")
                        f.write(chunk)
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
            raise RuntimeError("ডাউনলোড করা ভিডিও ফাইলটি খালি।")
        return video_path
