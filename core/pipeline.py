import os
import time
from typing import Callable, Dict, List, Optional
from core.downloader import VideoDownloader
from core.transcriber import Transcriber
from core.ai_analyzer import AIAnalyzer
from core.subtitle_burner import SubtitleBurner
from core.video_cropper import VideoCropper

class ClipperPipeline:
    def __init__(
        self,
        base_dir: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        whisper_model: str = "base"
    ):
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = base_dir
        self.temp_dir = os.path.join(base_dir, "temp")
        self.output_dir = os.path.join(base_dir, "output")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.downloader = VideoDownloader(temp_dir=self.temp_dir)
        self.transcriber = Transcriber(model_size=whisper_model)
        self.ai_analyzer = AIAnalyzer(api_key=gemini_api_key)
        self.subtitle_burner = SubtitleBurner()
        self.cropper = VideoCropper()

    def process_url(
        self,
        url: str,
        num_clips: int = 3,
        min_duration: int = 30,
        max_duration: int = 60,
        crop_mode: str = "blur_bg",
        burn_subtitles: bool = True,
        subtitle_color: str = "&H0000FFFF",  # Yellow
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Dict]:
        """
        End-to-end execution:
        1. Fetch metadata & check native transcripts
        2. Download video & extract audio
        3. Transcribe audio if native subs not available
        4. Detect viral clips using Gemini or heuristics
        5. Generate subtitles and crop each clip to 9:16 vertical
        """
        def update_progress(msg: str, frac: float):
            if progress_callback:
                progress_callback(msg, frac)
            print(f"[{int(frac * 100)}%] {msg}")

        update_progress("ভিডিওর তথ্য ও মেটাডাটা রিড করা হচ্ছে...", 0.05)
        info = self.downloader.get_info(url)
        video_title = info.get("title", "Video")

        update_progress("সাবটাইটেল ও ট্রান্সক্রিপ্ট চেক করা হচ্ছে...", 0.15)
        native_subs = self.downloader.fetch_native_transcript(url)

        update_progress("ভিডিও ডাউনলোড এবং অডিও প্রস্তুত করা হচ্ছে...", 0.25)
        video_path, audio_path = self.downloader.download_video(url)

        segments = []
        if native_subs:
            update_progress("ইউটিউব থেকে সরাসরি সাবটাইটেল পাওয়া গেছে!", 0.40)
            segments = native_subs
        else:
            update_progress("Whisper AI দিয়ে অডিও ট্রান্সক্রিপশন ও কথা সনাক্ত করা হচ্ছে...", 0.40)
            segments = self.transcriber.transcribe(audio_path)

        if not segments:
            raise RuntimeError("কোনো কথা বা ট্রান্সক্রিপ্ট পাওয়া যায়নি।")

        return self._analyze_and_render_clips(
            video_path=video_path,
            video_title=video_title,
            segments=segments,
            num_clips=num_clips,
            min_duration=min_duration,
            max_duration=max_duration,
            crop_mode=crop_mode,
            burn_subtitles=burn_subtitles,
            subtitle_color=subtitle_color,
            update_progress=update_progress
        )

    def process_file(
        self,
        video_path: str,
        video_title: str = "Uploaded Video",
        num_clips: int = 3,
        min_duration: int = 30,
        max_duration: int = 60,
        crop_mode: str = "center_crop",
        burn_subtitles: bool = True,
        subtitle_color: str = "&H0000FFFF",
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Dict]:
        """Processes an already downloaded or uploaded local video file."""
        def update_progress(msg: str, frac: float):
            if progress_callback:
                progress_callback(msg, frac)
            print(f"[{int(frac * 100)}%] {msg}")

        update_progress("ভিডিও থেকে অডিও আলাদা করা হচ্ছে...", 0.15)
        audio_path = self.downloader.extract_audio(video_path)

        update_progress("Whisper AI দিয়ে অডিও ট্রান্সক্রিপশন ও কথা সনাক্ত করা হচ্ছে...", 0.35)
        segments = self.transcriber.transcribe(audio_path)

        if not segments:
            raise RuntimeError("ভিডিওতে কোনো কথা বা ট্রান্সক্রিপ্ট পাওয়া যায়নি।")

        return self._analyze_and_render_clips(
            video_path=video_path,
            video_title=video_title,
            segments=segments,
            num_clips=num_clips,
            min_duration=min_duration,
            max_duration=max_duration,
            crop_mode=crop_mode,
            burn_subtitles=burn_subtitles,
            subtitle_color=subtitle_color,
            update_progress=update_progress
        )

    def process_direct_url(
        self,
        direct_url: str,
        num_clips: int = 3,
        min_duration: int = 30,
        max_duration: int = 60,
        crop_mode: str = "center_crop",
        burn_subtitles: bool = True,
        subtitle_color: str = "&H0000FFFF",
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Dict]:
        """Downloads a direct video URL (e.g. MP4) and runs clipping pipeline."""
        def update_progress(msg: str, frac: float):
            if progress_callback:
                progress_callback(msg, frac)
            print(f"[{int(frac * 100)}%] {msg}")

        update_progress("ডাইরেক্ট লিংক থেকে ভিডিও ডাউনলোড হচ্ছে...", 0.10)
        video_path = self.downloader.download_direct_url(direct_url)
        return self.process_file(
            video_path=video_path,
            video_title="Direct Video",
            num_clips=num_clips,
            min_duration=min_duration,
            max_duration=max_duration,
            crop_mode=crop_mode,
            burn_subtitles=burn_subtitles,
            subtitle_color=subtitle_color,
            progress_callback=progress_callback
        )

    def _analyze_and_render_clips(
        self,
        video_path: str,
        video_title: str,
        segments: List[Dict],
        num_clips: int,
        min_duration: int,
        max_duration: int,
        crop_mode: str,
        burn_subtitles: bool,
        subtitle_color: str,
        update_progress: Callable[[str, float], None]
    ) -> List[Dict]:
        """Runs viral clip detection and renders 9:16 vertical clips."""
        update_progress("AI দিয়ে ভাইরাল হুক এবং সেরা মোমেন্ট অ্যানালাইসিস করা হচ্ছে...", 0.60)
        clips = self.ai_analyzer.analyze_viral_clips(
            segments,
            video_title=video_title,
            min_duration=min_duration,
            max_duration=max_duration,
            num_clips=num_clips
        )

        if not clips:
            raise RuntimeError("কোনো উপযোগী ক্লিপ পাওয়া যায়নি।")

        update_progress(f"মোট {len(clips)}টি ভাইরাল ক্লিপ নির্বাচন করা হয়েছে! ভিডিও রেন্ডার শুরু হচ্ছে...", 0.70)

        rendered_results = []
        total_clips = len(clips)

        for idx, clip in enumerate(clips):
            clip_num = idx + 1
            progress_val = 0.70 + (0.28 * (clip_num / total_clips))
            update_progress(f"ক্লিপ {clip_num}/{total_clips} প্রসেস ও ৯:১৬ কনভার্ট করা হচ্ছে...", progress_val)

            start_t = clip["start_time"]
            end_t = clip["end_time"]
            clean_title = "".join(c for c in clip.get("title", f"Clip_{clip_num}") if c.isalnum() or c in (" ", "_", "-")).strip()
            clean_title = clean_title.replace(" ", "_")[:30]

            out_filename = f"Short_{clip_num}_{int(start_t)}s_{clean_title}.mp4"
            out_filepath = os.path.join(self.output_dir, out_filename)

            ass_path = None
            if burn_subtitles:
                ass_filename = f"sub_{clip_num}_{int(start_t)}.ass"
                ass_path = os.path.join(self.temp_dir, ass_filename)
                self.subtitle_burner.generate_ass(
                    segments=segments,
                    output_ass_path=ass_path,
                    clip_start=start_t,
                    clip_end=end_t,
                    primary_color=subtitle_color
                )

            self.cropper.render_vertical_clip(
                input_video=video_path,
                output_video=out_filepath,
                start_time=start_t,
                end_time=end_t,
                mode=crop_mode,
                ass_subtitles=ass_path if burn_subtitles else None
            )

            clip["output_file"] = out_filepath
            clip["filename"] = out_filename
            rendered_results.append(clip)

        update_progress("সবগুলো শর্টস ভিডিও সফলভাবে প্রস্তুত সম্পন্ন হয়েছে!", 1.0)
        return rendered_results
