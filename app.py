import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd
from streamlit_js_eval import streamlit_js_eval
from streamlit_autorefresh import st_autorefresh

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="天然薬石管理システム Pro", layout="wide")

# --- 2. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()
current_hour = now_jst.hour
current_minute = now_jst.minute

# --- 3. セッション管理 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

# 自動ログイン（LocalStorage）
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')
if not st.session_state.logged_in and saved_id:
    res = supabase.table("staff").select("*").eq("staff_id", saved_id).execute()
    if res.data:
        st.session_state.logged_in = True
        st.session_state.staff_info = res.data[0]
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
                streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{input_id}")', key='save_id')
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- B. ログイン後の共通データ取得 ---
staff = st.session_state.staff_info

# 同期のためにDBから現在の状態を取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None

b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# 今日のタスク一覧
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 実行中の自分のタスクがあるか確認
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# --- 4. 【重要】スマート・リフレッシュ制御 ---
# カメラ操作中（active_taskが存在する時）は、勝手なリロードを防ぐためリフレッシュを停止する
if not active_task:
    st_autorefresh(interval=30000, key="datarefresh") # 30秒に緩和
else:
    st.sidebar.info("🔄 作業中のため自動更新停止中")

# --- 5. CSS調整 ---
st.markdown("""
    <style>
    div.stButton > button:first-child[key="logout_btn"] { background-color: #ff4b4b; color: white; border-radius: 8px; }
    div[data-testid="stSidebarNav"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

# --- C. サイドバー ---
st.sidebar.title("🏪 管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")
menu_options = ["📋 本日の業務", "🕒 マイ勤怠履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 リアルタイム監視", "📅 出勤簿データ出力"]

choice = st.sidebar.radio("機能を切り替え", menu_options)

for _ in range(12): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    streamlit_js_eval(js_expressions='localStorage.clear()', key='clear_id')
    st.session_state.logged_in = False
    st.rerun()

# --- D. メイン画面遷移 ---

if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 日本時刻: {current_hour:02d}:{current_minute:02d}")
    
    # 勤怠UI
    st.divider()
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True, key="in_btn"):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute()
            st.rerun()
    else:
        st.success(f"出勤中: {curr_card['clock_in_at'][11:16]}〜")
        if not on_break:
            if c2.button("☕ 休憩入り", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute()
                st.rerun()
            if c3.button("🏁 退勤打刻", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute()
                st.rerun()
        else:
            st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
            if c2.button("🏃 業務戻り", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute()
                st.rerun()

    # タスク管理
    st.divider()
    if not curr_card: st.info("出勤打刻をしてください。")
    elif on_break: st.warning("休憩中です。")
    else:
        # 今日のタスク枠の自動生成（必要な場合のみ）
        if not l_data:
            tm_res = supabase.table("task_master").select("*").execute()
            for tm in tm_res.data:
                try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
                except: pass
            st.rerun()
        
        st.subheader(f"{current_hour}時台のタスク")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == current_hour]
        
        if not display_tasks:
            st.write("予定なし")
        else:
            for l in display_tasks:
                cola, colb = st.columns([3, 1])
                cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] == "pending":
                    if colb.button("着手", key=f"start_{l['id']}"):
                        supabase.table("task_logs").update({"status":"in_progress","started_at":now_jst.isoformat(),"staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.rerun()
                elif l['status'] == "in_progress" and l['staff_id'] == staff['id']:
                    if colb.button("取消", key=f"cncl_{l['id']}"):
                        supabase.table("task_logs").update({"status":"pending","started_at":None,"staff_id":None}).eq("id",l['id']).execute()
                        st.rerun()
                elif l['status'] == "in_progress": colb.warning("実施中")
                else: colb.success("完了")

        # 業務遂行
        if active_task:
            st.divider()
            st.error(f"📍 遂行中: {active_task['task_master']['locations']['name']}")
            qr = st.camera_input("QRスキャン", key=f"qr_cam")
            if qr and decode_qr(qr) == active_task['task_master']['locations']['qr_token']:
                st.success("到着。完了写真を撮影してください。")
                ph = st.camera_input("完了写真", key=f"ph_cam")
                if ph and st.button("報告を送信", type="primary", key="send_btn"):
                    f_path = f"{active_task['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_path, ph.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_path}).eq("id",active_task['id']).execute()
                    st.balloons()
                    st.rerun()

elif choice == "🕒 マイ勤怠履歴":
    st.title("🕒 あなたの勤怠履歴")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    st.table(h_res.data)

elif choice == "📊 リアルタイム監視":
    st.title("📊 管理者ダッシュボード")
    l_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    l_data_admin = sorted(l_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
    st.subheader("⚠️ 遅延アラート")
    for l in l_data_admin:
        t_h, t_m = l['task_master']['target_hour'] or 0, l['task_master']['target_minute'] or 0
        if l['status'] == 'pending' and (t_h < current_hour or (t_h == current_hour and t_m < current_minute)):
            st.error(f"【遅延】{t_h:02d}:{t_m:02d} - {l['task_master']['locations']['name']}")

elif choice == "📅 出勤簿データ出力":
    st.title("📅 出勤簿データ出力")
    # (以前の出力ロジックを維持)