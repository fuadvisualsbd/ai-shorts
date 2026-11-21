import os
from typing import Dict, List, Optional
from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "default"):
        """
        Initializes faster-whisper.
        device: 'cuda', 'cpu', or 'auto'
        model_size: 'tiny', 'base', 'small', 'medium'
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load_model(self):
        if self._model is None:
            # Check if CUDA is available or fallback to CPU gracefully
            try:
                self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            except Exception as e:
                print(f"[Notice] Failed to load on {self.device}, falling back to CPU float32: {e}")
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[Dict]:
        """
        Transcribes audio with word-level timestamps.
        Returns a list of segment dicts:
        [
            {
                'id': int,
                'start': float,
                'end': float,
                'text': str,
                'words': [{'word': str, 'start': float, 'end': float, 'probability': float}, ...]
            }
        ]
        """
        self._load_model()
        
        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True, # Voice Activity Detection filters out silence
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        results = []
        seg_id = 0
        for segment in segments:
            words_data = []
            if segment.words:
                for w in segment.words:
                    words_data.append({
                        'word': w.word.strip(),
                        'start': round(w.start, 2),
                        'end': round(w.end, 2),
                        'probability': round(w.probability, 2)
                    })
            results.append({
                'id': seg_id,
                'start': round(segment.start, 2),
                'end': round(segment.end, 2),
                'text': segment.text.strip(),
                'words': words_data
            })
            seg_id += 1

        return results

    @staticmethod
    def format_transcript_for_ai(segments: List[Dict]) -> str:
        """
        Formats transcript segments into a timestamped readable script for LLM analysis.
        e.g., "[00:15 - 00:22] This is what happened next..."
        """
        def format_ts(sec: float) -> str:
            m = int(sec // 60)
            s = int(sec % 60)
            return f"{m:02d}:{s:02d}"

        lines = []
        for seg in segments:
            start_str = format_ts(seg['start'])
            end_str = format_ts(seg['end'])
            lines.append(f"[{start_str} - {end_str}] {seg['text']}")
        return "\n".join(lines)
