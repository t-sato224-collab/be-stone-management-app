import streamlit as st
from supabase import create_client
import cv2
import numpy as np
from PIL import Image
import datetime
import pandas as pd
from streamlit_js_eval import streamlit_js_eval
from streamlit_autorefresh import st_autorefresh

# --- 1. システム設定 & デザイン設定 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

# initial_sidebar_stateを"auto"に変更し、スマホでもメニューを出せるようにします
st.set_page_config(page_title="天然薬石管理 Pro", layout="wide", initial_sidebar_state="auto")

# UIの微調整
st.markdown("""
    <style>
    /* ログアウトボタンを赤色で強調 */
    div.stButton > button:first-child[key="logout_btn"] { background-color: #ff4b4b; color: white; border-radius: 8px; }
    /* 標準のナビゲーション（ファイルリスト）のみを隠す */
    div[data-testid="stSidebarNav"] { display: none; }
    /* カメラ入力をスマホ画面いっぱいに広げる */
    .stCameraInput { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 日本時間の計算 ---
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()
current_hour = now_jst.hour

# --- 3. ログイン管理（LocalStorageからの自動復元） ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'staff_info' not in st.session_state:
    st.session_state.staff_info = None

# ブラウザから保存されたIDを取得（非同期実行）
saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='load_id')

# セッションが切れていてもブラウザがIDを覚えていればログイン状態を復元
if not st.session_state.logged_in and saved_id:
    res = supabase.table("staff").select("*").eq("staff_id", saved_id).execute()
    if res.data:
        st.session_state.logged_in = True
        st.session_state.staff_info = res.data[0]
        st.rerun()

# --- A. ログイン画面（未ログイン時のみ表示） ---
if not st.session_state.logged_in:
    st.title("🛡️ 業務管理システム ログイン")
    with st.form("login"):
        input_id = st.text_input("スタッフID")
        input_pass = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン"):
            res = supabase.table("staff").select("*").eq("staff_id", input_id).eq("password", input_pass).execute()
            if res.data:
                # ブラウザにIDを保存
                streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{input_id}")', key='save_id')
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
            else:
                st.error("IDまたはパスワードが正しくありません")
    st.stop()

# --- 4. 共通データ同期取得 ---
staff = st.session_state.staff_info

# 勤怠・休憩ステータス（全デバイス共通・DB最優先）
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# 今日のタスク一覧
logs_res = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
l_data = sorted(logs_res.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 実行中のタスクがあるか確認
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id']), None)

# 自動更新の設定（作業中でないときのみ30秒おきに更新）
if not active_task:
    st_autorefresh(interval=30000, key="global_ref")

# 共通QRデコード関数
def decode_qr(image):
    try:
        file_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)
        opencv_image = cv2.imdecode(file_bytes, 1)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(opencv_image)
        return data
    except: return ""

# モバイル判定
width = streamlit_js_eval(js_expressions='window.innerWidth', key='WIDTH', want_output=True)
is_mobile = width is not None and width < 768

# --- 5. 【核心】スマホ専用：業務遂行全画面モード ---
# 着手ボタンを押したときだけ、このブロックが発動し画面を独占します
if is_mobile and active_task and not on_break:
    st.title("📍 業務遂行中")
    st.error(f"場所: {active_task['task_master']['locations']['name']}")
    st.info(f"内容: {active_task['task_master']['task_name']}")
    
    if st.button("⬅️ 着手をキャンセルして戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "pending", "started_at": None, "staff_id": None}).eq("id", active_task['id']).execute()
        st.rerun()

    st.divider()
    qr_key = f"qrv_{active_task['id']}"
    if qr_key not in st.session_state: st.session_state[qr_key] = False

    if not st.session_state[qr_key]:
        st.write("📷 **STEP 1: 現場のQRをスキャン**")
        qr_in = st.camera_input("QRを枠に入れてください", key="m_qr")
        if qr_in:
            if decode_qr(qr_in) == active_task['task_master']['locations']['qr_token']:
                st.session_state[qr_key] = True
                st.success("QR照合完了！")
                st.rerun()
            else: st.error("場所が違います")
    else:
        st.write("📸 **STEP 2: 清掃後の証拠撮影**")
        ph_in = st.camera_input("完了写真を撮影", key="m_ph")
        if ph_in:
            if st.button("✅ 完了報告を送信", type="primary", use_container_width=True):
                f_p = f"{active_task['id']}.jpg"
                supabase.storage.from_("task-photos").upload(f_p, ph_in.getvalue(), {"upsert":"true"})
                supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",active_task['id']).execute()
                del st.session_state[qr_key]
                st.balloons()
                st.rerun()
    st.stop() # スマホ作業中はこの先を読み込ませない（メニューを隠す）

# --- B. 通常ナビゲーション（サイドバー） ---
st.sidebar.title("🏪 店舗管理メニュー")
st.sidebar.write(f"👤 **{staff['name']}** 様")

menu_options = ["📋 本日の業務", "🕒 マイ勤怠履歴"]
if staff['role'] == 'admin':
    menu_options += ["📊 リアルタイム監視", "📅 出勤簿データ出力"]

choice = st.sidebar.radio("機能を選択", menu_options)

# ログアウトボタン（位置調整）
for _ in range(8): st.sidebar.write("")
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
    streamlit_js_eval(js_expressions='localStorage.clear()', key='clear_id')
    st.session_state.logged_in = False
    st.rerun()

# --- C. 各画面のコンテンツ表示 ---

if choice == "📋 本日の業務":
    st.title("📋 本日の業務管理")
    st.info(f"🕒 現在の時刻: {now_jst.strftime('%H:%M')}")
    
    # 勤怠UI
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

    # タスク管理
    st.divider()
    if not curr_card: st.info("出勤打刻をしてください。")
    elif on_break: st.warning("休憩中です。")
    else:
        # 今日のタスク枠の自動生成
        if not l_data:
            tm_res = supabase.table("task_master").select("*").execute()
            for tm in tm_res.data:
                try: supabase.table("task_logs").insert({"task_id":tm["id"], "work_date":today_jst, "status":"pending"}).execute()
                except: pass
            st.rerun()
        
        st.subheader(f"{now_jst.hour:02d}時台のタスク")
        display_tasks = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        for l in display_tasks:
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
            elif l['status'] == "in_progress": colb.warning("他者が実施中")
            else: colb.success("完了")

        # PC用（画面遷移なし）
        if not is_mobile and active_task:
            st.divider()
            st.error(f"📍 遂行中: {active_task['task_master']['locations']['name']}")
            qr_pc = st.camera_input("QRスキャン", key="p_qr")
            if qr_pc and decode_qr(qr_pc) == active_task['task_master']['locations']['qr_token']:
                ph_pc = st.camera_input("写真撮影", key="p_ph")
                if ph_pc and st.button("報告送信", type="primary"):
                    f_p = f"{active_task['id']}.jpg"
                    supabase.storage.from_("task-photos").upload(f_p, ph_pc.getvalue(), {"upsert":"true"})
                    supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",active_task['id']).execute()
                    st.balloons(); st.rerun()

elif choice == "🕒 マイ勤怠履歴":
    st.title("🕒 あなたの勤怠履歴")
    h_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(20).execute()
    st.table(h_res.data)

elif choice == "📊 リアルタイム監視":
    st.title("📊 管理者ダッシュボード")
    l_res_adm = supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", today_jst).execute()
    l_data_adm = sorted(l_res_adm.data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))
    
    col1, col2 = st.columns(2)
    col1.metric("未完了タスク", len([l for l in l_data_adm if l['status'] != 'completed']))
    
    st.subheader("📸 本日の完了写真")
    comps = [l for l in l_data_adm if l['status'] == 'completed']
    cols = st.columns(4)
    for i, l in enumerate(comps):
        with cols[i % 4]: st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}", caption=l['task_master']['locations']['name'])

elif choice == "📅 出勤簿データ出力":
    st.title("📅 出勤簿データ抽出")
    # (既存のCSV出力ロジック)
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
            df_l.append({"名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "未"})
        st.dataframe(pd.DataFrame(df_l), use_container_width=True)