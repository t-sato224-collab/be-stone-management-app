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

st.set_page_config(page_title="BE STONE Pro", page_icon="logo.png", layout="wide", initial_sidebar_state="auto")

# --- 2. 視認性最優先・ブランドデザインCSS（漆黒文字・ターコイズ・75%幅） ---
st.markdown("""
    <style>
    :root { color-scheme: light !important; }
    .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
    
    /* モバイルサイドバー：横幅75% / 文字「漆黒」 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 75vw !important; min-width: 75vw !important; background-color: #F8F9FA !important; }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {
            color: #000000 !important; font-size: 26px !important; font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            padding: 30px 10px !important; border-bottom: 2px solid #EDF2F7 !important;
        }
    }
    /* PC版：中央寄せ */
    @media (min-width: 769px) { .main .block-container { max-width: 850px !important; margin: auto !important; } }

    /* ボタン：ターコイズブルー固定・黒靄除去 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; height: 3.5em !important; font-weight: bold !important;
        box-shadow: none !important; opacity: 1 !important; transition: none !important;
    }
    div.stButton > button * { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }

    div[data-testid="stSidebarNav"] { display: none !important; }
    header { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン永続化・キャッシュロジック ---

@st.cache_data(ttl=25) # 25秒間はDBを叩かずメモリから表示（白飛び防止の極意）
def fetch_active_tasks():
    # VIEWから「今やるべき仕事」だけをピンポイント取得（要因①②対策）
    res = supabase.table("v_active_tasks_today").select("*").execute()
    return res.data or []

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

if not st.session_state.logged_in and saved_id and saved_key and str(saved_id) != "null":
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
        st_autorefresh(interval=1000, limit=2, key="sync"); st.stop()
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center; color: #75C9D7;'>BE STONE ログイン</h2>", unsafe_allow_html=True)
        with st.form("login_f"):
            u_id = st.text_input("STAFF ID")
            u_pw = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_k = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_k}).eq("staff_id", u_id).execute()
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_k}")')
                    st.session_state.logged_in = True; st.session_state.staff_info = res.data[0]; st.rerun()
                else: st.error("ID / PW不一致")
    st.stop()

# --- 4. 共通データ同期 ---
staff = st.session_state.staff_info
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# セッション有効チェック
check = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check.data or check.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# 勤怠・タスク取得（最適化版）
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# キャッシュされたVIEWからタスク取得
tasks = fetch_active_tasks()
active_task = next((t for t in tasks if t["status"] == "in_progress" and t["staff_id"] == staff['id']), None)

# 自動更新
if not active_task: st_autorefresh(interval=30000, key="global_ref")
is_mobile = (streamlit_js_eval(js_expressions='window.innerWidth', key='W_W', want_output=True) or 1000) < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

def render_task_execution(task):
    st.markdown(f"## 📍 遂行中: {task['location_name']}")
    if st.button("⏸️ 一時中断して戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['task_log_id']).execute()
        st.cache_data.clear(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['task_log_id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    
    cam_in = st.camera_input("認証・報告カメラ", key=f"c_{task['task_log_id']}")
    if cam_in:
        img = cv2.imdecode(np.asarray(bytearray(cam_in.read()), dtype=np.uint8), 1)
        qr_data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if not st.session_state[qr_v_key]:
            if qr_data == task['qr_token']:
                st.session_state[qr_v_key] = True; st.rerun()
            else: st.error("場所が違います")
        else:
            if st.button("✅ 報告して完了", type="primary", use_container_width=True):
                f_p = f"{task['task_log_id']}.jpg"
                supabase.storage.from_("task-photos").upload(f_p, cam_in.getvalue(), {"upsert":"true"})
                supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['task_log_id']).execute()
                st.cache_data.clear(); del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    menu_options = ["📋 本日の業務", "⚠️ 未完了タスク", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_options, key="nav")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア表示 ---
st.markdown("<h1 style='color: #75C9D7; margin-top: 0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%H:%M')} | {staff['name']}")

if choice == "📋 本日の業務":
    if is_mobile and active_task and not on_break:
        render_task_execution(active_task); st.stop()
    
    # タイムカード表示
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.cache_data.clear(); st.rerun()
    else:
        st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if not on_break:
            if c2.button("☕ 休憩", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤", use_container_width=True):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            if c2.button("🏃 復帰", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader("📋 今やるべきタスク")
        # VIEWから取得した「今の時間」のタスクだけを表示（要因①②対策）
        tasks_now = [t for t in tasks if t['target_hour'] == now_jst.hour]
        if not tasks_now: st.info("現在予定されているタスクはありません。")
        else:
            for t in tasks_now[:5]: # 表示上限5件（要因④対策）
                st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 15px 0;'>", unsafe_allow_html=True)
                ca, cb = st.columns([3, 1])
                with ca:
                    st.markdown(f"**【{t['target_hour']:02d}:{t['target_minute']:02d}】 {t['location_name']}**")
                    st.write(t['task_name'])
                with cb:
                    if t['status'] in ["pending", "interrupted"]:
                        if st.button("着手" if t['status']=="pending" else "再開", key=f"s_{t['task_log_id']}", use_container_width=True):
                            supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",t['task_log_id']).execute()
                            st.cache_data.clear(); st.session_state[f"qr_v_{t['task_log_id']}"] = False; st.rerun()
                    elif t['status'] == "in_progress": st.warning("Busy")
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "⚠️ 未完了タスク":
    # VIEWの仕組みを使い、過去の未完了のみを抽出
    all_today = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute().data
    overdue = [l for l in all_today if l['task_master']['target_hour'] < now_jst.hour and l['status'] != "completed"]
    if not overdue: st.success("全て完了しています！")
    else:
        for l in overdue:
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            ca, cb = st.columns([3, 1])
            ca.write(f"**【未完了】{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d} - {l['task_master']['locations']['name']}**")
            if cb.button("リカバリー", key=f"rec_{l['id']}", use_container_width=True, type="primary"):
                supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                st.cache_data.clear(); st.rerun()
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
        st.markdown(f"**📅 {c_in.strftime('%Y年%m月%d日')}** / {c_in.strftime('%H:%M')}〜 / <span style='color:{t_color};'>実働：{h:02d}:{m:02d}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif choice == "📊 監視(Admin)":
    # 管理者は全履歴をVIEWに頼らず取得
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    for l in l_adm.data:
        with st.container():
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
            st.markdown("</div>", unsafe_allow_html=True)

elif "出勤簿" in choice:
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    # (既存の出勤簿CSV出力ロジックを統合 - 動作安定版)
    all_s = supabase.table("staff").select("id, name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    target = st.selectbox("STAFF", ["-- 全員 --"] + list(s_dict.keys()))
    s_d, e_d = st.date_input("START", datetime.date.today()-datetime.timedelta(days=30)), st.date_input("END", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if target != "-- 全員 --": q = q.eq("staff_id", s_dict[target])
    data_res = q.order("work_date", desc=True).execute()
    if data_res.data:
        df_l = []
        for r in data_res.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_m = sum([int((datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() // 60) for b in r.get('breaks', []) if b['break_end_at']])
            act_m = (int((c_out - c_in).total_seconds() // 60) - br_m) if c_out else 0
            df_l.append({"名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "未", "休憩(分)": br_m, "実働(分)": act_m})
        st.dataframe(pd.DataFrame(df_l), use_container_width=True)