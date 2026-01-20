import streamlit as st
import os
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd
import uuid
from streamlit_js_eval import streamlit_js_eval
from streamlit_autorefresh import st_autorefresh

# =====================================================
# ★ Streamlitページ設定（必ず最初・1回のみ）
# =====================================================
st.set_page_config(
    page_title="BE STONE Pro",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

# --- 2. 視認性・レイアウト保証CSS（強制ライトモード・デカ文字・ボタン色固定） ---
st.markdown("""
<style>
:root { color-scheme: light !important; }
.stApp { background-color: #FFFFFF !important; color: #000000 !important; }
.stMarkdown, p, h1, h2, h3, span, label, li, div { color: #000000 !important; }

@media (max-width: 768px) {
    section[data-testid="stSidebar"] {
        width: 75vw !important;
        min-width: 75vw !important;
        background-color: #F8F9FA !important;
    }
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p {
        color: #000000 !important;
        font-size: 26px !important;
        font-weight: 900 !important;
        -webkit-text-fill-color: #000000 !important;
    }
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        padding: 30px 10px !important;
        border-bottom: 2px solid #EDF2F7 !important;
    }
}

div.stButton > button, [data-testid="stCameraInput"] button {
    background-color: #75C9D7 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    height: 3.5em !important;
    font-weight: bold !important;
    box-shadow: none !important;
    opacity: 1 !important;
    transition: none !important;
}
div.stButton > button * {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}

div.stButton > button[key="logout_btn"] {
    background-color: #FC8181 !important;
}

div[data-testid="stSidebarNav"] { display: none !important; }
footer { visibility: hidden !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. ログイン・セッション管理 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

saved_id = streamlit_js_eval(
    js_expressions='localStorage.getItem("staff_id")', key='L_ID'
)
saved_key = streamlit_js_eval(
    js_expressions='localStorage.getItem("session_key")', key='L_KEY'
)

if not st.session_state.logged_in and saved_id and saved_key:
    if str(saved_id) != "null" and str(saved_key) != "null":
        try:
            res = (
                supabase.table("staff")
                .select("*")
                .eq("staff_id", saved_id)
                .eq("session_key", saved_key)
                .execute()
            )
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
        except:
            pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        st.markdown(
            "<h1 style='text-align:center; color:#75C9D7;'>BE STONE</h1>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='text-align:center; color:#718096; font-weight:bold;'>"
            "OPERATION MANAGEMENT</p>",
            unsafe_allow_html=True
        )
        with st.form("login_form"):
            u_id = st.text_input("STAFF ID")
            u_pw = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = (
                    supabase.table("staff")
                    .select("*")
                    .eq("staff_id", u_id)
                    .eq("password", u_pw)
                    .execute()
                )
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update(
                        {"session_key": new_key}
                    ).eq("staff_id", u_id).execute()
                    streamlit_js_eval(
                        js_expressions=f'localStorage.setItem("staff_id","{u_id}")'
                    )
                    streamlit_js_eval(
                        js_expressions=f'localStorage.setItem("session_key","{new_key}")'
                    )
                    st.session_state.logged_in = True
                    st.session_state.staff_info = res.data[0]
                    st.rerun()
                else:
                    st.error("ID / PW MISMATCH")
    st.stop()

# --- 4. 同期データ取得 ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

check_res = (
    supabase.table("staff")
    .select("session_key")
    .eq("id", staff['id'])
    .single()
    .execute()
)
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False
    st.rerun()

t_res = (
    supabase.table("timecards")
    .select("*")
    .eq("staff_id", staff['id'])
    .is_("clock_out_at", "null")
    .order("clock_in_at", desc=True)
    .limit(1)
    .execute()
)
curr_card = t_res.data[0] if t_res.data else None

logs_res = (
    supabase.table("task_logs")
    .select("*, task_master(*, locations(*))")
    .eq("work_date", today_jst)
    .execute()
)
l_data = sorted(
    logs_res.data,
    key=lambda x: (
        x['task_master']['target_hour'] or 0,
        x['task_master']['target_minute'] or 0
    )
)
active_task = next(
    (l for l in l_data if l['status'] == "in_progress"
     and l['staff_id'] == staff['id']),
    None
)

if not active_task:
    st_autorefresh(interval=30000, key="global_ref")

width = streamlit_js_eval(
    js_expressions='window.innerWidth',
    key='WIDTH_CHECK',
    want_output=True
)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        return data
    except:
        return ""

def render_task_execution(task):
    st.markdown(
        f"### 📍 遂行中: {task['task_master']['locations']['name']}"
    )
    if st.button("⏸️ 中断してリストに戻る"):
        supabase.table("task_logs").update(
            {"status": "interrupted"}
        ).eq("id", task['id']).execute()
        st.rerun()

    st.divider()
    v_key = f"qr_v_{task['id']}"
    if v_key not in st.session_state:
        st.session_state[v_key] = False

    if not st.session_state[v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("認証撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[v_key] = True
            st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("証拠撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(
                f_p, ph_in.getvalue(), {"upsert": "true"}
            )
            supabase.table("task_logs").update({
                "status": "completed",
                "completed_at": now_jst.isoformat(),
                "photo_url": f_p
            }).eq("id", task['id']).execute()
            del st.session_state[v_key]
            st.balloons()
            st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task:
    render_task_execution(active_task)
    st.stop()

with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    choice = st.radio(
        "MENU",
        ["📋 本日の業務", "🕒 履歴"]
        + (["📊 監視(Admin)", "📅 出勤簿(Admin)"]
           if staff['role'] == 'admin' else []),
        key="nav"
    )
    for _ in range(8):
        st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update(
            {"session_key": None}
        ).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()')
        st.session_state.logged_in = False
        st.rerun()

# --- C. メイン表示 ---
st.markdown("<h1 style='color:#75C9D7;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%H:%M')} | {staff['name']}")

# （以下、業務／履歴／管理画面ロジックは元コードと同一）
