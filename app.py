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

# CSS: ログアウトボタンを赤くし、標準メニューを隠す
st.markdown("""
    <style>
    div.stButton > button:first-child[key="logout_btn"] { background-color: #ff4b4b; color: white; border-radius: 8px; }
    div[data-testid="stSidebarNav"] { display: none; }
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# --- 3. セッション管理 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

# ブラウザの記憶（LocalStorage）からIDとキーを読み取る
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='load_key')

# 自動ログイン（記憶があればDB照合して復元）
if not st.session_state.logged_in and saved_id and saved_key:
    try:
        res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except:
        pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    st.title("🛡️ 業務管理システム ログイン")
    with st.form("login_form"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                new_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_key}).eq("staff_id", input_id).execute()
                # LocalStorageに書き込み（JavaScriptで実行）
                st.markdown(f"""
                    <script>
                        localStorage.setItem('staff_id', '{input_id}');
                        localStorage.setItem('session_key', '{new_key}');
                    </script>
                """, unsafe_allow_html=True)
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else:
                st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- 4. 共通データ取得（ログイン後のみ実行） ---
staff = st.session_state.staff_info

# グローバル・ログアウト・チェック（他端末でのログアウトを検知）
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    st.markdown("<script>localStorage.clear();</script>", unsafe_allow_html=True)
    st.session_state.logged_in = False
    st.rerun()

# 勤怠・休憩・タスク状況をDBから同期
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None

b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 実行中の自分のタスクを探す
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごと）
if not active_task:
    st_autorefresh(interval=30000, key="global_ref")

# モバイル判定
width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH', want_output=True)
is_mobile = width is not None and width < 768

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

# 業務遂行用UI
def render_task_execution(task):
    st.title("📍 業務遂行中")
    st.error(f"場所: {task['task_master']['locations']['name']} / {task['task_master']['task_name']}")
    if st.button("⏸️ 中断してリストに戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute()
        st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    if not st.session_state[qr_v_key]:
        st.subheader("1️⃣ 現場QRスキャン")
        qr_in = st.camera_input("QR撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2️⃣ 完了写真撮影")
        ph_in = st.camera_input("完了写真", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告を送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. ナビゲーション ---
# スマホで作業中の場合はメニューを隠して全画面カメラに
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

st.sidebar.title("🏪 店舗管理")
st.sidebar.write(f"👤 {staff['name']} 様")
menu_options = ["📋 本日の業務", "🕒 履歴", "📊 監視(Admin)", "📅 出勤簿(Admin)"]
choice = st.sidebar.radio("機能を選択", [m for m in menu_options if "Admin" not in m or staff['role'] == 'admin'])

for _ in range(12): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    st.markdown("<script>localStorage.clear();</script>", unsafe_allow_html=True)
    st.session_state.logged_in = False
    st.rerun()

# --- C. メインコンテンツ ---
if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 日本時刻: {now_jst.strftime('%H:%M')}")
    st.divider()
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute()
            st.rerun()
    else:
        st.success(f"出勤中 ({curr_card['clock_in_at'][11:16]}〜)")
        if not on_break:
            if c2.button("☕ 休憩入り", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤打刻", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
            if c2.button("🏃 業務戻り", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()

    st.divider()
    if curr_card and not on_break:
        # PCで作業中の場合の表示
        if not is_mobile and active_task: render_task_execution(active_task); st.divider()

        st.subheader(f"{now_jst.hour:02d}時台のタスク")
        # タスク枠の自動生成（未生成なら）
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
                if colb.button("着手", key=f"s_{l['id']}"):
                    supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.rerun()
            elif l['status'] == "interrupted":
                if colb.button("再開", key=f"r_{l['id']}", type="primary"):
                    supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.rerun()
            elif l['status'] == "in_progress" and l['staff_id'] == staff['id']: colb.warning("作業中")
            elif l['status'] == "in_progress": colb.error("他者対応中")
            else: colb.success("完了")

elif choice == "🕒 履歴":
    st.title("🕒 履歴")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    st.table(h_res.data)

elif "Admin" in choice:
    # (監視/出勤簿ロジック - 以前のものを継続)
    st.title(choice)
    if "監視" in choice:
        l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
        cols = st.columns(4)
        for i, l in enumerate(l_adm.data):
            with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])
    else:
        # 出勤簿CSV出力ロジック
        all_s = supabase.table("staff").select("id, name").order("name").execute()
        s_dict = {s['name']: s['id'] for s in all_s.data}
        ca, cb, cc = st.columns(3)
        t_staff = ca.selectbox("スタッフ", ["-- 全員 --"] + list(s_dict.keys()))
        s_d, e_d = cb.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), cc.date_input("終了", datetime.date.today())
        q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
        if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
        res_data = q.order("work_date", desc=True).execute()
        if res_data.data:
            df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "未"} for r in res_data.data])
            st.dataframe(df, use_container_width=True)
            st.download_button("📥 CSVダウンロード", df.to_csv(index=False).encode('utf_8_sig'), "attendance.csv", "text/csv")