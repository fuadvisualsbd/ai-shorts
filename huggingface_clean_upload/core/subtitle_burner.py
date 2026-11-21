import os
from typing import Dict, List, Optional

class SubtitleBurner:
    @staticmethod
    def format_ass_time(seconds: float) -> str:
        """Converts seconds into ASS timestamp format: H:MM:SS.cs"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @classmethod
    def generate_ass(
        cls,
        segments: List[Dict],
        output_ass_path: str,
        clip_start: float = 0.0,
        clip_end: float = 999999.0,
        font_name: str = "Arial Black",
        font_size: int = 60,
        primary_color: str = "&H0000FFFF",  # Bright Yellow in BGR hex (&H00BBGGRR)
        outline_color: str = "&H00000000",  # Pure Black Outline
        words_per_group: int = 3
    ) -> str:
        """
        Generates an Alex Hormozi / MrBeast style ASS subtitle file with
        2-4 words per group, bold styling, heavy outline, placed at the safe lower-third.
        """
        ass_header = f"""[Script Info]
Title: Viral Shorts Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,5,3,2,60,60,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        dialogue_lines = []

        for seg in segments:
            # Check if segment overlaps with the clip
            seg_start = seg.get('start', 0.0)
            seg_end = seg.get('end', 0.0)
            if seg_end <= clip_start or seg_start >= clip_end:
                continue

            words = seg.get('words', [])
            if words:
                # Group words into bite-sized chunks
                for i in range(0, len(words), words_per_group):
                    chunk = words[i:i + words_per_group]
                    w_start = chunk[0]['start']
                    w_end = chunk[-1]['end']

                    # Clamp to clip range
                    if w_end <= clip_start or w_start >= clip_end:
                        continue
                    
                    rel_start = max(0.0, w_start - clip_start)
                    rel_end = max(rel_start + 0.3, min(clip_end - clip_start, w_end - clip_start))

                    chunk_text = " ".join(w['word'] for w in chunk).strip()
                    # Uppercase text looks punchy and viral
                    chunk_text = chunk_text.upper()

                    start_str = cls.format_ass_time(rel_start)
                    end_str = cls.format_ass_time(rel_end)
                    dialogue_lines.append(
                        f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{chunk_text}"
                    )
            else:
                # Segment-level fallback if word timestamps not present
                rel_start = max(0.0, seg_start - clip_start)
                rel_end = max(rel_start + 0.5, min(clip_end - clip_start, seg_end - clip_start))
                text = seg.get('text', '').strip().upper()

                # Split longer sentences into 3-4 word lines
                words_list = text.split()
                if not words_list:
                    continue
                num_chunks = max(1, (len(words_list) + words_per_group - 1) // words_per_group)
                chunk_duration = (rel_end - rel_start) / num_chunks

                for idx in range(num_chunks):
                    sub_chunk = words_list[idx * words_per_group : (idx + 1) * words_per_group]
                    c_start = rel_start + idx * chunk_duration
                    c_end = c_start + chunk_duration
                    dialogue_lines.append(
                        f"Dialogue: 0,{cls.format_ass_time(c_start)},{cls.format_ass_time(c_end)},ViralStyle,,0,0,0,,{' '.join(sub_chunk)}"
                    )

        full_content = ass_header + "\n".join(dialogue_lines) + "\n"
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return output_ass_path
