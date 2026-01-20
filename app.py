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

# --- 1. システム設定 & CSS強制適用 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

# サイドバーを常に開いた状態で固定
st.set_page_config(page_title="天然薬石 Pro V2.1", layout="wide", initial_sidebar_state="expanded")

# 強力なCSSセレクタによるデザイン強制上書き
st.markdown(f"""
    <style>
    /* 1. モバイルサイドバー横幅 75% 強制固定 */
    [data-testid="stSidebar"] {{
        min-width: 75vw !important;
        max-width: 75vw !important;
    }}
    
    /* 2. メインメニュー：フォント特大・間隔広め・クリック領域拡大 */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
        font-size: 26px !important; 
        font-weight: bold !important;
        color: #31333F !important;
        padding: 30px 10px !important; /* 間隔を劇的に広げる */
        margin-bottom: 15px !important;
        border-bottom: 2px solid #e6e9ef !important;
        display: block !important;
    }}

    /* 3. ログアウトボタン：赤色・巨大化・押し間違いなし */
    div.stButton > button[key="logout_btn"] {{
        background-color: #ff4b4b !important;
        color: white !important;
        height: 5em !important;
        font-size: 22px !important;
        font-weight: 1000 !important;
        margin-top: 40px !important;
        border: none !important;
    }}

    /* 4. 標準パーツの完全抹殺 */
    div[data-testid="stSidebarNav"] {{ display: none !important; }}
    [data-testid="stHeader"] {{ visibility: hidden !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. ログイン持続・復元ロジック（要因①への対策） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# ブラウザのLocalStorageを読み込む（ラグを考慮して変数化）
local_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
local_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

# セッション復旧（DBを正解とする）
if not st.session_state.logged_in and local_id and local_key:
    try:
        res = supabase.table("staff").select("*").eq("staff_id", local_id).eq("session_key", local_key).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.staff_info = res.data[0]
            st.rerun()
    except: pass

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    # 同期待ちの間にログイン画面を出さないためのガード（要因①対策）
    if local_id is None:
        st.write("システム同期中...")
        st_autorefresh(interval=1000, limit=5, key="init_ref")
        st.stop()

    st.title("🛡️ 業務管理ログイン")
    with st.form("login_f"):
        input_id = st.text_input("スタッフID")
        input_pw = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pw).execute()
            if res.data:
                new_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_key}).eq("staff_id", input_id).execute()
                # LocalStorageに直接JavaScriptで書き込む
                st.markdown(f"""<script>
                    localStorage.setItem('staff_id', '{input_id}');
                    localStorage.setItem('session_key', '{new_key}');
                    location.reload();
                </script>""", unsafe_allow_html=True)
                st.stop()
            else: st.error("ID/PW不一致")
    st.stop()

# --- 3. 日本時間の計算 & 同期データ取得（要因③への対策） ---
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()
staff = st.session_state.staff_info

# グローバル同期チェック（他デバイスでのログアウト検知）
check_res = supabase.table("staff").select("session_key").eq("id", staff['id']).single().execute()
if not check_res.data or check_res.data['session_key'] is None:
    st.markdown("<script>localStorage.clear(); location.reload();</script>", unsafe_allow_html=True)
    st.stop()

# DBからのリアルタイム状態取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごと。同期の要）
if not active_task: st_autorefresh(interval=30000, key="global_ref")

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

def render_task_execution(task):
    st.title("📍 業務遂行中")
    st.error(f"場所: {task['task_master']['locations']['name']} / {task['task_master']['task_name']}")
    if st.button("⏸️ 中断して戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    if not st.session_state[qr_v_key]:
        st.subheader("1. 現場QRスキャン")
        qr_in = st.camera_input("QR撮影", key=f"qr_{task['id']}")
        if qr_in and decode_qr(qr_in) == task['task_master']['locations']['qr_token']:
            st.session_state[qr_v_key] = True; st.rerun()
    else:
        st.subheader("2. 完了写真撮影")
        ph_in = st.camera_input("完了写真", key=f"ph_{task['id']}")
        if ph_in and st.button("✅ 報告送信", type="primary", use_container_width=True):
            f_p = f"{task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
            del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー表示（要因②対策版デザイン） ---
if is_mobile and active_task and not on_break:
    render_task_execution(active_task); st.stop()

st.sidebar.title("🏪 管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")

choice = st.sidebar.radio(
    "機能を選択してください",
    ["📋 本日の業務", "🕒 履歴", "📊 監視(Admin)", "📅 出勤簿(Admin)"],
    key="nav_radio"
)

# ログアウトボタンを最下部へ
for _ in range(5): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    st.markdown("<script>localStorage.clear(); location.reload();</script>", unsafe_allow_html=True)
    st.stop()

# --- C. コンテンツ表示 ---
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
        if not is_mobile and active_task: render_task_execution(active_task); st.divider()
        st.subheader(f"{now_jst.hour:02d}時台のタスク")
        # タスク枠生成
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

elif "監視" in choice:
    st.title("📊 リアルタイム監視")
    l_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).eq("status", "completed").execute()
    cols = st.columns(4)
    for i, l in enumerate(l_adm.data):
        with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])

elif "出勤簿" in choice:
    st.title("📅 出勤簿出力")
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