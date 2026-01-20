import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd # requirements.txtに追加してください

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="天然薬石管理システム V2.0", layout="wide")

# --- 2. 日本時間の強制計算 ---
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()
current_hour = now_jst.hour

# --- 3. セッション・ログイン管理 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

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
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else: st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- B. ログイン後のサイドバー・ナビゲーション ---
staff = st.session_state.staff_info
st.sidebar.title("店舗管理メニュー")
st.sidebar.write(f"👤 {staff['name']} 様")

# メニュー構成
menu_options = ["📋 本日の業務", "🕒 マイ勤怠履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 リアルタイム監視", "📅 出勤簿データ出力"]

choice = st.sidebar.radio("機能を選択", menu_options)

if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

# --- C. 画面遷移ロジック ---

# 1. 本日の業務画面
if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    
    # 勤怠・休憩
    t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).order("clock_in_at", desc=True).limit(1).execute()
    curr_card = t_res.data[0] if t_res.data else None
    b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).is_("break_end_at", "null").execute()
    on_break = b_res.data[0] if b_res.data else None

    c1, c2, c3 = st.columns(3)
    if not curr_card or curr_card['clock_out_at']:
        if c1.button("🚀 出勤打刻", key="in"):
            supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":now_jst.isoformat(), "work_date":today_jst}).execute()
            st.rerun()
    else:
        st.success(f"出勤中: {curr_card['clock_in_at'][11:16]}")
        if not on_break:
            if c2.button("☕ 休憩入り"):
                supabase.table("breaks").insert({"staff_id":staff['id'], "timecard_id":curr_card['id'], "break_start_at":now_jst.isoformat(), "work_date":today_jst}).execute()
                st.rerun()
            if c3.button("🏁 退勤打刻", type="primary"):
                supabase.table("timecards").update({"clock_out_at":now_jst.isoformat()}).eq("id", curr_card['id']).execute()
                st.rerun()
        else:
            st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
            if c2.button("🏃 業務戻り", type="primary"):
                supabase.table("breaks").update({"break_end_at":now_jst.isoformat()}).eq("id", on_break['id']).execute()
                st.rerun()

    # タスク
    if on_break: st.warning("休憩を終了してください")
    elif curr_card and not curr_card['clock_out_at']:
        tms = supabase.table("task_master").select("*").execute()
        for tm in tms.data:
            try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
            except: pass
        logs = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
        l_data = sorted(logs.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
        
        st.write(f"### {current_hour}時台のタスク")
        for l in l_data:
            if l['task_master']['target_hour'] == current_hour:
                cola, colb = st.columns([3, 1])
                cola.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**")
                if l['status'] == "pending":
                    if colb.button("着手", key=l['id']):
                        supabase.table("task_logs").update({"status":"in_progress","started_at":now_jst.isoformat(),"staff_id":staff['id']}).eq("id",l['id']).execute()
                        st.rerun()
                elif l['status'] == "in_progress" and l['staff_id'] == staff['id']:
                    if colb.button("取消", key=f"c_{l['id']}"):
                        supabase.table("task_logs").update({"status":"pending","started_at":None,"staff_id":None}).eq("id",l['id']).execute()
                        st.rerun()
                elif l['status'] == "in_progress": colb.warning("他者が実施中")
                else: colb.success("完了")

        # 遂行
        active = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)
        if active:
            st.divider()
            st.error(f"📍 遂行中: {active['task_master']['locations']['name']}")
            qr = st.camera_input("QRスキャン")
            if qr and decode_qr(qr) == active['task_master']['locations']['qr_token']:
                ph = st.camera_input("完了写真")
                if ph and st.button("送信完了", type="primary"):
                    f_path = f"{active['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_path, ph.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_path}).eq("id",active['id']).execute()
                    st.balloons()
                    st.rerun()

# 2. マイ勤怠履歴画面
elif choice == "🕒 マイ勤怠履歴":
    st.title("🕒 あなたの勤怠・業務履歴")
    h_res = supabase.table("timecards").select("*, breaks(*)").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    if h_res.data:
        history = []
        for r in h_res.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_mins = sum([(datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).seconds // 60 for b in r.get('breaks', []) if b['break_end_at']])
            history.append({"日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "勤務中", "休憩計": f"{br_mins}分"})
        st.table(history)

# 3. リアルタイム監視画面 (Admin)
elif choice == "📊 リアルタイム監視":
    st.title("📊 管理者ダッシュボード（リアルタイム）")
    l_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    l_data = sorted(l_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
    
    col1, col2 = st.columns(2)
    col1.metric("未完了タスク", len([l for l in l_data if l['status'] != 'completed']))
    
    st.subheader("⚠️ 遅延アラート")
    for l in l_data:
        t_h, t_m = l['task_master']['target_hour'] or 0, l['task_master']['target_minute'] or 0
        if l['status'] == 'pending' and (t_h < now_jst.hour or (t_h == now_jst.hour and t_m <= now_jst.minute)):
            st.error(f"【遅延】{t_h:02d}:{t_m:02d} - {l['task_master']['locations']['name']}")

    st.subheader("📸 本日の報告写真")
    comp_logs = [l for l in l_data if l['status'] == 'completed']
    if comp_logs:
        cols = st.columns(4)
        for i, l in enumerate(comp_logs):
            with cols[i % 4]:
                st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=f"{l['task_master']['locations']['name']}")

# 4. 出勤簿データ出力画面 (Admin)
elif choice == "📅 出勤簿データ出力":
    st.title("📅 出勤簿データ抽出・CSV出力")
    
    all_s_res = supabase.table("staff").select("id, name").order("name").execute()
    staff_dict = {s['name']: s['id'] for s in all_s_res.data}
    
    col_a, col_b, col_c = st.columns(3)
    target_staff = col_a.selectbox("スタッフ選択", ["-- 全員 --"] + list(staff_dict.keys()))
    start_d = col_b.date_input("開始日", datetime.date.today() - datetime.timedelta(days=30))
    end_d = col_c.date_input("終了日", datetime.date.today())

    query = supabase.table("timecards").select("*, breaks(*)").gte("work_date", start_d.isoformat()).lte("work_date", end_d.isoformat())
    if target_staff != "-- 全員 --":
        query = query.eq("staff_id", staff_dict[target_staff])
    
    data = query.order("work_date", desc=True).execute()

    if data.data:
        df_list = []
        for r in data.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_sec = sum([(datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() for b in r.get('breaks', []) if b['break_end_at']])
            
            work_str = "--"
            if c_out:
                actual_sec = max(0, (c_out - c_in).total_seconds() - br_sec)
                work_str = f"{int(actual_sec // 3600)}時間{int((actual_sec % 3600) // 60)}分"

            df_list.append({
                "名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"),
                "退勤": c_out.strftime("%H:%M") if c_out else "未打刻", "休憩(分)": int(br_sec // 60), "実働時間": work_str
            })
        
        df = pd.DataFrame(df_list)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 CSVダウンロード", df.to_csv(index=False).encode('utf_8_sig'), f"attendance_{start_d}_{end_d}.csv", "text/csv")