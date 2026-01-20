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

st.set_page_config(page_title="BE STONE Pro", layout="wide", initial_sidebar_state="expanded")

# --- 2. 視認性100%保証CSS（色の強制固定とメニューボタン復活） ---
st.markdown("""
    <style>
    /* 1. 全体：背景白、文字色を黒に強制固定 */
    .stApp { background-color: #FFFFFF !important; color: #1A202C !important; }
    
    /* 全てのテキスト・マークダウンの視認性を確保 */
    .stMarkdown, p, h1, h2, h3, span, label, li { color: #1A202C !important; }

    /* 2. サイドバーのデザイン：背景を薄いグレーに、文字を黒に */
    section[data-testid="stSidebar"] {
        background-color: #F7FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown, 
    section[data-testid="stSidebar"] label, 
    section[data-testid="stSidebar"] span {
        color: #1A202C !important;
    }

    /* 3. モバイル：サイドバー横幅 75% ＆ メニューの巨大化 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 75vw !important;
            min-width: 75vw !important;
        }
        /* ラジオボタンの間隔とサイズ */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            font-size: 22px !important; 
            font-weight: bold !important;
            padding: 20px 10px !important; 
            margin-bottom: 15px !important;
            border-bottom: 2px solid #E2E8F0 !important;
        }
    }

    /* 4. PC：中央寄せコンパクト設計 */
    @media (min-width: 769px) {
        .main .block-container {
            max-width: 800px !important;
            margin: auto !important;
            padding-top: 5vh !important;
        }
    }

    /* 5. カードデザイン：枠線をはっきりさせる */
    .app-card {
        background-color: #FFFFFF !important;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
        margin-bottom: 20px;
        border: 2px solid #EDF2F7 !important;
    }

    /* 6. ログアウトボタン：視認性重視の赤色 */
    div.stButton > button[key="logout_btn"] {
        background-color: #E53E3E !important;
        color: #FFFFFF !important;
        height: 3.5em !important;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 10px !important;
    }

    /* 7. 不要パーツの処理（メニューボタンは残す） */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden; }
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン永続化・自動復旧 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# LocalStorage読み込み
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

if not st.session_state.logged_in and saved_id and saved_key and saved_id != "null":
    try:
        res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except: pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    left_sp, center_co, right_sp = st.columns([1, 2, 1])
    with center_co:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("<h1 style='text-align: center;'>BE STONE</h1>", unsafe_allow_html=True)
        
        st.markdown("<p style='text-align: center; color: #718096; letter-spacing: 2px; font-weight: bold;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            u_id = st.text_input("スタッフID (STAFF ID)")
            u_pw = st.text_input("パスワード (PASSWORD)", type="password")
            if st.form_submit_button("ログイン (SYSTEM LOGIN)", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")')
                    st.session_state.logged_in = True
                    st.session_state.staff_info = res.data[0]
                    st.rerun()
                else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- 4. 共通データ同期 ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# グローバルログアウトチェック
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False; st.rerun()

# ステータス取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

if not active_task: st_autorefresh(interval=30000, key="global_ref")

# モバイル判定
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_WIDTH', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); det = cv2.QRCodeDetector()
        val, _, _ = det.detectAndDecode(opencv_image)
        return val
    except: return ""

def render_task_execution(task):
    st.markdown(f"<div class='app-card'><h2 style='color:#E53E3E; margin:0;'>📍 遂行中: {task['task_master']['locations']['name']}</h2></div>", unsafe_allow_html=True)
    st.write(f"**指示内容**: {task['task_master']['task_name']}")
    if st.button("⏸️ 一時中断して戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    if not st.session_state[qr_v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("QR撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了写真", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告を送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー（高コントラスト設計） ---
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("メニュー (MENU)", menu_options, key="nav_radio")
    for _ in range(5): st.write("") # 適度な間隔
    st.divider()
    if st.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. コンテンツエリア ---
st.markdown(f"<h1 style='margin-bottom:0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"Time: {now_jst.strftime('%H:%M')} | Staff: {staff['name']}")

if choice == "📋 本日の業務":
    # 勤怠カード
    with st.container():
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader("🕙 タイムカード")
        c1, c2, c3 = st.columns(3)
        if not curr_card:
            if c1.button("🚀 出勤打刻", use_container_width=True):
                supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
        else:
            st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
            if not on_break:
                if c2.button("☕ 休憩入り", use_container_width=True):
                    supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
                if c3.button("🏁 退勤打刻", use_container_width=True, type="primary"):
                    supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
            else:
                st.warning("休憩中")
                if c2.button("🏃 業務復帰", use_container_width=True, type="primary"):
                    supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # タスクカード
    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader(f"📋 予定タスク ({now_jst.hour:02d}時台)")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not display_tasks: st.write("この時間の予定はありません。")
        else:
            for l in display_tasks:
                cola, colb = st.columns([3, 1])
                cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] == "pending":
                    if colb.button("着手", key=f"s_{l['id']}", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                elif l['status'] == "interrupted":
                    if colb.button("再開", key=f"r_{l['id']}", type="primary", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                elif l['status'] == "in_progress" and l['staff_id'] == staff['id']: colb.warning("作業中")
                elif l['status'] == "in_progress": colb.error("他者対応")
                else: colb.success("完了")
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("勤怠履歴 (Attendance Log)")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    st.table([{"日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])
    st.markdown("</div>", unsafe_allow_html=True)

elif "監視" in choice:
    st.subheader("リアルタイム写真監視")
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    for l in l_adm.data:
        with st.container():
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
            st.markdown("</div>", unsafe_allow_html=True)

elif "出勤簿" in choice:
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("出勤簿データ抽出")
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("スタッフ選択", ["-- 全員 --"] + list(s_dict.keys()))
    s_d, e_d = cb.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), cc.date_input("終了", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
    data = q.order("work_date", desc=True).execute()
    if data.data:
        df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in data.data])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 CSVダウンロード", df.to_csv(index=False).encode('utf_8_sig'), "attendance.csv", "text/csv")
    st.markdown("</div>", unsafe_allow_html=True)