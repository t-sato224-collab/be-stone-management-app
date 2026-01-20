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

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="天然薬石管理 Pro", layout="wide", initial_sidebar_state="auto")

# --- 2. CSS調整（UI最適化） ---
st.markdown("""
    <style>
    div.stButton > button:first-child[key="logout_btn"] { background-color: #ff4b4b; color: white; border-radius: 8px; }
    div[data-testid="stSidebarNav"] { display: none; }
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# --- 4. セッション・ログイン・グローバル同期管理 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザメモリ（LocalStorage）からの自動復元
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='load_key')

if not st.session_state.logged_in and saved_id and saved_key:
    res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
    if res.data:
        st.session_state.logged_in = True
        st.session_state.staff_info = res.data[0]
        st.rerun()

# グローバル・ログアウト・チェック（他デバイスでのログアウト検知）
if st.session_state.logged_in:
    check_res = supabase.table("staff").select("session_key").eq("id", st.session_state.staff_info['id']).single().execute()
    if not check_res.data or check_res.data['session_key'] is None:
        streamlit_js_eval(js_expressions='localStorage.clear()', key='force_clear')
        st.session_state.logged_in = False
        st.rerun()

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    st.title("🛡️ 業務管理システム ログイン")
    with st.form("login"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                new_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_key}).eq("staff_id", input_id).execute()
                streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{input_id}")', key='s_id')
                streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")', key='s_key')
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
    st.stop()

# --- B. 共通データ取得（リアルタイム同期） ---
staff = st.session_state.staff_info
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# 今日の全タスク取得
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 【核心】「自分が今、遂行中」のタスクを探す
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごとに他のデバイス情報を反映）
if not active_task:
    st_autorefresh(interval=30000, key="global_ref")

width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH', want_output=True)
is_mobile = width is not None and width < 768

# --- C. 【核心】モバイル業務遂行画面（中断・引き継ぎ対応） ---
if is_mobile and active_task and not on_break:
    st.title("📍 業務遂行中")
    st.error(f"場所: {active_task['task_master']['locations']['name']}")
    st.info(f"指示: {active_task['task_master']['task_name']}")

    # 中断ボタン
    if st.button("⏸️ 接客・緊急トラブルで中断", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", active_task['id']).execute()
        st.rerun()

    st.divider()
    qr_v_key = f"qr_v_{active_task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False

    if not st.session_state[qr_v_key]:
        st.subheader("1️⃣ 現場QRをスキャン")
        qr_in = st.camera_input("QRを撮影", key="m_qr")
        if qr_in:
            if decode_qr(qr_in) == active_task['task_master']['locations']['qr_token']:
                st.session_state[qr_v_key] = True
                st.rerun()
            else: st.error("場所が違います")
    else:
        st.subheader("2️⃣ 作業終了・アフター写真")
        ph_in = st.camera_input("完了写真を撮影", key="m_ph")
        if ph_in and st.button("✅ 送信して完了", type="primary", use_container_width=True):
            f_p = f"{active_task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",active_task['id']).execute()
            del st.session_state[qr_v_key]
            st.balloons(); st.rerun()
    st.stop()

# --- D. 通常ナビゲーション ---
st.sidebar.title("🏪 管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")
menu_options = ["📋 本日の業務", "🕒 履歴", "📊 監視(Admin)", "📅 出勤簿(Admin)"]
choice = st.sidebar.radio("機能を選択", [m for m in menu_options if "Admin" not in m or staff['role'] == 'admin'])

for _ in range(8): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    streamlit_js_eval(js_expressions='localStorage.clear()', key='clr')
    st.session_state.logged_in = False
    st.rerun()

# --- E. 業務メイン画面 ---
if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 日本時刻: {now_jst.strftime('%H:%M')}")
    
    # 勤怠UI
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤", use_container_width=True):
            supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":now_jst.isoformat(), "work_date":today_jst}).execute()
            st.rerun()
    else:
        st.success(f"出勤中 ({curr_card['clock_in_at'][11:16]}〜)")
        if not on_break:
            if c2.button("☕ 休憩", use_container_width=True):
                supabase.table("breaks").insert({"staff_id":staff['id'], "timecard_id":curr_card['id'], "break_start_at":now_jst.isoformat(), "work_date":today_jst}).execute()
                st.rerun()
            if c3.button("🏁 退勤", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at":now_jst.isoformat()}).eq("id", curr_card['id']).execute()
                st.rerun()
        else:
            st.warning("休憩中")
            if c2.button("🏃 復帰", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at":now_jst.isoformat()}).eq("id", on_break['id']).execute()
                st.rerun()

    # タスクリスト
    st.divider()
    if curr_card and not on_break:
        # 今日のタスク枠自動生成（未生成時のみ）
        if not l_data:
            tm_res = supabase.table("task_master").select("*").execute()
            for tm in tm_res.data:
                try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
                except: pass
            st.rerun()

        st.subheader(f"{now_jst.hour:02d}時台の予定")
        for l in [x for x in l_data if x['task_master']['target_hour'] == now_jst.hour]:
            cola, colb = st.columns([3, 1])
            cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
            
            if l['status'] == "pending":
                if colb.button("着手", key=f"s_{l['id']}"):
                    supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                    st.rerun()
            elif l['status'] == "interrupted":
                # 他の人が中断したタスクを「再開（引き継ぎ）」できる
                if colb.button("再開", key=f"r_{l['id']}", type="primary"):
                    supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute()
                    st.rerun()
            elif l['status'] == "in_progress" and l['staff_id'] == staff['id']:
                colb.warning("遂行中")
            elif l['status'] == "in_progress":
                colb.error("他者が対応中")
            else:
                colb.success("完了")

elif choice == "📊 監視(Admin)":
    st.title("📊 リアルタイム監視")
    l_res_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    comps = [l for l in l_res_adm.data if l['status'] == 'completed']
    cols = st.columns(4)
    for i, l in enumerate(comps):
        with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=f"{l['task_master']['locations']['name']} ({l['completed_at'][11:16]})")

elif choice == "📅 出勤簿(Admin)":
    st.title("📅 出勤簿データ出力")
    # (既存のCSV出力ロジックを統合)
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("スタッフ選択", ["-- 全員 --"] + list(s_dict.keys()))
    s_d = cb.date_input("開始", datetime.date.today() - datetime.timedelta(days=30))
    e_d = cc.date_input("終了", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
    res_data = q.order("work_date", desc=True).execute()
    if res_data.data:
        df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "未"} for r in res_data.data])
        st.dataframe(df, use_container_width=True)