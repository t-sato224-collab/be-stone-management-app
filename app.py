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

st.set_page_config(page_title="BE STONE 管理 Pro", layout="wide", initial_sidebar_state="expanded")

# --- 2. 究極のブランド・デザイン（CSS） ---
# ロゴの色（ターコイズブルー）をアクセントに使用
st.markdown("""
    <style>
    /* 全体背景 */
    .stApp { background-color: #f8f9fa !important; }
    
    /* ヘッダー・フッター隠蔽 */
    div[data-testid="stSidebarNav"] { display: none; }
    header { visibility: hidden; }
    footer { visibility: hidden; }

    /* カードデザイン（共通） */
    .app-card {
        background-color: white;
        padding: 25px;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.05);
        margin-bottom: 25px;
        border: 1px solid #edf2f7;
    }

    /* PC版：中央寄せとコンパクト設計 */
    @media (min-width: 769px) {
        .main .block-container {
            max-width: 800px !important;
            margin: auto !important;
            padding-top: 5vh !important;
        }
        [data-testid="stForm"] {
            border: none !important;
            background-color: white !important;
            border-radius: 20px !important;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1) !important;
            padding: 40px !important;
        }
    }

    /* モバイル版：サイドバーと操作系 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 75vw !important; min-width: 75vw !important; }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            font-size: 24px !important; font-weight: bold !important;
            padding: 25px 10px !important; margin-bottom: 15px !important;
            border-bottom: 2px solid #f0f2f6 !important;
        }
    }

    /* ボタン・入力系統 */
    div.stButton > button {
        border-radius: 12px !important;
        font-weight: bold !important;
        transition: 0.3s !important;
    }
    div.stButton > button[key="logout_btn"] {
        background-color: #ff4b4b !important; color: white !important;
        height: 4em !important; font-size: 20px !important; margin-top: 30px !important;
    }
    input { text-align: center !important; border-radius: 10px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン永続化・自動復旧 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

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
    # センター配置
    left_spacer, center_content, right_spacer = st.columns([1, 2, 1])
    with center_content:
        # ロゴ表示
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("<h1 style='text-align: center; color: #75C9D7;'>BE STONE</h1>", unsafe_allow_html=True)
        
        st.markdown("<p style='text-align: center; color: #7f8c8d; letter-spacing: 2px;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
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
                else: st.error("Authentication Failed")
    st.stop()

# --- 4. 共通データ同期（ログイン後） ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# グローバルログアウトチェック
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False; st.rerun()

# 同期データ
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

if not active_task: st_autorefresh(interval=30000, key="global_ref")

# モバイル判定
width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH_CHECK', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); det = cv2.QRCodeDetector()
        val, _, _ = det.detectAndDecode(opencv_image)
        return val
    except: return ""

def render_task_execution(task):
    st.markdown(f"<div class='app-card'><h2 style='color:#e74c3c; margin:0;'>📍 遂行中: {task['task_master']['locations']['name']}</h2></div>", unsafe_allow_html=True)
    st.info(f"指示: {task['task_master']['task_name']}")
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
        if ph_in and st.button("✅ 完了報告を送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    st.markdown(f"<p style='text-align:center; font-weight:bold; color:#2c3e50;'>{staff['name']} 様</p>", unsafe_allow_html=True)
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin':
        menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_options, key="nav_radio")
    
    for _ in range(8): st.write("")
    st.divider()
    if st.button("🚪 LOGOUT", use_container_width=True, key="logout_btn"):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. コンテンツエリア ---
st.markdown(f"<h1 style='color: #2c3e50; font-size: 24px; margin-bottom:0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"Server Time: {now_jst.strftime('%Y/%m/%d %H:%M')}")

if choice == "📋 本日の業務":
    # 勤怠カード
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
    else:
        st.info(f"出勤中: {curr_card['clock_in_at'][11:16]}")
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
        st.subheader(f"📋 TASKS - {now_jst.hour:02d}:00")
        if not l_data:
            tms = supabase.table("task_master").select("*").execute()
            for tm in tms.data:
                try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
                except: pass
            st.rerun()
        
        for l in [x for x in l_data if x['task_master']['target_hour'] == now_jst.hour]:
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
            elif l['status'] == "in_progress" and l['staff_id'] == staff['id']: colb.warning("遂行中")
            elif l['status'] == "in_progress": colb.error("他者対応")
            else: colb.success("完了")
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("YOUR HISTORY")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(15).execute()
    st.dataframe(pd.DataFrame(h_res.data)[['work_date', 'clock_in_at', 'clock_out_at']], use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif "監視" in choice:
    st.subheader("REALTIME MONITORING")
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    cols = st.columns(4)
    for i, l in enumerate(l_adm.data):
        with cols[i % 4]:
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])
            st.markdown("</div>", unsafe_allow_html=True)

elif "出勤簿" in choice:
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("ATTENDANCE REPORT")
    # CSV出力ロジック（前回の完成版を継承）
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("STAFF", ["-- ALL --"] + list(s_dict.keys()))
    s_d, e_d = cb.date_input("START", datetime.date.today()-datetime.timedelta(days=30)), cc.date_input("END", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- ALL --": q = q.eq("staff_id", s_dict[t_staff])
    data = q.order("work_date", desc=True).execute()
    if data.data:
        df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in data.data])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 DOWNLOAD CSV", df.to_csv(index=False).encode('utf_8_sig'), "attendance.csv", "text/csv")
    st.markdown("</div>", unsafe_allow_html=True)