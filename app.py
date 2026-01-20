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

# --- 2. 究極のデザイン設定（CSS：PC中央寄せ・ボタン黒靄除去・モバイル最適化） ---
st.markdown("""
    <style>
    /* 全体背景：白固定 */
    .stApp { background-color: #FFFFFF !important; color: #1A202C !important; }

    /* 1. PC版：メイン画面の中央寄せと幅制限 */
    @media (min-width: 769px) {
        .main .block-container {
            max-width: 800px !important;
            margin: auto !important;
            padding-top: 3rem !important;
        }
        /* 入力ボックス内の文字を中央に */
        input { text-align: center !important; }
    }

    /* 2. モバイル版：サイドバー横幅 75% ＆ デカ文字 ＆ 広間隔 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 75vw !important;
            min-width: 75vw !important;
        }
        /* メニュー項目のカスタマイズ */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            font-size: 26px !important; 
            font-weight: bold !important;
            padding-top: 35px !important; 
            padding-bottom: 35px !important; 
            margin-bottom: 10px !important; 
            border-bottom: 2px solid #f0f2f6 !important;
            color: #1A202C !important;
            display: block !important;
        }
    }

    /* 3. 【ボタン】黒い靄・変色を完全に防ぐ絶対命令 */
    div.stButton > button {
        background-color: #2c3e50 !important; /* 信頼の濃紺 */
        color: #FFFFFF !important;            /* 白文字 */
        border: none !important;
        border-radius: 12px !important;
        height: 3.5em !important;
        width: 100% !important;
        font-weight: bold !important;
        box-shadow: none !important;          /* 黒い影を消去 */
        outline: none !important;
        opacity: 1 !important;                /* 透明度変化を禁止 */
        transition: none !important;          /* アニメーションを停止 */
    }
    
    /* ボタンの中の文字が消えないように強制 */
    div.stButton > button * {
        color: #FFFFFF !important;
        font-size: 1.1rem !important;
    }

    /* ログアウトボタン（赤） */
    div.stButton > button[key="logout_btn"] {
        background-color: #E53E3E !important;
        height: 4.5em !important;
        margin-top: 30px !important;
    }

    /* 4. 不要パーツの隠蔽 */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    header { visibility: visible !important; background: transparent !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン持続・復旧ロジック ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動ログインチェック
if not st.session_state.logged_in and saved_id and saved_key and saved_id != "null":
    try:
        res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except: pass

# --- A. ログイン画面（イメージ図を完全再現） ---
if not st.session_state.logged_in:
    # 同期中のチラつきガード
    if saved_id is None:
        st.write("🔄 システム同期中...")
        st_autorefresh(interval=1000, limit=3, key="sync_init")
        st.stop()

    # ログイン画面中央配置
    c_l, c_main, c_r = st.columns([1, 2, 1])
    with c_main:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("<h1 style='text-align: center; color: #2c3e50; font-size: 36px; margin-bottom: 0;'>BE STONE</h1>", unsafe_allow_html=True)
        
        st.markdown("<p style='text-align:center; color:#718096; letter-spacing:3px; font-size:14px; font-weight:bold; margin-top:-10px;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            u_id = st.text_input("STAFF ID", placeholder="ID")
            u_pw = st.text_input("PASSWORD", type="password", placeholder="PASS")
            # 視認性最強のボタン
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                    # JavaScriptでLocalStorageに書き込み
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")')
                    st.session_state.logged_in = True
                    st.session_state.staff_info = res.data[0]
                    st.rerun()
                else: st.error("IDまたはパスワードが違います")
    st.stop()

# --- 4. 共通データ同期（ログイン成功後） ---
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
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新
if not active_task: st_autorefresh(interval=30000, key="global_ref")
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_WIDTH', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"## 📍 {task['task_master']['locations']['name']}")
    st.info(f"指示: {task['task_master']['task_name']}")
    if st.button("⏸️ 中断してリストに戻る"):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    if not st.session_state[qr_v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("撮影ボタンを押して認証", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了写真を撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告を送信", key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task and not on_break: render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.sidebar.radio("MENU", menu_options, key="nav_radio")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア表示 ---
st.markdown("<h1 style='color: #2c3e50; font-size: 28px; margin-bottom: 0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%H:%M')} / {staff['name']}")

if choice == "📋 本日の業務":
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
            if c3.button("🏁 退勤打刻", use_container_width=True):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            if c2.button("🏃 業務復帰", use_container_width=True):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()

    st.divider()
    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.subheader(f"📋 今日のタスク ({now_jst.hour:02d}時台)")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not display_tasks: st.write("予定なし")
        else:
            for l in display_tasks:
                # 【改善】タスクテキストの最後にボタンを配置するレイアウト
                st.markdown("<div style='border-bottom: 1px solid #E2E8F0; padding: 20px 0;'>", unsafe_allow_html=True)
                col_text, col_btn = st.columns([3, 1])
                with col_text:
                    st.markdown(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
                    st.write(l['task_master']['task_name'])
                with col_btn:
                    if l['status'] == "pending":
                        if st.button("着手", key=f"s_{l['id']}", use_container_width=True):
                            supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                            st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                    elif l['status'] == "interrupted":
                        if st.button("再開", key=f"r_{l['id']}", type="primary", use_container_width=True):
                            supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                            st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                    elif l['status'] == "in_progress": st.warning("対応中")
                    else: st.success("完了")
                st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    st.table([{"日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])

elif "Admin" in choice:
    # 必要に応じて管理者監視ロジックを追加
    st.title(choice)
    if "監視" in choice:
        l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
        for l in l_adm.data:
            st.write(f"**{l['task_master']['locations']['name']}**")
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")