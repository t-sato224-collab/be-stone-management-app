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

# initial_sidebar_stateを"auto"にし、モバイルでもPCでも適切に。
st.set_page_config(page_title="BE STONE Pro", layout="wide", initial_sidebar_state="auto")

# --- 2. 究極のデザインCSS（サイドバー幅75%・デカ文字・黒靄除去） ---
st.markdown("""
    <style>
    /* 全体背景白固定 */
    .stApp { background-color: #FFFFFF !important; color: #1A202C !important; }

    /* 1. 【最重要】モバイルサイドバー横幅 75% 強制 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 75vw !important;
            min-width: 75vw !important;
        }
    }
    
    /* 2. サイドバーメニュー：フォント26px・間隔35px・押し間違い防止 */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        font-size: 26px !important; 
        font-weight: bold !important;
        padding: 35px 10px !important; 
        margin-bottom: 10px !important; 
        border-bottom: 2px solid #E2E8F0 !important;
        color: #1A202C !important;
        display: block !important;
    }

    /* 3. 【ボタン】黒い靄（影）を完全に除去 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #2c3e50 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        height: 3.5em !important;
        width: 100% !important;
        font-weight: bold !important;
        box-shadow: none !important;
        opacity: 1 !important;
        transition: none !important;
    }
    
    /* ボタン内テキストの白固定 */
    div.stButton > button *, [data-testid="stCameraInput"] button * {
        color: #FFFFFF !important;
    }

    /* ログアウトボタン（赤） */
    div.stButton > button[key="logout_btn"] {
        background-color: #E53E3E !important;
    }

    /* 不要パーツ隠蔽 */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン持続・復旧ロジック ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動復旧チェック（同期中でも止めない）
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
    st.markdown("<h2 style='text-align: center;'>🛡️ BE STONE 業務管理</h2>", unsafe_allow_html=True)
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    
    with st.form("login_form"):
        u_id = st.text_input("スタッフID")
        u_pw = st.text_input("パスワード", type="password")
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

# --- 4. データ同期取得（ログイン成功後） ---
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

# 自動更新（30秒ごと）
if not active_task: st_autorefresh(interval=30000, key="global_ref")
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_WIDTH', want_output=True)
is_mobile = width is not None and width < 768

# 共通QRデコード
def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

# --- B. サイドバー（メニューを最初に定義する） ---
# ここを「着手中」でも実行するようにしたのでメニューは消えません
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"<b>{staff['name']} 様</b>", unsafe_allow_html=True)
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_options, key="nav_radio")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア表示 ---
def render_task_execution(task):
    st.markdown(f"### 📍 遂行中: {task['task_master']['locations']['name']}")
    if st.button("⏸️ 中断してリストに戻る"):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    
    if not st.session_state[qr_v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("撮影して認証", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了状態を撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# モバイルで作業中の場合、メイン画面をカメラに。サイドバーは残る。
if is_mobile and active_task and not on_break:
    render_task_execution(active_task)
else:
    # 通常の画面表示
    st.title("BE STONE")
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
                    st.markdown("<div style='border-bottom: 1px solid #E2E8F0; padding: 15px 0;'>", unsafe_allow_html=True)
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
        # 管理者用監視/出勤簿ロジック（Admin権限のみ実行）
        st.title(choice)
        if "監視" in choice:
            l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
            for l in l_adm.data:
                st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
                st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
        else:
            all_s = supabase.table("staff").select("id, name").execute()
            s_dict = {s['name']: s['id'] for s in all_s.data}
            target = st.selectbox("スタッフ", ["-- 全員 --"] + list(s_dict.keys()))
            s_d, e_d = st.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), st.date_input("終了", datetime.date.today())
            q = supabase.table("timecards").select("*").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
            if target != "-- 全員 --": q = q.eq("staff_id", s_dict[target])
            res = q.order("work_date", desc=True).execute()
            if res.data: st.dataframe(pd.DataFrame(res.data), use_container_width=True)