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

st.set_page_config(page_title="BE STONE Pro", page_icon="logo.png", layout="wide")

# --- 2. 視認性最優先・強制ライトモードCSS ---
st.markdown("""
    <style>
    :root { color-scheme: light !important; }
    .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
    .stMarkdown, p, h1, h2, h3, span, label, li, div { color: #000000 !important; }

    /* モバイルサイドバー：横幅75% / 文字色「漆黒」 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 75vw !important; min-width: 75vw !important; background-color: #F8F9FA !important; }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {
            color: #000000 !important; font-size: 26px !important; font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            padding-top: 35px !important; padding-bottom: 35px !important; border-bottom: 2px solid #EDF2F7 !important;
        }
    }
    /* ボタン：ターコイズブルー (#75C9D7) 統一 / 黒靄物理消去 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; height: 3.5em !important; font-weight: bold !important;
        box-shadow: none !important; opacity: 1 !important; transition: none !important;
    }
    div.stButton > button * { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 高速化キャッシュ・ロジック ---

@st.cache_data(ttl=60) # 1分間はDBに再アクセスせずメモリから返す（白飛び対策）
def get_task_logs(today_date):
    """今日一日の全ログを取得"""
    res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_date).execute()
    return res.data

def ensure_daily_tasks(today_date):
    """今日一日のタスク枠を一度だけ生成する重い処理"""
    # 既に今日のデータが1件でもあれば、この関数全体をスキップする
    existing = supabase.table("task_logs").select("id").eq("work_date", today_date).limit(1).execute()
    if not existing.data:
        tm_data = supabase.table("task_master").select("*").execute()
        for tm in tm_data.data:
            try: supabase.table("task_logs").insert({"task_id": tm["id"], "work_date": today_date, "status": "pending"}).execute()
            except: pass
        return True
    return False

# --- 4. ログイン管理（自動復旧） ---
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
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center; color: #75C9D7;'>BE STONE ログイン</h2>", unsafe_allow_html=True)
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
                else: st.error("ID / PW不一致")
    st.stop()

# --- 5. ログイン後の同期処理 ---
staff = st.session_state.staff_info
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# タスク自動生成（今日最初のアクセス時のみ実行）
ensure_daily_tasks(today_jst)

# データ取得（キャッシュ利用）
l_data_all = get_task_logs(today_jst)
l_data = sorted(l_data_all, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 勤怠・休憩ステータス（これは常に最新が必要なのでキャッシュしない）
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごと。キャッシュがあるため一瞬で終わる）
if not active_task: st_autorefresh(interval=30000, key="global_ref")

# モバイル判定
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
    st.markdown(f"### 📍 遂行中: {task['task_master']['locations']['name']}")
    if st.button("⏸️ 中断してリストに戻る"):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute()
        st.cache_data.clear() # キャッシュを消して即時反映させる
        st.rerun()
    st.divider()
    v_key = f"qr_v_{task['id']}"
    if v_key not in st.session_state: st.session_state[v_key] = False
    if not st.session_state[v_key]:
        qr_in = st.camera_input("1. 現場QRを撮影して認証", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[v_key] = True; st.rerun()
    else:
        ph_in = st.camera_input("2. 完了写真撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            st.cache_data.clear() # 完了後はキャッシュを消去
            del st.session_state[v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
if is_mobile and active_task: render_task_execution(active_task); st.stop()

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"**{staff['name']} 様**")
    st.divider()
    menu_list = ["📋 本日の業務", "⚠️ 未完了タスク", "🕒 履歴"]
    if staff['role'] == 'admin': menu_list += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.radio("MENU", menu_list, key="nav")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリア ---
st.markdown("<h1 style='color: #75C9D7;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%H:%M')} | {staff['name']}")

if choice == "📋 本日の業務":
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute()
            st.rerun()
    else:
        st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if st.button("🏁 退勤打刻", use_container_width=True):
            supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute()
            st.rerun()

    st.divider()
    if curr_card:
        st.subheader("📋 今の時間帯のタスク")
        # 【改善】DBからの全データ(l_data)を現在の時間でフィルタリング
        tasks_now = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        
        if not tasks_now: st.info("この時間の予定はありません。")
        else:
            for l in tasks_now:
                st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 20px 0;'>", unsafe_allow_html=True)
                cola, colb = st.columns([3, 1])
                with cola:
                    st.markdown(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
                    st.write(l['task_master']['task_name'])
                with colb:
                    if l['status'] == "pending":
                        if st.button("着手", key=f"s_{l['id']}", use_container_width=True):
                            supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                            st.cache_data.clear(); st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
                    elif l['status'] == "in_progress": st.warning("Busy")
                    else: st.success("OK")
                st.markdown("</div>", unsafe_allow_html=True)

elif choice == "⚠️ 未完了タスク":
    st.subheader("🚨 過去の未完了")
    overdue = [l for l in l_data if l['task_master']['target_hour'] < now_jst.hour and l['status'] != "completed"]
    if not overdue: st.success("全て完了しています！")
    else:
        for l in overdue:
            st.markdown("<div style='border-bottom: 1px solid #FFEDED; padding: 15px 0;'>", unsafe_allow_html=True)
            ca, cb = st.columns([3, 1])
            ca.write(f"**【遅延】{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d} - {l['task_master']['locations']['name']}**")
            if cb.button("リカバリー", key=f"rec_{l['id']}", use_container_width=True, type="primary"):
                supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                st.cache_data.clear(); st.session_state[f"qr_v_{l['id']}"] = False; st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

elif choice == "📊 監視(Admin)":
    l_adm = [l for l in l_data if l['status'] == 'completed']
    for l in l_adm:
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
        st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "📅 出勤簿(Admin)":
    # 以前の出勤簿ロジックを統合
    st.write("Admin Report logic")