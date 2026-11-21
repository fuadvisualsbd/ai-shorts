import os
import argparse
from core.pipeline import ClipperPipeline

def main():
    parser = argparse.ArgumentParser(description="AI Video Clipper - YouTube to Shorts CLI")
    parser.add_argument("--url", type=str, required=True, help="YouTube video URL")
    parser.add_argument("--clips", type=int, default=3, help="Number of viral clips to extract (default: 3)")
    parser.add_argument("--min", type=int, default=25, help="Minimum clip duration in seconds (default: 25)")
    parser.add_argument("--max", type=int, default=60, help="Maximum clip duration in seconds (default: 60)")
    parser.add_argument("--crop", type=str, default="blur_bg", choices=["blur_bg", "center_crop", "fit_black"], help="Crop layout style")
    parser.add_argument("--no-subs", action="store_true", help="Disable burned-in subtitles")
    parser.add_argument("--key", type=str, default="", help="Google Gemini API key")
    parser.add_argument("--model", type=str, default="base", help="Whisper model: tiny, base, small")

    args = parser.parse_args()

    pipeline = ClipperPipeline(
        base_dir=os.path.dirname(os.path.abspath(__file__)),
        gemini_api_key=args.key or None,
        whisper_model=args.model
    )

    print(f"\n[AI Video Clipper] Starting processing for: {args.url}")
    results = pipeline.process_url(
        url=args.url,
        num_clips=args.clips,
        min_duration=args.min,
        max_duration=args.max,
        crop_mode=args.crop,
        burn_subtitles=not args.no_subs
    )

    print("\n✅ Processing Complete! Rendered Clips:")
    for i, c in enumerate(results, 1):
        print(f" {i}. [{c.get('viral_score', 0)}/100] {c.get('title')} -> {c.get('output_file')}")

if __name__ == "__main__":
    main()
