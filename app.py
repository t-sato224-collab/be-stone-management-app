import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime

# --- 1. システム接続設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

st.set_page_config(page_title="天然薬石管理システム V1.0", layout="centered")

# --- 2. セッション状態の初期化 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None
if 'task_status' not in st.session_state:
    st.session_state.task_status = "waiting"

# --- 3. 共通関数 ---
def decode_qr(image):
    """カメラ入力からQRを解析"""
    file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
    opencv_image = cv2.imdecode(file_bytes, 1)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(opencv_image)
    return data

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    st.title("🛡️ 薬石岩盤浴 業務管理ログイン")
    with st.form("login_form"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else:
                st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- B. メイン画面（ログイン後） ---
staff = st.session_state.staff_info
today = datetime.date.today().isoformat()
current_hour = datetime.datetime.now().hour

# サイドバー設定
st.sidebar.title("MENU")
st.sidebar.write(f"👤 ログイン: {staff['name']} 様")
st.sidebar.write(f"権限: {staff['role']}")

# パスワード変更
with st.sidebar.expander("🔑 パスワード変更"):
    with st.form("pw_change"):
        c_pw = st.text_input("現在", type="password")
        n_pw = st.text_input("新規", type="password")
        if st.form_submit_button("更新"):
            if c_pw == staff['password'] and len(n_pw) >= 4:
                supabase.table("staff").update({"password": n_pw}).eq("id", staff['id']).execute()
                st.session_state.staff_info['password'] = n_pw
                st.success("更新完了")
            else: st.error("不備あり")

# 管理者ダッシュボード切替（admin権限のみ）
admin_mode = False
if staff['role'] == 'admin':
    st.sidebar.divider()
    admin_mode = st.sidebar.checkbox("🚀 管理者ダッシュボード")

if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

# --- C. 管理者ダッシュボード画面 ---
if admin_mode:
    st.title("📊 店舗運営ダッシュボード")
    
    # 状況集計
    working_res = supabase.table("timecards").select("id", count="exact").eq("work_date", today).is_("clock_out_at", "null").execute()
    breaking_res = supabase.table("breaks").select("id", count="exact").eq("work_date", today).is_("break_end_at", "null").execute()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("出勤中", f"{working_res.count} 名")
    col2.metric("休憩中", f"{breaking_res.count} 名")
    
    # 全ログ取得
    all_logs = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today).execute()
    logs_data = all_logs.data
    
    pending_count = len([l for l in logs_data if l['status'] != 'completed'])
    col3.metric("未完了タスク", f"{pending_count} 件")

    st.subheader("📸 本日の報告写真（検閲）")
    comp_logs = [l for l in logs_data if l['status'] == 'completed']
    if comp_logs:
        cols = st.columns(3)
        for i, l in enumerate(comp_logs):
            with cols[i % 3]:
                st.write(f"**{l['task_master']['locations']['name']}**")
                img_url = f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}"
                st.image(img_url)
                st.caption(f"完了:{l['completed_at'][11:16]}")
    else: st.info("完了報告はありません")

    st.subheader("⚠️ 遅延アラート")
    for l in logs_data:
        if l['status'] == 'pending' and (l['task_master']['target_hour'] or 0) < current_hour:
            st.error(f"【遅延】{l['task_master']['target_hour']}時: {l['task_master']['locations']['name']}")
    st.stop() # 管理者画面を表示したら下は表示しない

# --- D. スタッフ用業務画面 ---
st.title("薬石岩盤浴・業務管理")

# 4. 勤怠管理
st.divider()
st.subheader("🕙 タイムカード")
t_card_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).eq("work_date", today).order("clock_in_at", desc=True).limit(1).execute()
current_card = t_card_res.data[0] if t_card_res.data else None
br_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).eq("work_date", today).is_("break_end_at", "null").execute()
on_break = br_res.data[0] if br_res.data else None

c1, c2, c3 = st.columns(3)
if not current_card or current_card['clock_out_at']:
    if c1.button("🚀 出勤打刻", use_container_width=True, key="in"):
        supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":datetime.datetime.now().isoformat(), "work_date":today}).execute()
        st.rerun()
else:
    st.info(f"出勤中: {current_card['clock_in_at'][11:16]}")
    if not on_break:
        if c2.button("☕ 休憩入り", use_container_width=True, key="br_s"):
            supabase.table("breaks").insert({"staff_id":staff['id'], "timecard_id":current_card['id'], "break_start_at":datetime.datetime.now().isoformat(), "work_date":today}).execute()
            st.rerun()
        if c3.button("🏁 退勤打刻", use_container_width=True, type="primary", key="out"):
            supabase.table("timecards").update({"clock_out_at":datetime.datetime.now().isoformat()}).eq("id", current_card['id']).execute()
            st.rerun()
    else:
        st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
        if c2.button("🏃 業務戻り", use_container_width=True, type="primary", key="br_e"):
            supabase.table("breaks").update({"break_end_at":datetime.datetime.now().isoformat()}).eq("id", on_break['id']).execute()
            st.rerun()

# 5. タスク管理
st.divider()
if on_break: st.warning("休憩を終了してください")
else:
    # 今日のタスク生成
    tm_res = supabase.table("task_master").select("*").execute()
    for tm in tm_res.data:
        try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today, "status":"pending"}).execute()
        except: pass
    
    logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today).execute()
    logs_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0))

    tab1, tab2 = st.tabs(["📋 今日の業務", "🕒 履歴"])
    with tab1:
        st.write(f"### {current_hour}時台のタスク")
        for l in logs_data:
            t_h = l['task_master']['target_hour']
            if t_h == current_hour or t_h is None:
                cola, colb = st.columns([3, 1])
                cola.write(f"**{l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] == "pending":
                    if colb.button("着手", key=f"s_{l['id']}"):
                        supabase.table("task_logs").update({"status":"in_progress","started_at":datetime.datetime.now().isoformat(),"staff_id":staff['id']}).eq("id",l['id']).eq("status","pending").execute()
                        st.rerun()
                elif l['status'] == "in_progress": colb.warning("実施中")
                else: colb.success("完了")

    with tab2:
        st.write("### 履歴")
        h_res = supabase.table("timecards").select("*, breaks(*)").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
        if h_res.data:
            table = [{"日付":r['work_date'], "出勤":r['clock_in_at'][11:16], "退勤":r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data]
            st.table(table)

# 6. 業務遂行モード
active = next((l for l in logs_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)
if active and not on_break:
    st.divider()
    st.header(f"📍 実行中: {active['task_master']['locations']['name']}")
    qr_in = st.camera_input("QRスキャン", key="q")
    if qr_in and decode_qr(qr_in) == active['task_master']['locations']['qr_token']:
        st.success("現場到着。写真を撮影。")
        ph_in = st.camera_input("完了写真", key="p")
        if ph_in and st.button("送信完了", type="primary"):
            f_path = f"{active['id']}.jpg"
            supabase.storage.from_("task-photos").upload(f_path, ph_in.getvalue(), {"upsert":"true"})
            supabase.table("task_logs").update({"status":"completed","completed_at":datetime.datetime.now().isoformat(),"photo_url":f_path}).eq("id",active['id']).execute()
            st.balloons()
            st.rerun()