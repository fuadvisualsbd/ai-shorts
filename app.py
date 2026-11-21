import os
import json
import gradio as gr
from core.pipeline import ClipperPipeline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def load_saved_key():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "")
        except Exception:
            pass
    return ""

def save_key(api_key: str):
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["gemini_api_key"] = api_key
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

def process_video(
    youtube_url: str,
    num_clips: int,
    crop_mode: str,
    burn_subs: bool,
    gemini_key: str,
    progress=gr.Progress(track_tqdm=True)
):
    if not youtube_url or not youtube_url.strip():
        raise gr.Error("দয়া করে একটি সঠিক ইউটিউব ভিডিওর লিংক দিন!")

    if gemini_key and gemini_key.strip():
        save_key(gemini_key.strip())

    progress(0.05, desc="ভিডিও অ্যানালাইসিস শুরু হচ্ছে...")

    def progress_callback(msg: str, frac: float):
        progress(frac, desc=msg)

    pipeline = ClipperPipeline(
        base_dir=BASE_DIR,
        gemini_api_key=gemini_key.strip() or None,
        whisper_model="base"
    )

    results = pipeline.process_url(
        url=youtube_url.strip(),
        num_clips=int(num_clips),
        crop_mode=crop_mode,
        burn_subtitles=burn_subs,
        progress_callback=progress_callback
    )

    outputs = []
    # Maximum 5 clips slots
    for i in range(5):
        if i < len(results):
            c = results[i]
            info_text = f"### 📌 {c.get('title', f'Clip {i+1}')}\n🔥 **Viral Score: {c.get('viral_score', 90)}/100** | ⏱️ {c.get('duration', 0)}s\n_{c.get('reason', '')}_"
            outputs.append(gr.update(value=c.get("output_file"), visible=True))
            outputs.append(gr.update(value=info_text, visible=True))
        else:
            outputs.append(gr.update(value=None, visible=False))
            outputs.append(gr.update(value="", visible=False))

    return tuple(outputs)

# Custom Gradio Blocks UI
with gr.Blocks(theme=gr.themes.Soft(primary_hue="red", neutral_hue="slate"), title="AI Video Clipper - YouTube to Shorts") as demo:
    gr.Markdown("""
    # 🎬 AI Video Clipper & Shorts Generator
    **ইউটিউবের বড় ভিডিও থেকে AI দিয়ে ১-ক্লিকে ৯:১৬ ভাইরাল রিলস/শর্টস তৈরি করুন।**
    """)

    with gr.Row():
        with gr.Column(scale=4):
            url_box = gr.Textbox(
                label="📺 ইউটিউব ভিডিও লিংক",
                placeholder="https://www.youtube.com/watch?v=... বা https://youtu.be/...",
                lines=1
            )
            
            with gr.Row():
                clips_slider = gr.Slider(
                    minimum=1, maximum=5, value=3, step=1,
                    label="কতগুলো শর্টস বের করবেন?"
                )
                crop_select = gr.Dropdown(
                    choices=[
                        ("🌟 Blurred Background (পডকাস্ট স্টাইল)", "blur_bg"),
                        ("📐 Center Crop (ফুলস্ক্রিন ৯:১৬)", "center_crop"),
                        ("⬛ Fit Black Bars (কালো ফ্রেম)", "fit_black")
                    ],
                    value="blur_bg",
                    label="লেআউট স্টাইল"
                )

            with gr.Row():
                subs_check = gr.Checkbox(value=True, label="🔥 অ্যানিমেটেড সাবটাইটেল যুক্ত করুন")
                key_box = gr.Textbox(
                    label="Google Gemini API Key (ঐচ্ছিক)",
                    placeholder="AI Studio API Key দিলে সবচেয়ে সেরা হুক বেছে নেবে",
                    value=load_saved_key(),
                    type="password"
                )

            submit_btn = gr.Button("⚡ Generate Viral Shorts", variant="primary", size="lg")

        with gr.Column(scale=5):
            gr.Markdown("### 🌟 তৈরি হওয়া শর্টস প্রিভিউ:")
            video_slots = []
            info_slots = []
            
            for idx in range(5):
                with gr.Group(visible=False) as grp:
                    info_md = gr.Markdown("", visible=False)
                    vid_player = gr.Video(label=f"Short #{idx+1}", interactive=False, visible=False)
                    video_slots.append(vid_player)
                    info_slots.append(info_md)

    # Flatten output targets: [vid0, info0, vid1, info1, ...]
    out_targets = []
    for v, inf in zip(video_slots, info_slots):
        out_targets.append(v)
        out_targets.append(inf)

    submit_btn.click(
        fn=process_video,
        inputs=[url_box, clips_slider, crop_select, subs_check, key_box],
        outputs=out_targets
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
