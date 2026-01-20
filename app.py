import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd
import uuid
from streamlit_js_eval import streamlit_js_eval
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="BE STONE Pro", layout="wide", initial_sidebar_state="auto")

# --- 2. 視認性最優先CSS（モバイル横幅・文字色・ボタン） ---
st.markdown("""
    <style>
    /* 1. モバイルサイドバー：横幅75% / 文字色「漆黒」 */
    @media (max-width: 768px) {
        [data-testid="stSidebar"] {
            min-width: 75vw !important;
            max-width: 75vw !important;
        }
        /* メニュー項目の文字を絶対的に黒にする */
        [data-testid="stSidebar"] .stRadio label p {
            color: #000000 !important;
            font-size: 24px !important;
            font-weight: bold !important;
            padding: 20px 0 !important;
        }
    }

    /* 2. PC版：中央寄せレイアウト */
    @media (min-width: 769px) {
        .main .block-container {
            max-width: 800px !important;
            margin: auto !important;
        }
    }

    /* 3. ボタン：黒靄（もや）を物理的に消去 / ターコイズブルー固定 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        height: 3.5em !important;
        box-shadow: none !important;
        text-shadow: none !important;
        opacity: 1 !important;
    }
    div.stButton > button:hover, div.stButton > button:active {
        background-color: #5BAEB8 !important;
        color: #FFFFFF !important;
    }
    /* ボタンの中の全テキストを白に固定 */
    div.stButton > button * { color: #FFFFFF !important; }

    /* 4. ログアウトボタン（赤） */
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }

    /* 不要パーツ隠蔽 */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン管理（自動復旧） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動ログイン（記憶があればDB照合）
if not st.session_state.logged_in and saved_id and saved_key:
    if saved_id != "null" and saved_key != "null":
        try:
            res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
        except: pass

# --- A. ログイン画面（絶対に表示させる） ---
if not st.session_state.logged_in:
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        st.markdown("<h1 style='text-align: center; color: #75C9D7;'>BE STONE</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#718096; font-weight:bold;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            u_id = st.text_input("STAFF ID")
            u_pw = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")')
                    st.session_state.logged_in = True
                    st.session_state.staff_info = res.data[0]
                    st.rerun()
                else: st.error("ID / PW MISMATCH")
    st.stop()

# --- 4. 共通データ取得（ログイン後） ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# 同期データ取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごと）
if not active_task: st_autorefresh(interval=30000, key="global_ref")
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_WIDTH_CHECK', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"### 📍 遂行中: {task['task_master']['locations']['name']}")
    if st.button("⏸️ 中断してリストに戻る"):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    v_key = f"qr_v_{task['id']}"
    if v_key not in st.session_state: st.session_state[v_key] = False
    if not st.session_state[v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("QR撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了写真", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task and not on_break: render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    choice = st.radio("MENU", ["📋 本日の業務", "🕒 履歴"] + (["📊 監視(Admin)", "📅 出勤簿(Admin)"] if staff['role'] == 'admin' else []), key="nav")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア表示 ---
st.markdown("<h1 style='color: #75C9D7;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%Y/%m/%d %H:%M')} | {staff['name']}")

if choice == "📋 本日の業務":
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 打刻(IN)", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
    else:
        st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if not on_break:
            if c2.button("☕ 休憩", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤", use_container_width=True):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            if c2.button("🏃 復帰", use_container_width=True):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()

    st.divider()
    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.subheader(f"📋 今日のタスク")
        for l in [x for x in l_data if x['task_master']['target_hour'] == now_jst.hour]:
            st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 15px 0;'>", unsafe_allow_html=True)
            cola, colb = st.columns([3, 1])
            with cola:
                st.markdown(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
                st.write(l['task_master']['task_name'])
            with colb:
                if l['status'] == "pending":
                    if st.button("着手", key=f"s_{l['id']}", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.rerun()
                elif l['status'] == "interrupted":
                    if st.button("再開", key=f"r_{l['id']}", type="primary", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.rerun()
                elif l['status'] == "in_progress": st.warning("対応中")
                else: st.success("完了")
            st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    st.table([{"日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])

elif "Admin" in choice:
    # 以前の管理/監視ロジック
    st.write("Admin Data")