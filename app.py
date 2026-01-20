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

st.set_page_config(page_title="天然薬石管理 Pro", layout="wide", initial_sidebar_state="expanded")

# --- 2. 究極のデザイン設定（CSS：サイドバー75%・特大文字・広間隔） ---
st.markdown("""
    <style>
    /* モバイルサイドバー横幅 75% 強制固定 */
    [data-testid="stSidebar"] {
        min-width: 75vw !important;
        max-width: 75vw !important;
    }
    
    /* サイドバーメニュー：特大フォント(26px)・上下間隔(40px) */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        font-size: 26px !important; 
        font-weight: bold !important;
        padding: 20px 0px !important; 
        margin-bottom: 20px !important;
        border-bottom: 2px solid #f0f2f6 !important;
        display: block !important;
    }

    /* ログアウトボタン：赤色・巨大 */
    div.stButton > button[key="logout_btn"] {
        background-color: #ff4b4b !important;
        color: white !important;
        height: 5em !important;
        font-size: 22px !important;
        font-weight: bold !important;
    }

    /* ヘッダー等を隠してアプリ感を出す */
    div[data-testid="stSidebarNav"] { display: none; }
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン永続化・自動復旧ロジック ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザの記憶を取得（非同期）
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# 自動復旧チェック（プログラムを止めずに判定）
if not st.session_state.logged_in and saved_id and saved_key:
    try:
        res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except: pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    # 記憶を読み込んでいる最中（1〜2秒）は「読み込み中」だけ出す
    if saved_id is None:
        st.info("🔄 認証情報を同期しています...")
        st_autorefresh(interval=1000, limit=3, key="init_ref")
        st.stop()
    
    st.title("🛡️ 業務管理 ログイン")
    with st.form("login_form"):
        u_id = st.text_input("スタッフID")
        u_pw = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
            if res.data:
                new_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                # LocalStorageに書き込み
                streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")')
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("ID/PWが違います")
    st.stop()

# --- 4. データ取得 & グローバル同期 ---
staff = st.session_state.staff_info
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# セッション有効チェック
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    streamlit_js_eval(js_expressions='localStorage.clear()')
    st.session_state.logged_in = False
    st.rerun()

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

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); det = cv2.QRCodeDetector()
        val, _, _ = det.detectAndDecode(opencv_image)
        return val
    except: return ""

# --- 5. 業務遂行モード (PC/スマホ共通) ---
def render_task_execution(task):
    st.markdown(f"## 📍 遂行中: {task['task_master']['locations']['name']}")
    st.info(f"指示内容: {task['task_master']['task_name']}")
    if st.button("⏸️ 中断してリストに戻る", use_container_width=True, key=f"int_{task['id']}"):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    
    # QR認証済みかセッションで保持
    v_key = f"v_{task['id']}"
    if v_key not in st.session_state: st.session_state[v_key] = False
    
    if not st.session_state[v_key]:
        st.subheader("1️⃣ 現場のQRをスキャン")
        qr_in = st.camera_input("QR撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[v_key] = True; st.rerun()
    else:
        st.subheader("2️⃣ 完了写真の撮影")
        ph_in = st.camera_input("写真撮影", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", type="primary", use_container_width=True, key=f"send_{task['id']}"):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[v_key]; st.balloons(); st.rerun()

# --- B. ナビゲーション ---
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W', want_output=True)
is_mobile = width is not None and width < 768

# スマホ作業中はサイドバーを封印して全画面化
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

st.sidebar.title("🏪 管理メニュー")
st.sidebar.write(f"👤 {staff['name']} 様")
menu = ["📋 本日の業務", "🕒 履歴", "📊 監視(Admin)", "📅 出勤簿(Admin)"]
choice = st.sidebar.radio("メニューを選択", [m for m in menu if "Admin" not in m or staff['role'] == 'admin'])

for _ in range(8): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メイン画面 ---
if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 日本時刻: {now_jst.strftime('%H:%M')}")
    st.divider()
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
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
        # PC作業中の表示
        if not is_mobile and active_task:
            render_task_execution(active_task)
            st.divider()

        st.subheader(f"{now_jst.hour:02d}時台のタスク")
        # タスク生成
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
            elif l['status'] == "in_progress" and l['staff_id'] == staff['id']: colb.warning("遂行中")
            elif l['status'] == "in_progress": colb.error("他者対応")
            else: colb.success("完了")

elif choice == "🕒 履歴":
    st.title("🕒 履歴")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    st.table(h_res.data)

elif "監視" in choice:
    st.title("📊 リアルタイム写真監視")
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    cols = st.columns(4)
    for i, l in enumerate(l_adm.data):
        with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])

elif "出勤簿" in choice:
    st.title("📅 出勤簿データ出力")
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("スタッフ", ["-- 全員 --"] + list(s_dict.keys()))
    s_d, e_d = cb.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), cc.date_input("終了", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
    data = q.order("work_date", desc=True).execute()
    if data.data:
        df_l = []
        for r in data.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_s = sum([(datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() for b in r.get('breaks', []) if b['break_end_at']])
            work_str = f"{int((max(0,(c_out-c_in).total_seconds()-br_s))//3600)}時{int(((max(0,(c_out-c_in).total_seconds()-br_s))%3600)//60)}分" if c_out else "--"
            df_l.append({"名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "未打刻", "休憩(分)": int(br_s // 60), "実働": work_str})
        st.dataframe(pd.DataFrame(df_l), use_container_width=True)
        st.download_button("📥 CSVダウンロード", pd.DataFrame(df_l).to_csv(index=False).encode('utf_8_sig'), "attendance.csv", "text/csv")