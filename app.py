import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd
import uuid # 追加：セッションID生成用
from streamlit_js_eval import streamlit_js_eval
from streamlit_autorefresh import st_autorefresh

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="天然薬石管理 Pro", layout="wide", initial_sidebar_state="auto")

# --- 2. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# --- 3. セッション管理 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

# ブラウザから保存された情報を取得
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='load_key')

# 【重要】グローバル同期チェックロジック
if not st.session_state.logged_in and saved_id and saved_key:
    # DBのsession_keyが一致するか確認
    res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
    if res.data:
        st.session_state.logged_in = True
        st.session_state.staff_info = res.data[0]
        st.rerun()

# ログイン中の場合、30秒ごとに「自分のセッションがまだ有効か」をDBに確認
if st.session_state.logged_in:
    check_res = supabase.table("staff").select("session_key").eq("id", st.session_state.staff_info['id']).single().execute()
    # 他のデバイスでログアウト（NULLに）されていたら、強制終了
    if not check_res.data or check_res.data['session_key'] is None:
        streamlit_js_eval(js_expressions='localStorage.clear()', key='force_clear')
        st.session_state.logged_in = False
        st.session_state.staff_info = None
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
                # 新しいログイン許可証（UUID）を発行してDBとブラウザに保存
                new_session_key = str(uuid.uuid4())
                supabase.table("staff").update({"session_key": new_session_key}).eq("staff_id", input_id).execute()
                streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{input_id}")', key='save_id')
                streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_session_key}")', key='save_key')
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- B. 共通データ取得 ---
staff = st.session_state.staff_info
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新（作業中でなければ30秒おき）
if not active_task:
    st_autorefresh(interval=30000, key="global_ref")

width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH', want_output=True)
is_mobile = width is not None and width < 768

# --- 4. スマホ専用：業務遂行全画面モード ---
if is_mobile and active_task and not on_break:
    st.title("📍 業務遂行中")
    st.error(f"場所: {active_task['task_master']['locations']['name']}")
    if st.button("⬅️ 取消して戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "pending", "started_at": None, "staff_id": None}).eq("id", active_task['id']).execute()
        st.rerun()
    st.divider()
    qr_key = f"qrv_{active_task['id']}"
    if qr_key not in st.session_state: st.session_state[qr_key] = False
    if not st.session_state[qr_key]:
        qr_in = st.camera_input("QRスキャン", key="m_qr")
        if qr_in and decode_qr(qr_in) == active_task['task_master']['locations']['qr_token']:
            st.session_state[qr_key] = True
            st.rerun()
    else:
        ph_in = st.camera_input("写真撮影", key="m_ph")
        if ph_in and st.button("✅ 報告送信", type="primary", use_container_width=True):
            f_p = f"{active_task['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",active_task['id']).execute()
            del st.session_state[qr_key]
            st.balloons(); st.rerun()
    st.stop()

# --- C. 通常ナビゲーション ---
st.sidebar.title("🏪 店舗管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")
menu_options = ["📋 本日の業務", "🕒 マイ勤怠履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 リアルタイム監視", "📅 出勤簿データ出力"]
choice = st.sidebar.radio("機能を選択", menu_options)

for _ in range(8): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    # 【核心】DBの許可証をNULLにして、全デバイスから追い出す
    supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
    streamlit_js_eval(js_expressions='localStorage.clear()', key='clear_id')
    st.session_state.logged_in = False
    st.rerun()

# --- D. 各画面表示 ---
if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 現在時刻: {now_jst.strftime('%H:%M')}")
    st.divider()
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
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
    st.divider()
    if curr_card and not on_break:
        if not l_data:
            tms = supabase.table("task_master").select("*").execute()
            for tm in tms.data:
                try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
                except: pass
            st.rerun()
        st.subheader(f"{now_jst.hour:02d}時台のタスク")
        for l in [x for x in l_data if x['task_master']['target_hour'] == now_jst.hour]:
            cola, colb = st.columns([3, 1])
            cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
            if l['status'] == "pending":
                if colb.button("着手", key=f"s_{l['id']}"):
                    supabase.table("task_logs").update({"status":"in_progress","started_at":now_jst.isoformat(),"staff_id":staff['id']}).eq("id",l['id']).execute()
                    st.rerun()
            elif l['status'] == "in_progress" and l['staff_id'] == staff['id']:
                if colb.button("取消", key=f"c_{l['id']}"):
                    supabase.table("task_logs").update({"status":"pending","started_at":None,"staff_id":None}).eq("id",l['id']).execute()
                    st.rerun()
            elif l['status'] == "in_progress": colb.warning("他者実施中")
            else: colb.success("完了")

elif choice == "🕒 マイ勤怠履歴":
    st.title("🕒 あなたの勤怠履歴")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    st.table(h_res.data)

elif choice == "📊 リアルタイム監視":
    st.title("📊 管理者ダッシュボード")
    l_res_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    comps = [l for l in l_res_adm.data if l['status'] == 'completed']
    cols = st.columns(4)
    for i, l in enumerate(comps):
        with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])

elif choice == "📅 出勤簿データ出力":
    st.title("📅 出勤簿データ抽出")
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("スタッフ選択", ["-- 全員 --"] + list(s_dict.keys()))
    s_d, e_d = cb.date_input("開始", datetime.date.today()-datetime.timedelta(days=30)), cc.date_input("終了", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
    data = q.order("work_date", desc=True).execute()
    if data.data:
        df = pd.DataFrame([{"名前": r['staff_name'], "日付": r['work_date'], "出勤": r['clock_in_at'][11:16], "退勤": r['clock_out_at'][11:16] if r['clock_out_at'] else "未"} for r in data.data])
        st.dataframe(df, use_container_width=True)