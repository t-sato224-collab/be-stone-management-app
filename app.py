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

# --- 2. 究極の視認性・レイアウト保証CSS（PC中央寄せ・ボタン色強制固定） ---
st.markdown("""
    <style>
    /* 全体背景：白固定 */
    .stApp { background-color: #FFFFFF !important; color: #1A202C !important; }

    /* 【PC限定】メイン画面の中央寄せと幅制限 */
    @media (min-width: 769px) {
        .main .block-container {
            max-width: 850px !important;
            margin: auto !important;
            padding-top: 3rem !important;
        }
    }

    /* 【モバイル限定】サイドバー横幅 75% */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 75vw !important;
            min-width: 75vw !important;
        }
        /* メニュー項目のフォント特大・間隔拡大 */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            font-size: 26px !important; 
            font-weight: bold !important;
            padding: 25px 10px !important; 
            margin-bottom: 20px !important; 
            border-bottom: 2px solid #E2E8F0 !important;
            color: #1A202C !important;
        }
    }

    /* 【ボタン】全てのボタンを黒化から救う絶対命令 */
    div.stButton > button {
        background-color: #2c3e50 !important; /* 濃紺 */
        color: #FFFFFF !important;            /* 白文字 */
        border: none !important;
        border-radius: 12px !important;
        height: 3.2em !important;
        width: 100% !important;
        font-weight: bold !important;
        opacity: 1 !important;
    }
    
    /* ボタンの中の全要素（文字）を白に強制 */
    div.stButton > button * {
        color: #FFFFFF !important;
        font-size: 1.1rem !important;
    }

    /* ログアウトボタンだけは赤色 */
    div.stButton > button[key="logout_btn"] {
        background-color: #E53E3E !important;
        height: 4em !important;
    }

    /* カード形式の装飾（ログイン後の各セクション） */
    .app-card {
        background-color: #FFFFFF;
        padding: 25px;
        border-radius: 15px;
        border: 2px solid #EDF2F7;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-bottom: 25px;
    }

    /* 不要パーツの隠蔽 */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    header { visibility: visible !important; background: transparent !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン持続・復旧ロジック ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶（LocalStorage）を取得
sync_msg = st.empty()
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動復旧チェック
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
    if saved_id is None:
        sync_msg.caption("🔄 認証情報を同期中...")
    
    # PC版：中央に寄せるためのカラム
    c_left, c_main, c_right = st.columns([1, 2, 1])
    with c_main:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<p style='text-align:center; color:#718096; letter-spacing:3px; font-size:12px; font-weight:bold;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            u_id = st.text_input("STAFF ID", placeholder="ID")
            u_pw = st.text_input("PASSWORD", type="password", placeholder="PASS")
            # ここが黒くなってしまうボタンの対策
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
                else: st.error("IDまたはパスワードが違います")
    st.stop()

# --- 4. 共通データ同期（ログイン成功後） ---
sync_msg.empty()
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# セッション有効チェック
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False; st.rerun()

# 各種ステータス取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新
if not active_task: st_autorefresh(interval=30000, key="global_ref")
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_W', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"<div class='app-card'><h2 style='color:#E53E3E; margin:0;'>📍 遂行中: {task['task_master']['locations']['name']}</h2></div>", unsafe_allow_html=True)
    st.write(f"**内容**: {task['task_master']['task_name']}")
    if st.button("⏸️ 一時中断して戻る"):
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
        if ph_in and st.button("✅ 報告を送信", key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"<p style='text-align:center; font-weight:bold;'>{staff['name']} 様</p>", unsafe_allow_html=True)
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_options, key="nav_radio")
    for _ in range(8): st.write("")
    st.divider()
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインコンテンツエリア ---
st.markdown(f"<h1 style='color: #2c3e50; font-size: 28px; margin-bottom:0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%Y/%m/%d %H:%M')}")

if choice == "📋 本日の業務":
    # 勤怠
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
    else:
        st.info(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if not on_break:
            if c2.button("☕ 休憩入り", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤打刻", use_container_width=True):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            st.warning("休憩中")
            if c2.button("🏃 業務復帰", use_container_width=True):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # タスク
    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader(f"📋 TASKS ({now_jst.hour:02d}時台)")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not display_tasks: st.write("予定なし")
        else:
            for l in display_tasks:
                cola, colb = st.columns([3, 1])
                cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] == "pending":
                    if colb.button("着手", key=f"s_{l['id']}"):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                elif l['status'] == "interrupted":
                    if colb.button("再開", key=f"r_{l['id']}"):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                elif l['status'] == "in_progress": colb.warning("対応中")
                else: colb.success("完了")
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("HISTORY")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    st.table([{"日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])
    st.markdown("</div>", unsafe_allow_html=True)

elif "監視" in choice:
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    for l in l_adm.data:
        with st.container():
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
            st.markdown("</div>", unsafe_allow_html=True)

elif "出勤簿" in choice:
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("ATTENDANCE DATA")
    all_s = supabase.table("staff").select("id, name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    target = st.selectbox("スタッフ", ["-- 全員 --"] + list(s_dict.keys()))
    s_d, e_d = st.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), st.date_input("終了", datetime.date.today())
    q = supabase.table("timecards").select("*").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if target != "-- 全員 --": q = q.eq("staff_id", s_dict[target])
    res = q.order("work_date", desc=True).execute()
    if res.data:
        df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "未"} for r in res.data])
        st.dataframe(df, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)