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
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("システム設定が見つかりません。")
    st.stop()

JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')
APP_TITLE = "BE STONE"

st.set_page_config(
    page_title=APP_TITLE, 
    page_icon="logo.png" if os.path.exists("logo.png") else "💎", 
    layout="wide", 
    initial_sidebar_state="auto"
)

# --- 2. 究極のデザインCSS（漆黒文字・ターコイズ・モバイル最適化） ---
st.markdown("""
    <style>
    /* 全体背景とライトモード強制 */
    :root { color-scheme: light !important; }
    .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
    header { visibility: hidden !important; height: 0 !important; }
    .main .block-container { padding-top: 1.5rem !important; }

    /* 全ての文字を真っ黒に固定 */
    .stMarkdown, p, h1, h2, h3, span, label, li, div { color: #000000 !important; }

    /* 1. モバイルサイドバー：横幅75% / 文字色「漆黒」 / デカ文字 / 広間隔 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 75vw !important; min-width: 75vw !important; background-color: #FFFFFF !important; }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {
            color: #000000 !important; font-size: 26px !important; font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            padding: 35px 10px !important; border-bottom: 2px solid #EDF2F7 !important;
        }
    }
    
    @media (min-width: 769px) { .main .block-container { max-width: 850px !important; margin: auto !important; } }

    /* ボタンデザイン：ターコイズブルー (#75C9D7) 統一 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; height: 3.5em !important; font-weight: bold !important;
        box-shadow: none !important; opacity: 1 !important; transition: none !important;
    }
    div.stButton > button * { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }

    .app-card {
        background-color: #FFFFFF !important; padding: 25px; border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.03); border: 1px solid #EDF2F7; margin-bottom: 20px;
    }
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン・同期管理（永続化・ページ維持） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')
saved_page = streamlit_js_eval(js_expressions='localStorage.getItem("active_page")', key='L_PAGE')

# 自動復旧チェック（同期が終わるまでログイン画面を表示しない）
if not st.session_state.logged_in:
    if saved_id is None: # JS実行中
        st_autorefresh(interval=1000, limit=3, key="sync_init")
        st.write("🔄 BE STONE システム同期中...")
        st.stop()
    
    if saved_id and saved_key and str(saved_id) != "null":
        try:
            res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
        except: pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown(f"<h2 style='text-align: center; color: #75C9D7;'>{APP_TITLE} ログイン</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            u_id = st.text_input("STAFF ID")
            u_pw = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                    # JavaScriptでLocalStorageに書き込み
                    streamlit_js_eval(js_expressions=f"localStorage.setItem('staff_id', '{u_id}')")
                    streamlit_js_eval(js_expressions=f"localStorage.setItem('session_key', '{new_key}')")
                    streamlit_js_eval(js_expressions=f"localStorage.setItem('active_page', '📋 本日の業務')")
                    st.session_state.logged_in = True
                    st.session_state.staff_info = res.data[0]
                    st.rerun()
                else: st.error("ID / PW不一致")
    st.stop()

# --- 4. 共通データ同期（ログイン後） ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# セッション有効チェック
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False; st.rerun()

# 同期データ取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# タスク生成（1日1回）
try:
    exist_check = supabase.table("task_logs").select("id").eq("work_date", today_jst).limit(1).execute()
    if not exist_check.data:
        tm_data = supabase.table("task_master").select("*").execute()
        for tm in tm_data.data:
            try: supabase.table("task_logs").insert({"task_id": tm["id"], "work_date": today_jst, "status": "pending"}).execute()
            except: pass
        st.cache_data.clear(); st.rerun()
except: pass

@st.cache_data(ttl=25)
def get_task_logs_direct(today):
    return supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today).execute().data

l_data = get_task_logs_direct(today_jst)
l_data = sorted(l_data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id'] and l['task_master']['target_hour'] == now_jst.hour), None)

if not active_task: st_autorefresh(interval=30000, key="global_ref")
width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH_CHECK', want_output=True)
is_mobile = isinstance(width, (int, float)) and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"### 📍 遂行中: {task['task_master']['locations']['name']}")
    if st.button("⏸️ 中断してリストに戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.cache_data.clear(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    qr_in = st.camera_input("1. 現場QRをスキャン", key=f"qr_{task['id']}")
    if qr_in:
        if decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
        else: st.error("場所が違います")
    if st.session_state.get(qr_v_key):
        ph_in = st.camera_input("2. 完了写真撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告を送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            st.cache_data.clear(); del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    menu_options = ["📋 本日の業務", "⚠️ 未完了タスク", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    
    # ページ維持のための初期値設定
    default_index = 0
    if saved_page in menu_options:
        default_index = menu_options.index(saved_page)
    
    choice = st.radio("MENU", menu_options, index=default_index, key="nav")
    # 選択した瞬間にJSで記憶
    streamlit_js_eval(js_expressions=f"localStorage.setItem('active_page', '{choice}')")
    
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア表示 ---
if is_mobile and active_task and choice == "📋 本日の業務":
    render_task_execution(active_task)
    st.stop()

st.markdown(f"<h1 style='color: #75C9D7; margin-top: 0; margin-bottom: 0;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%H:%M')} | {staff['name']}")

if choice == "📋 本日の業務":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.cache_data.clear(); st.rerun()
    else:
        st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if not on_break:
            if c2.button("☕ 休憩入り", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤打刻", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            st.warning("休憩中")
            if c2.button("🏃 業務戻り", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader(f"📋 今のタスク ({now_jst.hour:02d}時台)")
        tasks_now = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not tasks_now: st.info("予定はありません。")
        else:
            for l in tasks_now:
                st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 20px 0;'>", unsafe_allow_html=True)
                ca, cb = st.columns([3, 1])
                ca.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] in ["pending", "interrupted"]:
                    if cb.button("着手" if l['status']=="pending" else "再開", key=f"s_{l['id']}", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.cache_data.clear(); st.rerun()
                elif l['status'] == "in_progress": st.warning("Busy")
                else: st.success("OK")
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "⚠️ 未完了タスク":
    overdue = [l for l in l_data if l['task_master']['target_hour'] < now_jst.hour and l['status'] != "completed"]
    if not overdue: st.success("全て完了しています！")
    else:
        for l in overdue:
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            ca, cb = st.columns([3, 1])
            ca.write(f"**【遅延】{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d} - {l['task_master']['locations']['name']}**")
            if cb.button("リカバリー", key=f"rec_{l['id']}", use_container_width=True, type="primary"):
                supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.cache_data.clear(); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    res = supabase.table("timecards").select("*, breaks(*)").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    for r in res.data:
        c_in, c_out = datetime.datetime.fromisoformat(r['clock_in_at']), (datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None)
        br_m = sum([int((datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() // 60) for b in r.get('breaks', []) if b['break_end_at']])
        act_m = (int((c_out - c_in).total_seconds() // 60) - br_m) if c_out else 0
        h, m = divmod(act_m, 60)
        t_color = "red" if act_m >= 420 else "#000000"
        st.markdown(f"**📅 {c_in.strftime('%Y年%m月%d日')}** / {c_in.strftime('%H:%M')}〜 / <span style='color:{t_color}; font-weight:bold;'>実働：{h:02d}:{m:02d}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif "Admin" in choice:
    # 以前の管理/出勤簿ロジック
    st.markdown("<div class='app-card'>管理者用機能</div>", unsafe_allow_html=True)