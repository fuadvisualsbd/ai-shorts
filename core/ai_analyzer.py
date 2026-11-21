import os
import re
import json
import warnings
from typing import Dict, List, Optional
warnings.filterwarnings("ignore")
import google.generativeai as genai

class AIAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    def analyze_viral_clips(
        self,
        transcript_segments: List[Dict],
        video_title: str = "",
        min_duration: int = 30,
        max_duration: int = 60,
        num_clips: int = 3
    ) -> List[Dict]:
        """
        Finds the most viral continuous segments from the timestamped transcript.
        If Gemini API key is set, uses Gemini 2.5 Flash / 1.5 Flash.
        Otherwise, falls back to intelligent heuristic highlight detection.
        """
        if self.api_key:
            try:
                clips = self._analyze_with_gemini(transcript_segments, video_title, min_duration, max_duration, num_clips)
                if clips:
                    return clips
            except Exception as e:
                print(f"[Warning] Gemini API analysis failed: {e}. Falling back to heuristic detection.")

        return self._heuristic_viral_detection(transcript_segments, min_duration, max_duration, num_clips)

    def _analyze_with_gemini(
        self,
        segments: List[Dict],
        video_title: str,
        min_duration: int,
        max_duration: int,
        num_clips: int
    ) -> List[Dict]:
        """Uses Gemini to detect hooks, emotional peaks, and standalone engaging clips."""
        # Format transcript lines with seconds
        formatted_lines = []
        for s in segments:
            formatted_lines.append(f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}")
        full_transcript = "\n".join(formatted_lines)

        prompt = f"""You are a world-class viral short-form video editor (expert in TikTok, YouTube Shorts, and Instagram Reels).
Video Title: "{video_title}"

Here is the full timestamped transcript of the video:
---
{full_transcript[:25000]}
---

YOUR MISSION:
Identify the top {num_clips} most viral, engaging, and standalone clips suitable for YouTube Shorts or Reels.
CRITERIA FOR EACH CLIP:
1. **Immediate Hook**: The first 3-5 seconds MUST grab immediate attention (curiosity gap, controversial statement, shocking fact, funny reaction, or clear question).
2. **Standalone Story**: The clip must make complete sense on its own. Do NOT start mid-sentence or cut off before the punchline or conclusion.
3. **Target Duration**: Duration MUST be strictly between {min_duration} seconds and {max_duration} seconds.
4. **Viral Score**: Rate from 1 to 100 based on emotional impact, engagement, and retention potential.

Respond ONLY with a valid JSON array of objects with the exact following schema:
[
  {{
    "title": "Short punchy catchy title for the reel",
    "start_time": 45.2,
    "end_time": 88.0,
    "duration": 42.8,
    "viral_score": 94,
    "hook": "First sentence or hook statement",
    "reason": "Why this specific moment will get high engagement"
  }}
]
"""

        # Try gemini-2.5-flash or gemini-1.5-flash
        model_names = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-pro"]
        response_text = None
        for m_name in model_names:
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(prompt)
                if response and response.text:
                    response_text = response.text
                    break
            except Exception:
                continue

        if not response_text:
            raise RuntimeError("No response received from Gemini models")

        # Parse JSON from response
        clean_json_str = response_text.strip()
        if "```json" in clean_json_str:
            clean_json_str = clean_json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json_str:
            clean_json_str = clean_json_str.split("```")[1].split("```")[0].strip()

        clips_data = json.loads(clean_json_str)
        # Validate timestamps
        valid_clips = []
        for c in clips_data:
            start = float(c.get("start_time", 0))
            end = float(c.get("end_time", 0))
            dur = end - start
            if dur >= min_duration * 0.8:
                c["start_time"] = round(start, 2)
                c["end_time"] = round(end, 2)
                c["duration"] = round(dur, 2)
                valid_clips.append(c)

        return valid_clips[:num_clips]

    def _heuristic_viral_detection(
        self,
        segments: List[Dict],
        min_duration: int = 30,
        max_duration: int = 60,
        num_clips: int = 3
    ) -> List[Dict]:
        """
        Rule-based heuristic detector:
        Evaluates speech density, hook trigger words (curiosity, questions, surprises),
        and continuous flow to select top segments without requiring any API key.
        """
        if not segments:
            return []

        hook_keywords = {
            "why", "how", "secret", "never", "always", "mistake", "truth", "crazy",
            "insane", "money", "rich", "stop", "best", "worst", "unbelievable",
            "কখনো", "কেন", "কীভাবে", "রহস্য", "ভুল", "সত্যি", "টাকা", "আসল"
        }

        candidates = []
        n = len(segments)

        for i in range(n):
            start_t = segments[i]['start']
            current_text = []
            
            for j in range(i, n):
                end_t = segments[j]['end']
                dur = end_t - start_t
                current_text.append(segments[j]['text'])

                if min_duration <= dur <= max_duration:
                    combined_text = " ".join(current_text)
                    words = combined_text.lower().split()
                    
                    # Score based on hook keywords, question marks, exclamation marks
                    score = 70.0
                    hook_matches = sum(1 for w in words if any(kw in w for kw in hook_keywords))
                    score += min(hook_matches * 5, 20)
                    score += combined_text.count("?") * 3
                    score += combined_text.count("!") * 2
                    
                    # Bonus if first 10 words have a question or hook keyword
                    first_words = " ".join(words[:12])
                    if any(kw in first_words for kw in hook_keywords) or "?" in first_words:
                        score += 8

                    first_sentence = segments[i]['text'].strip()
                    candidates.append({
                        "title": f"Viral Highlight @ {int(start_t)}s",
                        "start_time": round(start_t, 2),
                        "end_time": round(end_t, 2),
                        "duration": round(dur, 2),
                        "viral_score": min(int(score), 99),
                        "hook": first_sentence[:80],
                        "reason": "High speech density and hook keyword triggers"
                    })
                elif dur > max_duration:
                    break

        # Sort by viral_score descending and pick non-overlapping clips
        candidates.sort(key=lambda x: x["viral_score"], reverse=True)

        selected = []
        for cand in candidates:
            # Check overlap with already selected
            overlap = False
            for s in selected:
                if not (cand["end_time"] <= s["start_time"] or cand["start_time"] >= s["end_time"]):
                    overlap = True
                    break
            if not overlap:
                selected.append(cand)
            if len(selected) >= num_clips:
                break

        return selected
