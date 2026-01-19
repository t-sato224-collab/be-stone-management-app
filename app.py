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

# --- 2. 【最重要】日本時間の強制計算 ---
# サーバーの時間(UTC)に9時間を足して、強制的に日本時間を作ります
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
    file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
    opencv_image = cv2.imdecode(file_bytes, 1)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(opencv_image)
    return data

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
            else: st.error("IDまたはパスワードが違います")
    st.stop()

# --- B. メイン画面 ---
staff = st.session_state.staff_info
st.sidebar.title("MENU")
st.sidebar.write(f"👤 {staff['name']} 様")
# デバッグ用：ここに表示される時間が「19時台」なら成功です
st.sidebar.write(f"🕒 現在の日本時刻: {current_hour:02d}:{current_minute:02d}")

admin_mode = False
if staff['role'] == 'admin':
    admin_mode = st.sidebar.checkbox("🚀 管理者ダッシュボード")
if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

# --- C. 管理者ダッシュボード ---
if admin_mode:
    st.title("📊 店舗運営状況")
    logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("出勤中", len(supabase.table("timecards").select("id").eq("work_date", today_jst).is_("clock_out_at", "null").execute().data))
    col2.metric("未完了タスク", len([l for l in l_data if l['status'] != 'completed']))

    st.subheader("⚠️ 遅延アラート")
    for l in l_data:
        t_h, t_m = l['task_master']['target_hour'] or 0, l['task_master']['target_minute'] or 0
        if l['status'] == 'pending' and (t_h < current_hour or (t_h == current_hour and t_m <= current_minute)):
            st.error(f"【遅延】{t_h:02d}:{t_m:02d} - {l['task_master']['locations']['name']}")
    st.stop()

# --- D. スタッフ画面 ---
st.title("薬石岩盤浴 業務管理")
st.info(f"現在の日本時刻は {current_hour:02d}:{current_minute:02d} です")

# 5. 勤怠・休憩
st.divider()
st.subheader("🕙 タイムカード ＆ 休憩")
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None

if not curr_card or curr_card['clock_out_at']:
    if st.button("🚀 出勤打刻", key="in_btn"):
        supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":now_jst.isoformat(), "work_date":today_jst}).execute()
        st.rerun()
else:
    st.success(f"出勤中: {curr_card['clock_in_at'][11:16]}")
    if st.button("🏁 退勤打刻", type="primary", key="out_btn"):
        supabase.table("timecards").update({"clock_out_at":now_jst.isoformat()}).eq("id", curr_card['id']).execute()
        st.rerun()

# 6. タスク管理
st.divider()
# タスクの自動生成
tms = supabase.table("task_master").select("*").execute()
for tm in tms.data:
    try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
    except: pass

logs = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 「現在の1時間以内」のタスクだけを表示する
st.write(f"### {current_hour}時台の予定")
display_tasks = [l for l in l_data if l['task_master']['target_hour'] == current_hour]

if not display_tasks:
    st.write("この時間の予定はありません。")
else:
    for l in display_tasks:
        col_a, col_b = st.columns([3, 1])
        col_a.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
        if l['status'] == "pending":
            if col_b.button("着手", key=l['id']):
                supabase.table("task_logs").update({"status":"in_progress","started_at":now_jst.isoformat(),"staff_id":staff['id']}).eq("id",l['id']).execute()
                st.rerun()
        elif l['status'] == "in_progress": col_b.warning("実施中")
        else: col_b.success("完了")
        # --- 6. 業務遂行モード（修正版：カメラを最優先表示） ---
# 自分が「実施中」にしているタスクを探す
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

if active_task and not on_break:
    st.divider()
    # 進行中のタスクを画面の一番上に持ってくるための強調
    st.error(f"🚨 現在実行中の業務があります: {active_task['task_master']['locations']['name']}")
    st.subheader("ステップ1：現場のQRコードをスキャン")
    
    # keyをユニークにするためにlogのIDを混ぜる
    qr_in = st.camera_input("QRコードを枠内に収めてください", key=f"qr_cam_{active_task['id']}")
    
    if qr_in:
        scanned_data = decode_qr(qr_in)
        if scanned_data == active_task['task_master']['locations']['qr_token']:
            st.success("✅ 現地到着を確認しました！")
            st.subheader("ステップ2：清掃後の証拠写真を撮影")
            
            ph_in = st.camera_input("完了写真を撮影してください", key=f"photo_cam_{active_task['id']}")
            if ph_in:
                if st.button("報告を送信して完了する", type="primary", key=f"send_{active_task['id']}"):
                    # 写真保存
                    f_path = f"{active_task['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_path, ph_in.getvalue(), {"upsert":"true"})
                    # DB更新
                    supabase.table("task_logs").update({
                        "status":"completed",
                        "completed_at":now_jst.isoformat(),
                        "photo_url":f_path
                    }).eq("id",active_task['id']).execute()
                    st.balloons()
                    st.rerun()
        else:
            st.error("❌ 場所が違います。正しいエリアのQRコードをスキャンしてください。")