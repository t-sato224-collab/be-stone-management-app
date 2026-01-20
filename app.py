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

# --- 1. システム設定 (アイコン・名前の変更) ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

# アプリの顔（タブ名とアイコン）を設定
APP_NAME = "BE STONE Pro"
LOGO_PATH = "logo.png"

st.set_page_config(
    page_title=APP_NAME,
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "💎",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- 2. 究極のデザインCSS（BE STONE ブランドカラー & モバイル最適化） ---
st.markdown(f"""
    <style>
    /* 全体背景：清潔感のある白 */
    .stApp {{ background-color: #FFFFFF !important; color: #000000 !important; }}
    
    /* 文字色を「漆黒」に強制固定 */
    .stMarkdown, p, h1, h2, h3, span, label, li, div {{ color: #000000 !important; }}

    /* 1. モバイルサイドバー設定：横幅75% / フォント26px / 間隔35px */
    @media (max-width: 768px) {{
        section[data-testid="stSidebar"] {{
            width: 75vw !important;
            min-width: 75vw !important;
            background-color: #FFFFFF !important;
        }}
        /* メニュー項目のテキストを「純黒」に固定 */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {{
            color: #000000 !important;
            font-size: 26px !important;
            font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }}
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
            padding-top: 35px !important;
            padding-bottom: 35px !important;
            border-bottom: 2px solid #EDF2F7 !important;
        }}
    }}

    /* 2. PC版：中央寄せレイアウト */
    @media (min-width: 769px) {{
        .main .block-container {{
            max-width: 850px !important;
            margin: auto !important;
            padding-top: 3rem !important;
        }}
    }}

    /* 3. ボタン：ターコイズブルー (#75C9D7) / 白文字固定 / 黒靄除去 */
    div.stButton > button, [data-testid="stCameraInput"] button {{
        background-color: #75C9D7 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        height: 3.5em !important;
        font-weight: bold !important;
        box-shadow: none !important;
        opacity: 1 !important;
        transition: none !important;
    }}
    div.stButton > button * {{ color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }}

    /* 4. ログアウトボタン（赤） */
    div.stButton > button[key="logout_btn"] {{
        background-color: #E53E3E !important;
        height: 4em !important;
    }}

    /* カードデザイン */
    .app-card {{
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #EDF2F7;
        margin-bottom: 20px;
    }}

    /* 不要パーツ隠蔽 */
    div[data-testid="stSidebarNav"] {{ display: none !important; }}
    footer {{ visibility: hidden !important; }}
    header {{ background: transparent !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン永続化・復旧ロジック ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動復旧（記憶があればDB照合）
if not st.session_state.logged_in and saved_id and saved_key and saved_id != "null":
    try:
        res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except: pass

# --- A. ログイン画面（ブランド統合デザイン） ---
if not st.session_state.logged_in:
    if saved_id is None: # 同期待ち
        st_autorefresh(interval=1000, limit=3, key="sync_init")
        st.stop()

    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, use_container_width=True)
        st.markdown("<h1 style='text-align: center; color: #75C9D7; font-size: 32px;'>BE STONE</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#718096; letter-spacing:2px; font-weight:bold;'>OPERATION MANAGEMENT</p>", unsafe_allow_html=True)
        
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
                else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- 4. 共通データ同期（ログイン成功後） ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# セッション有効性チェック
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
width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH_CHECK', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"<div class='app-card'><h2 style='color:#75C9D7; margin:0;'>📍 遂行中: {task['task_master']['locations']['name']}</h2></div>", unsafe_allow_html=True)
    st.write(f"**指示**: {task['task_master']['task_name']}")
    if st.button("⏸️ 一時中断して戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    if not st.session_state[qr_v_key]:
        st.subheader("1. 現場QRをスキャン")
        qr_in = st.camera_input("シャッターを押して認証", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了状態を撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告を送信して完了", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー（メニュー常に表示・黒文字固定） ---
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, use_container_width=True)
    st.markdown(f"<div style='text-align:center; padding:10px; color:#000000;'><b>{staff['name']} 様</b></div>", unsafe_allow_html=True)
    st.divider()
    menu_options = ["📋 本日の業務", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_options, key="nav_radio")
    for _ in range(8): st.write("")
    st.divider()
    if st.button("🚪 LOGOUT", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メイン表示 ---
st.markdown(f"<h1 style='color: #75C9D7; margin-bottom: 0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%Y/%m/%d %H:%M')} | Staff: {staff['name']}")

if choice == "📋 本日の業務":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
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
    st.markdown("</div>", unsafe_allow_html=True)

    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader(f"📋 TASKS ({now_jst.hour:02d}時台)")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not display_tasks: st.write("予定なし")
        else:
            for l in display_tasks:
                st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 20px 0;'>", unsafe_allow_html=True)
                cola, colb = st.columns([3, 1])
                with cola:
                    st.markdown(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
                    st.write(l['task_master']['task_name'])
                with colb:
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
            st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    st.table([{"日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])

elif "監視" in choice:
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    for l in l_adm.data:
        st.write(f"**{l['task_master']['locations']['name']}**")
        st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")

elif "出勤簿" in choice:
    all_s = supabase.table("staff").select("id, name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    target = st.selectbox("STAFF", ["-- ALL --"] + list(s_dict.keys()))
    s_d, e_d = st.date_input("START", datetime.date.today()-datetime.timedelta(days=30)), st.date_input("END", datetime.date.today())
    q = supabase.table("timecards").select("*").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if target != "-- ALL --": q = q.eq("staff_id", s_dict[target])
    res = q.order("work_date", desc=True).execute()
    if res.data: st.dataframe(pd.DataFrame(res.data), use_container_width=True)