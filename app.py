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

st.set_page_config(page_title="天然薬石管理システム V1.2", layout="centered")

# --- 2. 日本時間の強制計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
current_hour = now_jst.hour
current_minute = now_jst.minute
today_jst = now_jst.date().isoformat()

# --- 3. セッション状態の初期化 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

# --- 4. 共通関数 ---
def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except:
        return ""

# --- A. ログイン画面 ---
if not st.session_state.logged_in:
    st.title("🛡️ 業務管理システム ログイン")
    with st.form("login"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- B. ログイン後のデータ取得 ---
staff = st.session_state.staff_info

# 勤怠・休憩ステータスを最初に定義
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None

b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).is_("break_end_at", "null").execute()
on_break = b_res.data[0] if b_res.data else None

# 今日の全タスクを取得
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# サイドバー設定
st.sidebar.title("MENU")
st.sidebar.write(f"👤 {staff['name']} 様")
st.sidebar.write(f"🕒 日本時刻: {current_hour:02d}:{current_minute:02d}")

admin_mode = False
if staff['role'] == 'admin':
    admin_mode = st.sidebar.checkbox("🚀 管理者ダッシュボード")

if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

# --- C. 管理者ダッシュボード ---
if admin_mode:
    st.title("📊 店舗運営状況")
    col1, col2 = st.columns(2)
    col1.metric("未完了タスク", len([l for l in l_data if l['status'] != 'completed']))
    
    st.subheader("⚠️ 遅延アラート")
    for l in l_data:
        t_h, t_m = l['task_master']['target_hour'] or 0, l['task_master']['target_minute'] or 0
        if l['status'] == 'pending' and (t_h < current_hour or (t_h == current_hour and t_m <= current_minute)):
            st.error(f"【遅延】{t_h:02d}:{t_m:02d} - {l['task_master']['locations']['name']}")

    st.subheader("📸 本日の完了報告写真")
    comp_logs = [l for l in l_data if l['status'] == 'completed']
    if comp_logs:
        cols = st.columns(3)
        for i, l in enumerate(comp_logs):
            with cols[i % 3]:
                st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=f"{l['task_master']['locations']['name']}")
    st.stop()

# --- D. スタッフ画面 ---
st.title("薬石岩盤浴 業務管理")

# 1. 勤怠UI
st.divider()
st.subheader("🕙 タイムカード ＆ 休憩")
c1, c2, c3 = st.columns(3)

if not curr_card or curr_card['clock_out_at']:
    if c1.button("🚀 出勤打刻", key="in"):
        supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":now_jst.isoformat(), "work_date":today_jst}).execute()
        st.rerun()
else:
    st.success(f"出勤中: {curr_card['clock_in_at'][11:16]}")
    if not on_break:
        if c2.button("☕ 休憩入り", key="b_s"):
            supabase.table("breaks").insert({"staff_id":staff['id'], "timecard_id":curr_card['id'], "break_start_at":now_jst.isoformat(), "work_date":today_jst}).execute()
            st.rerun()
        if c3.button("🏁 退勤打刻", type="primary", key="out"):
            supabase.table("timecards").update({"clock_out_at":now_jst.isoformat()}).eq("id", curr_card['id']).execute()
            st.rerun()
    else:
        st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
        if c2.button("🏃 業務戻り", type="primary", key="b_e"):
            supabase.table("breaks").update({"break_end_at":now_jst.isoformat()}).eq("id", on_break['id']).execute()
            st.rerun()

# 2. タスク管理
st.divider()
if on_break:
    st.warning("現在休憩中です。業務に戻る際は「業務戻り」を押してください。")
else:
    # タスク自動生成
    tms = supabase.table("task_master").select("*").execute()
    for tm in tms.data:
        try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
        except: pass

    tab1, tab2 = st.tabs(["📋 今日の業務", "🕒 履歴"])
    with tab1:
        st.write(f"### {current_hour}時台の予定")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == current_hour]
        if not display_tasks:
            st.write("この時間の予定はありません。")
        else:
            for l in display_tasks:
                col_a, col_b = st.columns([3, 1])
                t_h, t_m = l['task_master']['target_hour'], l['task_master']['target_minute']
                col_a.write(f"**【{t_h:02d}:{t_m:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] == "pending":
                    if col_b.button("着手", key=f"start_{l['id']}"):
                        supabase.table("task_logs").update({"status":"in_progress","started_at":now_jst.isoformat(),"staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.rerun()
                elif l['status'] == "in_progress": col_b.warning("実施中")
                else: col_b.success("完了")

    with tab2:
        st.write("### 過去の履歴")
        h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(5).execute()
        if h_res.data:
            st.table([{"日付":r['work_date'], "出勤":r['clock_in_at'][11:16], "退勤":r['clock_out_at'][11:16] if r['clock_out_at'] else "中"} for r in h_res.data])

# 3. 業務遂行モード（着手キャンセルボタン追加）
if not on_break:
    active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)
    if active_task:
        st.divider()
        # ここにキャンセルボタンを配置
        c_left, c_right = st.columns([3, 1])
        with c_left:
            st.error(f"📍 実行中: {active_task['task_master']['locations']['name']}")
        with c_right:
            if st.button("着手を取消", key=f"cancel_{active_task['id']}"):
                # DBステータスをpendingに戻す
                supabase.table("task_logs").update({
                    "status": "pending",
                    "started_at": None,
                    "staff_id": None
                }).eq("id", active_task['id']).execute()
                st.rerun()

        qr_in = st.camera_input("ステップ1：現場のQRをスキャン", key=f"qr_{active_task['id']}")
        if qr_in:
            scanned_data = decode_qr(qr_in)
            if scanned_data == active_task['task_master']['locations']['qr_token']:
                st.success("QR確認成功！清掃完了後に写真を撮影してください。")
                ph_in = st.camera_input("ステップ2：完了写真を撮影", key=f"photo_{active_task['id']}")
                if ph_in and st.button("報告を送信", type="primary", key=f"send_{active_task['id']}"):
                    f_path = f"{active_task['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_path, ph_in.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_path}).eq("id",active_task['id']).execute()
                    st.balloons()
                    st.rerun()
            else:
                st.error("場所が違います。正しい位置でスキャンしてください。")