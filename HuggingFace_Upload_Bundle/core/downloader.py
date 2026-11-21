import os
import re
import json
import subprocess
from typing import Dict, List, Optional, Tuple
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

    def get_info(self, url: str) -> Dict:
        """Fetches video metadata (title, duration, thumbnail, author) without downloading."""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'id': info.get('id'),
                'title': info.get('title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail'),
                'channel': info.get('uploader') or info.get('channel'),
                'description': info.get('description', '')[:500],
            }

    def fetch_native_transcript(self, url: str) -> Optional[List[Dict]]:
        """
        Tries to fetch native or auto-generated YouTube transcripts instantly.
        Returns list of {'start': float, 'end': float, 'text': str} if found.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return None

        try:
            # First try official transcript API
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
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
                    start = float(item['start'])
                    duration = float(item['duration'])
                    clean_segments.append({
                        'start': round(start, 2),
                        'end': round(start + duration, 2),
                        'text': item['text'].replace('\n', ' ').strip()
                    })
                if clean_segments:
                    return clean_segments
        except Exception as e:
            print(f"[Notice] Native YouTube transcript not available: {e}")

        return None

    def download_video(self, url: str, output_path: Optional[str] = None) -> Tuple[str, str]:
        """
        Downloads the video in 1080p / best quality MP4 and extracts audio.
        Returns (video_filepath, audio_filepath).
        """
        video_id = self.extract_video_id(url) or "video"
        if not output_path:
            output_template = os.path.join(self.temp_dir, f"{video_id}.%(ext)s")
        else:
            output_template = output_path

        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        final_video_path = os.path.join(self.temp_dir, f"{video_id}.mp4")
        if not os.path.exists(final_video_path):
            # Locate file matching prefix
            for f in os.listdir(self.temp_dir):
                if f.startswith(video_id) and f.endswith(('.mp4', '.mkv', '.webm')):
                    final_video_path = os.path.join(self.temp_dir, f)
                    break

        audio_path = os.path.join(self.temp_dir, f"{video_id}_audio.wav")
        # Extract 16kHz mono audio for Whisper / processing
        cmd = [
            "ffmpeg", "-y", "-i", final_video_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            audio_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        return final_video_path, audio_path
