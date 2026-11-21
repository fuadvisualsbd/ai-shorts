import os
import json
import subprocess
import streamlit as st
from core.downloader import VideoDownloader
from core.pipeline import ClipperPipeline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"gemini_api_key": "", "whisper_model": "base", "crop_mode": "blur_bg", "num_clips": 3}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

# Streamlit Page Config
st.set_page_config(
    page_title="AI Video Clipper - YouTube to Shorts",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF8533);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .sub-title {
        color: #888888;
        font-size: 1.05rem;
        margin-bottom: 25px;
    }
    .clip-card {
        background: #1e1e24;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #33333e;
        margin-bottom: 20px;
    }
    .score-badge {
        display: inline-block;
        background: #FF4B4B;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

config = load_config()

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Settings & Configuration")
    
    api_key_input = st.text_input(
        "Google Gemini API Key (Optional)",
        value="",
        type="password",
        help="গুগল এআই স্টুডিও থেকে ফ্রি এপিআই কী দিলে এআই সবচেয়ে সেরা ভাইরাল অংশ বেছে নেবে। না দিলেও লোকাল অ্যালগরিদম দিয়ে কাজ করবে।"
    )
    st.link_button(
        "🔑 Get Free Gemini API Key",
        "https://aistudio.google.com/app/apikey",
        use_container_width=True
    )
    gemini_model_map = {
        "Auto (সব Text-out মডেল পর্যায়ক্রমে)": "auto",
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 3.5 Flash Lite (500 RPD)": "gemini-3.5-flash-lite",
        "Gemini 3.1 Flash Lite (500 RPD)": "gemini-3.1-flash-lite",
        "Gemini 3 Flash": "gemini-3-flash",
        "Gemini 3.6 Flash": "gemini-3.6-flash",
        "Gemini 3.8 Flash": "gemini-3.8-flash",
        "Gemini 4 Hydrogen": "gemini-4-hydrogen",
        "Gemini 3.1 Pro": "gemini-3.1-pro",
    }
    gemini_model_label = st.selectbox(
        "Gemini AI Model (Text-out)",
        options=list(gemini_model_map.keys()),
        index=0,
        help="প্রথমে সিলেক্ট করা মডেল দিয়ে চেষ্টা করবে, কোটা শেষ হলে পরের মডেলগুলোতে অটো সুইচ করবে।"
    )
    selected_gemini_model = gemini_model_map[gemini_model_label]

    st.markdown("---")
    num_clips = st.slider("কতগুলো ক্লিপ বের করবেন?", min_value=1, max_value=5, value=config.get("num_clips", 3))
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        min_dur = st.number_input("মিনিমাম সেকেন্ড", min_value=15, max_value=60, value=25)
    with col_d2:
        max_dur = st.number_input("ম্যাক্সিমাম সেকেন্ড", min_value=30, max_value=90, value=60)

    st.markdown("---")
    crop_mode_label = st.selectbox(
        "৯:১৬ রিলস ফরম্যাট লেআউট",
        options=[
            "📐 Direct Center Crop (ফুলস্ক্রিন ক্রপ - সবচেয়ে দ্রুত)",
            "🌟 Blurred Background (পডকাস্ট ও ভাইরাল স্টাইল)",
            "⬛ Fit with Black Bars (কালো ফ্রেম)"
        ],
        index=0
    )
    crop_modes = {
        "📐 Direct Center Crop (ফুলস্ক্রিন ক্রপ - সবচেয়ে দ্রুত)": "center_crop",
        "🌟 Blurred Background (পডকাস্ট ও ভাইরাল স্টাইল)": "blur_bg",
        "⬛ Fit with Black Bars (কালো ফ্রেম)": "fit_black"
    }
    selected_crop_mode = crop_modes[crop_mode_label]

    st.markdown("---")
    burn_subs = st.checkbox("ক্যাপশন / সাবটাইটেল যুক্ত করুন", value=True)
    sub_color_choice = st.selectbox(
        "সাবটাইটেল কালার",
        options=["🔥 Vibrant Yellow (হলুদ)", "⚪ Clean White (সাদা)", "🟢 Neon Green (সবুজ)", "🔵 Cyan Blue (আকাশি)"],
        index=0
    )
    color_map = {
        "🔥 Vibrant Yellow (হলুদ)": "&H0000FFFF",
        "⚪ Clean White (সাদা)": "&H00FFFFFF",
        "🟢 Neon Green (সবুজ)": "&H0000FF00",
        "🔵 Cyan Blue (আকাশি)": "&H00FFFF00"
    }
    selected_sub_color = color_map[sub_color_choice]

    whisper_model = st.selectbox(
        "Whisper AI Model (লোকাল ট্রানস্ক্রিপশন)",
        options=["tiny", "base", "small"],
        index=0,
        help="'tiny' মডেল CPU-তে সবচেয়ে দ্রুত কাজ করে।"
    )

    st.markdown("---")
    if os.name == 'nt':
        if st.button("📂 আউটপুট ফোল্ডার খুলুন (PC)"):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            subprocess.run(["explorer", OUTPUT_DIR])

# Sync optional Streamlit Cloud Secrets to environment
for _secret_key in ("YOUTUBE_COOKIES", "GEMINI_API_KEY", "YOUTUBE_PROXY"):
    try:
        if _secret_key in st.secrets and not os.environ.get(_secret_key):
            os.environ[_secret_key] = str(st.secrets[_secret_key])
    except Exception:
        pass

# Main Area
st.markdown('<p class="main-title">🎬 AI Video Clipper & Shorts Generator</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">ফোন বা পিসি থেকে যেকোনো বড় ভিডিও আপলোড করুন — AI স্বয়ংক্রিয়ভাবে সেরা ভাইরাল মোমেন্ট খুঁজে ৯:১৬ রিলস/শর্টস বানিয়ে দেবে।</p>', unsafe_allow_html=True)

start_yt_button = False
url_input = ""

if os.name == "nt":
    tab_upload, tab_yt_local = st.tabs([
        "📁 ভিডিও আপলোড (ফোন / পিসি)",
        "📺 ইউটিউব লিংক (Local PC)"
    ])
    with tab_yt_local:
        url_input = st.text_input(
            "ইউটিউব ভিডিও লিংক পেস্ট করুন (লোকাল পিসির নিজের IP দিয়ে ডাউনলোড হবে):",
            placeholder="https://www.youtube.com/watch?v=... বা https://youtu.be/..."
        )
        preview_vid_id = VideoDownloader.extract_video_id(url_input.strip()) if url_input.strip() else None
        if preview_vid_id:
            st.video(f"https://www.youtube.com/watch?v={preview_vid_id}")
        start_yt_button = st.button("⚡ Generate Viral Shorts (YouTube Link)", type="primary", use_container_width=True)
else:
    tab_upload = st.container()

with tab_upload:
    st.info(
        "📱 **ফোন / পিসি থেকে শর্টস বানানোর নিয়ম:**\n\n"
        "১. নিচের **Browse files** বাটনে ট্যাপ করে ফোনের **Files / Downloads / Gallery** বা পিসি থেকে ভিডিও (`.mp4` / `.mov` / `.mkv`) সিলেক্ট করুন।\n"
        "২. ফাইল সিলেক্ট হলে নিচের **'⚡ Generate Viral Shorts'** বাটনে চাপুন।\n"
        "৩. প্রসেস চলাকালীন ব্রাউজার ট্যাবটি খোলা রাখুন—কয়েক মিনিটের মধ্যেই ৯:১৬ শর্টস তৈরি হয়ে যাবে।\n\n"
        "⚠️ **গুরুত্বপূর্ণ (অনলাইন সার্ভার লিমিট):** ভিডিওর দৈর্ঘ্য যেন **১ ঘণ্টা বা তার বেশি না হয়** (১ ঘণ্টার নিচে বা ছোট/মাঝারি ভিডিও দিন), অন্যথায় ফ্রি ক্লাউড সার্ভারের RAM লিমিটের কারণে অ্যাপ ক্র্যাশ করতে পারে।"
    )

    uploaded_file = st.file_uploader(
        "ফোন বা পিসি থেকে ভিডিও আপলোড করুন (MP4 / MOV / MKV / WEBM):",
        type=["mp4", "mov", "mkv", "webm"],
        help="সর্বোচ্চ 400MB পর্যন্ত ভিডিও আপলোড করা যাবে।"
    )
    start_upload_button = st.button("⚡ Generate Viral Shorts", type="primary", use_container_width=True)

if start_upload_button or start_yt_button:
    if start_upload_button and uploaded_file is None:
        st.error("দয়া করে একটি ভিডিও ফাইল আপলোড করুন!")
    elif start_yt_button and not url_input.strip():
        st.error("দয়া করে একটি সঠিক ইউটিউব ভিডিওর লিংক দিন!")
    else:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def on_progress(msg: str, frac: float):
            status_text.info(f"⏳ **{msg}**")
            progress_bar.progress(frac)

        try:
            pipeline = ClipperPipeline(
                base_dir=BASE_DIR,
                gemini_api_key=api_key_input.strip() or None,
                whisper_model=whisper_model,
                gemini_model=selected_gemini_model
            )

            if start_yt_button:
                results = pipeline.process_url(
                    url=url_input.strip(),
                    num_clips=num_clips,
                    min_duration=min_dur,
                    max_duration=max_dur,
                    crop_mode=selected_crop_mode,
                    burn_subtitles=burn_subs,
                    subtitle_color=selected_sub_color,
                    progress_callback=on_progress
                )
            else:
                temp_dir = os.path.join(BASE_DIR, "temp")
                os.makedirs(temp_dir, exist_ok=True)
                upload_path = os.path.join(temp_dir, uploaded_file.name)
                with open(upload_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                results = pipeline.process_file(
                    video_path=upload_path,
                    video_title=os.path.splitext(uploaded_file.name)[0],
                    num_clips=num_clips,
                    min_duration=min_dur,
                    max_duration=max_dur,
                    crop_mode=selected_crop_mode,
                    burn_subtitles=burn_subs,
                    subtitle_color=selected_sub_color,
                    progress_callback=on_progress
                )

            status_text.success("🎉 সবগুলো শর্টস সফলভাবে তৈরি হয়েছে!")
            progress_bar.progress(1.0)
            st.session_state["clips_results"] = results

        except Exception as e:
            st.error(f"❌ এরর দেখা দিয়েছে: {e}")
            st.info("টিপ: ভিডিওতে কথা/অডিও ঠিক আছে কি না তা যাচাই করুন।")

if st.session_state.get("clips_results"):
    results = st.session_state["clips_results"]
    st.markdown("### 🌟 প্রস্তুতকৃত ভাইরাল শর্টস সমূহ:")

    cols = st.columns(min(len(results), 3))
    for idx, clip in enumerate(results):
        col = cols[idx % len(cols)]
        with col:
            st.markdown(f"#### 📌 {clip.get('title', f'Clip {idx+1}')}")
            st.markdown(f"<span class='score-badge'>🔥 Viral Score: {clip.get('viral_score', 90)}/100</span>", unsafe_allow_html=True)
            st.caption(f"⏱️ দৈর্ঘ্য: {clip.get('duration', 0)} সেকেন্ড ({clip.get('start_time', 0)}s - {clip.get('end_time', 0)}s)")
            if clip.get('reason'):
                st.caption(f"💡 কেন ভাইরাল: {clip.get('reason')}")

            file_path = clip.get("output_file")
            if file_path and os.path.exists(file_path):
                st.video(file_path)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label=f"⬇️ ডাউনলোড শর্ট {idx+1}",
                        data=f.read(),
                        file_name=clip.get("filename", f"short_{idx+1}.mp4"),
                        mime="video/mp4",
                        key=f"dl_{idx}"
                    )
