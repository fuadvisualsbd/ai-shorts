import os
import subprocess
from typing import Optional

class VideoCropper:
    def __init__(self, use_gpu: bool = True):
        self.use_gpu = use_gpu

    @staticmethod
    def _escape_ffmpeg_path(path: str) -> str:
        """Escapes Windows and Linux path for FFmpeg filter graph."""
        p = os.path.abspath(path).replace("\\", "/")
        # Colon in drive letter must be escaped: C: -> C\\:
        if len(p) > 1 and p[1] == ":":
            p = p[0] + "\\:" + p[2:]
        p = p.replace("'", "'\\''")
        return p

    def render_vertical_clip(
        self,
        input_video: str,
        output_video: str,
        start_time: float,
        end_time: float,
        mode: str = "blur_bg",
        ass_subtitles: Optional[str] = None
    ) -> str:
        """
        Extracts and converts segment to 1080x1920 vertical video with optional burned subtitles.
        Modes:
          - 'blur_bg': Blurred zoomed video background + crisp centered video foreground.
          - 'center_crop': Direct 9:16 center crop filling the whole frame.
          - 'fit_black': Video centered with clean black bars.
        """
        os.makedirs(os.path.dirname(output_video), exist_ok=True)
        duration = end_time - start_time

        # Build FFmpeg video filtergraph
        if mode == "blur_bg":
            vf = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "boxblur=25:5,eq=brightness=-0.12[bg];"
                "[0:v]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[base]"
            )
            last_pad = "[base]"
        elif mode == "center_crop":
            vf = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base]"
            last_pad = "[base]"
        else: # fit_black
            vf = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2[base]"
            last_pad = "[base]"

        if ass_subtitles and os.path.exists(ass_subtitles):
            escaped_sub = self._escape_ffmpeg_path(ass_subtitles)
            vf += f";{last_pad}subtitles='{escaped_sub}'[v_out]"
            final_map = "[v_out]"
        else:
            final_map = last_pad

        # Encoder selection (veryfast cuts CPU render time significantly on cloud hosts)
        encoder = "libx264"
        preset = "veryfast"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", input_video,
            "-t", str(duration),
            "-filter_complex", vf,
            "-map", final_map,
            "-map", "0:a?",
            "-c:v", encoder,
            "-preset", preset,
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_video
        ]

        print(f"[FFmpeg] Rendering clip from {start_time}s to {end_time}s ({duration:.1f}s)...")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"[FFmpeg Error]: {result.stderr[-500:]}")
            raise RuntimeError(f"FFmpeg failed with code {result.returncode}: {result.stderr[-300:]}")

        return output_video
