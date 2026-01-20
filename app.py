import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd

# --- 1. システム設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(page_title="天然薬石管理システム Pro", layout="wide")

# --- 2. CSSによるUI調整（ログアウトボタンを最下部に固定） ---
st.markdown("""
    <style>
    /* サイドバーのログアウトエリアを強調し、余白を強制的に作る */
    .stButton > button[kind="primary"] {
        background-color: #ff4b4b;
        color: white;
    }
    div[data-testid="stSidebarNav"] {
        display: none;
    }
    </style>
    """, unsafe_allow_stdio=True)

# --- 3. 日本時間の計算 ---
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()
current_hour = now_jst.hour
current_minute = now_jst.minute

# --- 4. セッション・共通関数 ---
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

# --- B. サイドバー（極端な分離レイアウト） ---
staff = st.session_state.staff_info
st.sidebar.title("🏪 管理メニュー")

# 1. ユーザー情報と設定
st.sidebar.write(f"👤 **{staff['name']}** 様")
with st.sidebar.expander("🔑 パスワード変更"):
    with st.form("pw_change"):
        new_p = st.text_input("新パスワード", type="password")
        if st.form_submit_button("更新"):
            if len(new_p) >= 4:
                supabase.table("staff").update({"password": new_p}).eq("id", staff['id']).execute()
                st.session_state.staff_info['password'] = new_p
                st.success("更新成功")
            else: st.error("4文字以上")

st.sidebar.divider()

# 2. メイン機能選択
menu_options = ["📋 本日の業務", "🕒 マイ勤怠履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 リアルタイム監視", "📅 出勤簿データ出力"]

choice = st.sidebar.radio("機能を切り替え", menu_options)

# 3. 極端な空白の挿入（30行分の空白を作り、ボタンを画面外近くまで押し下げる）
for _ in range(30):
    st.sidebar.write("")

st.sidebar.divider()

# 4. ログアウトボタン（最下部へ隔離）
# 誤操作防止のため「確認用チェックボックス」を挟む二段構えにします
st.sidebar.warning("⚠️ アカウント操作")
if st.sidebar.button("🚪 システムをログアウト", use_container_width=True, help="ログアウトします"):
    st.session_state.logged_in = False
    st.rerun()


# --- C. メイン画面遷移ロジック ---

if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.write(f"🕒 現在時刻: {current_hour:02d}:{current_minute:02d}")
    
    # 勤怠・休憩
    t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).order("clock_in_at", desc=True).limit(1).execute()
    curr_card = t_res.data[0] if t_res.data else None
    b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).eq("work_date", today_jst).is_("break_end_at", "null").execute()
    on_break = b_res.data[0] if b_res.data else None

    c1, c2, c3 = st.columns(3)
    if not curr_card or curr_card['clock_out_at']:
        if c1.button("🚀 出勤打刻", use_container_width=True, key="in_btn"):
            supabase.table("timecards").insert({"staff_id":staff['id'], "staff_name":staff['name'], "clock_in_at":now_jst.isoformat(), "work_date":today_jst}).execute()
            st.rerun()
    else:
        st.success(f"出勤中: {curr_card['clock_in_at'][11:16]}")
        if not on_break:
            if c2.button("☕ 休憩入り", use_container_width=True):
                supabase.table("breaks").insert({"staff_id":staff['id'], "timecard_id":curr_card['id'], "break_start_at":now_jst.isoformat(), "work_date":today_jst}).execute()
                st.rerun()
            if c3.button("🏁 退勤打刻", use_container_width=True, type="primary"):
                supabase.table("timecards").update({"clock_out_at":now_jst.isoformat()}).eq("id", curr_card['id']).execute()
                st.rerun()
        else:
            st.warning(f"休憩中 ({on_break['break_start_at'][11:16]}〜)")
            if c2.button("🏃 業務戻り", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at":now_jst.isoformat()}).eq("id", on_break['id']).execute()
                st.rerun()

    # タスク管理
    if on_break: st.warning("休憩を終了してください")
    elif curr_card and not curr_card['clock_out_at']:
        # 今日のログ生成
        tm_res = supabase.table("task_master").select("*").execute()
        for tm in tm_res.data:
            try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
            except: pass
            
        logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
        l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
        
        st.divider()
        st.subheader(f"{current_hour}時台のタスク")
        for l in l_data:
            if l['task_master']['target_hour'] == current_hour:
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

        # 業務遂行モード
        active = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)
        if active:
            st.divider()
            st.error(f"📍 実行中: {active['task_master']['locations']['name']}")
            qr = st.camera_input("QRスキャン", key=f"qr_{active['id']}")
            if qr and decode_qr(qr) == active['task_master']['locations']['qr_token']:
                st.success("到着を確認。")
                ph = st.camera_input("完了写真", key=f"ph_{active['id']}")
                if ph and st.button("報告を送信", type="primary", key=f"send_{active['id']}"):
                    f_path = f"{active['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_path, ph.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_path}).eq("id",active['id']).execute()
                    st.balloons()
                    st.rerun()

elif choice == "🕒 マイ勤怠履歴":
    st.title("🕒 あなたの勤怠履歴")
    h_res = supabase.table("timecards").select("*, breaks(*)").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    if h_res.data:
        history = []
        for r in h_res.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_m = sum([(datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).seconds // 60 for b in r.get('breaks', []) if b['break_end_at']])
            history.append({"日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "中", "休憩計": f"{br_m}分"})
        st.table(history)

elif choice == "📊 リアルタイム監視":
    st.title("📊 管理者ダッシュボード")
    l_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    l_data = sorted(l_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
    
    c1, c2 = st.columns(2)
    c1.metric("未完了タスク", len([l for l in l_data if l['status'] != 'completed']))
    
    st.subheader("⚠️ 遅延アラート")
    for l in l_data:
        t_h, t_m = l['task_master']['target_hour'] or 0, l['task_master']['target_minute'] or 0
        if l['status'] == 'pending' and (t_h < now_jst.hour or (t_h == now_jst.hour and t_m <= now_jst.minute)):
            st.error(f"【遅延】{t_h:02d}:{t_m:02d} - {l['task_master']['locations']['name']}")

    st.subheader("📸 本日の報告写真")
    comp_l = [l for l in l_data if l['status'] == 'completed']
    if comp_l:
        cols = st.columns(4)
        for i, l in enumerate(comp_l):
            with cols[i % 4]:
                st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=f"{l['task_master']['locations']['name']}")

elif choice == "📅 出勤簿データ出力":
    st.title("📅 出勤簿データ抽出・CSV出力")
    all_s = supabase.table("staff").select("id, name").order("name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    
    ca, cb, cc = st.columns(3)
    t_staff = ca.selectbox("スタッフ選択", ["-- 全員 --"] + list(s_dict.keys()))
    s_d = cb.date_input("開始日", datetime.date.today() - datetime.timedelta(days=30))
    e_d = cc.date_input("終了日", datetime.date.today())

    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if t_staff != "-- 全員 --": q = q.eq("staff_id", s_dict[t_staff])
    data = q.order("work_date", desc=True).execute()

    if data.data:
        df_l = []
        for r in data.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_s = sum([(datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() for b in r.get('breaks', []) if b['break_end_at']])
            w_str = "--"
            if c_out:
                act_s = max(0, (c_out - c_in).total_seconds() - br_s)
                w_str = f"{int(act_s // 3600)}時間{int((act_s % 3600) // 60)}分"
            df_l.append({"名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "未打刻", "休憩(分)": int(br_s // 60), "実働時間": w_str})
        
        df = pd.DataFrame(df_l)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 CSVダウンロード", df.to_csv(index=False).encode('utf_8_sig'), f"attendance_{s_d}.csv", "text/csv")