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

# --- 2. CSS注入（デザイン要求を100%実現する強制設定） ---
st.markdown("""
    <style>
    /* 1. モバイルサイドバーの横幅を画面の4分の3(75%)に固定 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 75vw !important;
            min-width: 75vw !important;
        }
    }
    
    /* 2. メニュー項目のフォントを大きく、間隔を劇的に広げる */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        font-size: 24px !important; 
        font-weight: bold !important;
        padding-top: 30px !important;
        padding-bottom: 30px !important;
        border-bottom: 1px solid #ddd !important;
    }

    /* 3. ログアウトボタンを赤色・大きく・押しやすく */
    div.stButton > button[key="logout_btn"] {
        background-color: #ff4b4b !important;
        color: white !important;
        height: 4em !important;
        font-size: 20px !important;
        font-weight: bold !important;
    }

    /* 不要なナビを隠す */
    div[data-testid="stSidebarNav"] { display: none; }
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# --- 4. ログイン・セッション管理（安定性重視） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

# 自動ログイン（非表示で実行し、取得できたらリロード）
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='load_key')

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
    st.title("🛡️ 業務管理ログイン")
    with st.form("login"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                new_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_key}).eq("staff_id", input_id).execute()
                # LocalStorageに保存
                st.markdown(f"""<script>
                    localStorage.setItem('staff_id', '{input_id}');
                    localStorage.setItem('session_key', '{new_key}');
                </script>""", unsafe_allow_html=True)
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("不一致")
    st.stop()

# --- 5. ログイン後のデータ同期 ---
staff = st.session_state.staff_info

# DBから最新状態を取得（常に同期）
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒ごと）
if not active_task: st_autorefresh(interval=30000, key="global_ref")

def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1); detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

# --- B. サイドバー表示 ---
st.sidebar.title("🏪 店舗管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")

menu_options = ["📋 本日の業務", "🕒 履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]

choice = st.sidebar.radio("機能を選択", menu_options)

# 下の方に隔離
for _ in range(8): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    st.markdown("<script>localStorage.clear(); location.reload();</script>", unsafe_allow_html=True)
    st.session_state.logged_in = False; st.rerun()

# --- C. メインコンテンツ表示 ---
if choice == "📋 本日の業務":
    st.title("📋 業務管理")
    st.write(f"🕒 日本時刻: {now_jst.strftime('%H:%M')}")
    
    # 勤怠UI
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
    else:
        st.success(f"出勤中 ({curr_card['clock_in_at'][11:16]}〜)")
        if not on_break:
            if c2.button("☕ 休憩", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            st.warning("休憩中")
            if c2.button("🏃 復帰", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()

    st.divider()
    if curr_card and not on_break:
        # タスクリスト
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
            elif l['status'] == "in_progress": colb.error("他者対応")
            else: colb.success("完了")

        # 【核心】業務遂行（PC/スマホ共通の安定ロジック）
        if active_task:
            st.divider()
            st.error(f"📍 遂行中: {active_task['task_master']['locations']['name']}")
            if st.button("⏸️ 中断してリストに戻る", use_container_width=True):
                supabase.table("task_logs").update({"status": "interrupted"}).eq("id", active_task['id']).execute(); st.rerun()
            
            qr_v_key = f"qr_v_{active_task['id']}"
            if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
            
            if not st.session_state[qr_v_key]:
                qr_in = st.camera_input("1. 現場QRスキャン", key=f"qr_{active_task['id']}")
                if qr_in and decode_qr(qr_in) == active_task['task_master']['locations']['qr_token']:
                    st.session_state[qr_v_key] = True; st.rerun()
            else:
                ph_in = st.camera_input("2. 完了写真撮影", key=f"ph_{active_task['id']}")
                if ph_in and st.button("✅ 報告を送信", type="primary", use_container_width=True):
                    f_p = f"{active_task['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",active_task['id']).execute()
                    del st.session_state[qr_v_key]; st.balloons(); st.rerun()

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
        df = pd.DataFrame(df_l)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 CSVダウンロード", df.to_csv(index=False).encode('utf_8_sig'), "attendance.csv", "text/csv")