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
st.markdown('<p class="sub-title">বড় ইউটিউব ভিডিওর লিংক দিন — বিল্ট-ইন IDM ডাউনলোডার দিয়ে ভিডিও নামান অথবা সরাসরি ৯:১৬ ভাইরাল রিলস/শর্টস বানান।</p>', unsafe_allow_html=True)

tab_yt, tab_upload = st.tabs([
    "📺 ইউটিউব ডাউনলোডার ও শর্টস (IDM)",
    "📁 ভিডিও আপলোড (ফোন / পিসি)"
])

DEFAULT_FORMATS = [
    {"key": "1080p", "label": "🎬 1080p Full HD (MP4)", "height": 1080, "audio_only": False, "ext": "mp4"},
    {"key": "720p", "label": "🎬 720p HD (MP4) — প্রস্তাবিত", "height": 720, "audio_only": False, "ext": "mp4"},
    {"key": "480p", "label": "📱 480p SD (MP4)", "height": 480, "audio_only": False, "ext": "mp4"},
    {"key": "360p", "label": "⚡ 360p Compact (MP4)", "height": 360, "audio_only": False, "ext": "mp4"},
    {"key": "audio", "label": "🎵 Audio Only (M4A)", "height": 0, "audio_only": True, "ext": "m4a"},
]

if "idm_formats" not in st.session_state:
    st.session_state["idm_formats"] = {}

idm_dl_button = False
clip_from_idm_button = False
selected_fmt = DEFAULT_FORMATS[1]
num_connections = 8

with tab_yt:
    url_input = st.text_input(
        "ইউটিউব ভিডিও লিংক পেস্ট করুন:",
        placeholder="https://www.youtube.com/watch?v=... বা https://youtu.be/...",
        help="YouTube অ্যাপ থেকে Share → Copy link করে এখানে পেস্ট করুন।"
    )
    preview_vid_id = VideoDownloader.extract_video_id(url_input.strip()) if url_input.strip() else None
    clean_yt_url = f"https://www.youtube.com/watch?v={preview_vid_id}" if preview_vid_id else ""

    if preview_vid_id:
        st.video(clean_yt_url)

        st.markdown("#### 🚀 বিল্ট-ইন IDM ডাউনলোডার ও প্রসেসর")
        grab_col, info_col = st.columns([1, 2])
        with grab_col:
            grab_btn = st.button("🔍 কোয়ালিটি ও সাইজ চেক করুন", use_container_width=True)
        if grab_btn:
            with st.spinner("ভিডিওর ফরম্যাট ও সাইজ স্ক্যান করা হচ্ছে..."):
                try:
                    dl_probe = VideoDownloader(temp_dir=os.path.join(BASE_DIR, "temp"))
                    meta = dl_probe.list_available_formats(clean_yt_url)
                    st.session_state["idm_formats"][preview_vid_id] = meta
                except Exception as grab_err:
                    st.warning(f"ফরম্যাট স্ক্যান করা যায়নি (ডিফল্ট কোয়ালিটি ব্যবহার করুন): {grab_err}")

        cached_meta = st.session_state["idm_formats"].get(preview_vid_id)
        if cached_meta:
            with info_col:
                st.caption(f"📌 **{cached_meta.get('title', '')}** | চ্যানেল: {cached_meta.get('channel', 'N/A')}")
            fmt_options = cached_meta.get("formats") or DEFAULT_FORMATS
        else:
            fmt_options = DEFAULT_FORMATS

        q_col, c_col = st.columns([2, 1])
        with q_col:
            default_idx = next((i for i, f in enumerate(fmt_options) if f["key"] == "720p"), 0)
            selected_fmt = st.selectbox(
                "কোয়ালিটি সিলেক্ট করুন:",
                options=fmt_options,
                index=default_idx,
                format_func=lambda f: f["label"]
            )
        with c_col:
            num_connections = st.select_slider(
                "ডাউনলোড থ্রেড (IDM):",
                options=[1, 4, 8, 12],
                value=8,
                help="একসাথে কয়টি কানেকশনে ফাইল সেগমেন্ট ডাউনলোড হবে (IDM-এর মতো)।"
            )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            start_yt_button = st.button("⚡ ডাউনলোড ও অটো শর্টস বানান", type="primary", use_container_width=True)
        with btn_col2:
            idm_dl_button = st.button("⬇️ শুধু ডাউনলোড করুন (IDM)", use_container_width=True)

        # Show saved IDM download result if already downloaded for this video
        dl_res = st.session_state.get("idm_downloaded")
        if dl_res and dl_res.get("video_id") == preview_vid_id and os.path.exists(dl_res.get("file_path", "")):
            st.success(
                f"✅ ডাউনলোড সম্পন্ন: **{dl_res['title']}** "
                f"({dl_res['size_mb']} MB | ইঞ্জিন: `{dl_res['engine']}`)"
            )
            dl_file_path = dl_res["file_path"]
            safe_name = "".join(c for c in dl_res["title"] if c.isalnum() or c in (" ", "_", "-")).strip() or preview_vid_id
            dl_filename = f"{safe_name[:50]}.{dl_res['ext']}"
            mime_type = "audio/mp4" if dl_res["ext"] == "m4a" else "video/mp4"

            save_col1, save_col2 = st.columns(2)
            with save_col1:
                with open(dl_file_path, "rb") as df:
                    st.download_button(
                        label=f"💾 ফোনে / পিসিতে সেভ করুন (.{dl_res['ext'].upper()})",
                        data=df.read(),
                        file_name=dl_filename,
                        mime=mime_type,
                        use_container_width=True,
                        key=f"idm_save_{preview_vid_id}"
                    )
            with save_col2:
                if dl_res["ext"] != "m4a":
                    clip_from_idm_button = st.button(
                        "🎬 এই ভিডিও দিয়ে ভাইরাল শর্টস বানান",
                        type="primary",
                        use_container_width=True
                    )
    else:
        start_yt_button = st.button("⚡ ডাউনলোড ও অটো শর্টস বানান", type="primary", use_container_width=True)
        st.info(
            "📱 **ফোন ও পিসি থেকে ব্যবহারের নিয়ম:**\n\n"
            "১. YouTube অ্যাপে ভিডিওর **Share → Copy link** চাপুন এবং উপরের বক্সে পেস্ট করুন।\n"
            "২. ভিডিও প্রিভিউ এলে **কোয়ালিটি (1080p / 720p / 480p / Audio)** বেছে **'⬇️ শুধু ডাউনলোড করুন (IDM)'** অথবা **'⚡ ডাউনলোড ও অটো শর্টস বানান'** চাপুন।\n"
            "৩. শুধু ডাউনলোড করলে **'💾 ফোনে / পিসিতে সেভ করুন'** বাটন দিয়ে সরাসরি ফোনের Downloads/Gallery-তে সেভ করতে পারবেন।"
        )

with tab_upload:
    st.info(
        "📱 **ফোন / পিসি থেকে শর্টস বানানোর নিয়ম:**\n\n"
        "১. নিচের **Browse files** বাটনে ট্যাপ করে ফোনের **Files / Downloads / Gallery** থেকে ভিডিও (`.mp4`) সিলেক্ট করুন।\n"
        "২. ফাইল সিলেক্ট হলে নিচের **'⚡ Generate Viral Shorts (Upload)'** বাটনে চাপুন।\n"
        "৩. প্রসেস চলাকালীন ব্রাউজার ট্যাবটি খোলা রাখুন—কয়েক মিনিটের মধ্যেই ৯:১৬ শর্টস তৈরি হয়ে যাবে।"
    )
    uploaded_file = st.file_uploader(
        "ফোন বা পিসি থেকে ভিডিও আপলোড করুন (MP4 / MOV / MKV / WEBM):",
        type=["mp4", "mov", "mkv", "webm"],
        help="সর্বোচ্চ 400MB পর্যন্ত ভিডিও আপলোড করা যাবে।"
    )
    start_upload_button = st.button("⚡ Generate Viral Shorts (Upload)", type="primary", use_container_width=True)

if idm_dl_button:
    if not clean_yt_url:
        st.error("দয়া করে একটি সঠিক ইউটিউব ভিডিওর লিংক দিন!")
    else:
        idm_progress = st.progress(0.0)
        idm_status = st.empty()

        def on_idm_progress(frac: float, msg: str):
            idm_status.info(f"⏳ **{msg}**")
            idm_progress.progress(max(0.0, min(1.0, float(frac))))

        try:
            downloader = VideoDownloader(temp_dir=os.path.join(BASE_DIR, "temp"))
            dl_info = downloader.download_media(
                url=clean_yt_url,
                target_height=selected_fmt["height"],
                audio_only=selected_fmt["audio_only"],
                num_connections=num_connections,
                progress_callback=on_idm_progress,
            )
            dl_info["video_id"] = preview_vid_id
            st.session_state["idm_downloaded"] = dl_info
            st.rerun()
        except Exception as e:
            err_msg = str(e)
            if "403" in err_msg or "not a bot" in err_msg.lower() or "cookies" in err_msg.lower():
                st.warning(
                    "🔒 ক্লাউড সার্ভারের শেয়ার্ড IP থেকে YouTube এই ভিডিওটি ব্লক করেছে।\n\n"
                    "**সমাধান:**\n"
                    "• লোকাল পিসি থেকে `Run_Clipper_UI.bat` / `streamlit run streamlit_app.py` চালালে আপনার নিজের IP-তে ১০০% ডাউনলোড হবে, অথবা\n"
                    "• Streamlit Secrets-এ একটি `YOUTUBE_PROXY` যোগ করুন, অথবা\n"
                    "• আপনার কাছে ভিডিও থাকলে **'📁 ভিডিও আপলোড (ফোন / পিসি)'** ট্যাব ব্যবহার করুন।"
                )
                with st.expander("টেকনিক্যাল এরর ডিটেইলস"):
                    st.code(err_msg)
            else:
                st.error(f"❌ ডাউনলোড এরর: {err_msg}")

if start_yt_button or start_upload_button or clip_from_idm_button:
    if start_yt_button and not url_input.strip():
        st.error("দয়া করে একটি সঠিক ইউটিউব ভিডিওর লিংক দিন!")
    elif start_upload_button and uploaded_file is None:
        st.error("দয়া করে একটি ভিডিও ফাইল আপলোড করুন!")
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
                whisper_model=whisper_model
            )

            if clip_from_idm_button and st.session_state.get("idm_downloaded"):
                dl_res = st.session_state["idm_downloaded"]
                results = pipeline.process_file(
                    video_path=dl_res["file_path"],
                    video_title=dl_res.get("title", "YouTube Video"),
                    num_clips=num_clips,
                    min_duration=min_dur,
                    max_duration=max_dur,
                    crop_mode=selected_crop_mode,
                    burn_subtitles=burn_subs,
                    subtitle_color=selected_sub_color,
                    progress_callback=on_progress
                )
            elif start_yt_button:
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
            err_msg = str(e)
            if "403" in err_msg or "not a bot" in err_msg.lower() or "cookies" in err_msg.lower():
                st.warning(
                    "🔒 ক্লাউড সার্ভারের শেয়ার্ড IP থেকে YouTube সরাসরি ডাউনলোড ব্লক করেছে।\n\n"
                    "**সমাধান:**\n"
                    "• আপনার পিসিতে `Run_Clipper_UI.bat` (অথবা `streamlit run streamlit_app.py`) চালালে নিজের IP-তে সরাসরি ডাউনলোড ও প্রসেস হবে।\n"
                    "• ক্লাউডে চালাতে Streamlit Secrets-এ `YOUTUBE_PROXY` যোগ করুন, অথবা **'📁 ভিডিও আপলোড (ফোন / পিসি)'** ট্যাব থেকে ভিডিও দিন।"
                )
                with st.expander("টেকনিক্যাল এরর ডিটেইলস"):
                    st.code(err_msg)
            else:
                st.error(f"❌ এরর দেখা দিয়েছে: {err_msg}")
                st.info("টিপ: ভিডিওতে কথা/অডিও ঠিক আছে কি না অথবা লিংকটি সঠিক কি না তা যাচাই করুন।")

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
