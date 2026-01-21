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
import os

# --- 1. システム設定 ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("システム設定が見つかりません。")
    st.stop()

JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')

st.set_page_config(
    page_title="BE STONE Pro", 
    page_icon="logo.png" if os.path.exists("logo.png") else "💎", 
    layout="wide", 
    initial_sidebar_state="auto"
)

# --- 2. デザインCSS（視認性・漆黒文字・レイアウト） ---
st.markdown("""
    <style>
    :root { color-scheme: light !important; }
    .stApp { background-color: #F8F9FA !important; color: #000000 !important; }
    header { visibility: hidden !important; height: 0 !important; }
    .main .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    
    /* モバイルサイドバー設定 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 75vw !important; min-width: 75vw !important; background-color: #FFFFFF !important; }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {
            color: #000000 !important; font-size: 24px !important; font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            padding: 30px 10px !important; border-bottom: 2px solid #EDF2F7 !important;
        }
    }
    @media (min-width: 769px) { .main .block-container { max-width: 850px !important; margin: auto !important; } }

    /* ボタンデザイン */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; height: 3.5em !important; font-weight: bold !important;
        box-shadow: none !important; opacity: 1 !important;
    }
    div.stButton > button * { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }

    .app-card {
        background-color: #FFFFFF !important; padding: 25px; border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.03); border: 1px solid #EDF2F7; margin-bottom: 20px;
    }
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. キャッシュ・ロジック ---
@st.cache_data(ttl=30)
def get_task_logs_cached(date_str):
    return supabase.table("task_logs").select("*, task_master(*, locations(*))").eq("work_date", date_str).execute().data

# --- 4. ログイン管理（自動復旧） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

if not st.session_state.logged_in and saved_id and saved_key:
    if str(saved_id) != "null":
        try:
            res = supabase.table("staff").select("*").eq("staff_id", saved_id).eq("session_key", saved_key).execute()
            if res.data:
                st.session_state.logged_in = True
                st.session_state.staff_info = res.data[0]
                st.rerun()
        except: pass

if not st.session_state.logged_in:
    if saved_id is None:
        st_autorefresh(interval=1500, limit=2, key="sync_init"); st.stop()
    c_l, c_m, c_r = st.columns([1, 2, 1])
    with c_m:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center; color: #75C9D7; margin-top: 0;'>BE STONE ログイン</h2>", unsafe_allow_html=True)
        with st.form("login_f"):
            u_id = st.text_input("STAFF ID")
            u_pw = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("SYSTEM LOGIN", use_container_width=True):
                res = supabase.table("staff").select("*").eq("staff_id", u_id).eq("password", u_pw).execute()
                if res.data:
                    new_key = str(uuid.uuid4())
                    supabase.table("staff").update({"session_key": new_key}).eq("staff_id", u_id).execute()
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("staff_id", "{u_id}")')
                    streamlit_js_eval(js_expressions=f'localStorage.setItem("session_key", "{new_key}")')
                    st.session_state.logged_in = True; st.session_state.staff_info = res.data[0]; st.rerun()
                else: st.error("ID / PW不一致")
    st.stop()

# --- 5. ログイン後処理 ---
staff = st.session_state.staff_info
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
today_jst = now_jst.date().isoformat()

# 同期データ取得
t_res = supabase.table("timecards").select("*").eq("staff_id", staff['id']).is_("clock_out_at", "null").order("clock_in_at", desc=True).limit(1).execute()
curr_card = t_res.data[0] if t_res.data else None
b_res = supabase.table("breaks").select("*").eq("staff_id", staff['id']).is_("break_end_at", "null").order("break_start_at", desc=True).limit(1).execute()
on_break = b_res.data[0] if b_res.data else None

# タスク自動生成
try:
    existing = supabase.table("task_logs").select("id").eq("work_date", today_jst).limit(1).execute()
    if not existing.data:
        tm_data = supabase.table("task_master").select("*").execute()
        for tm in tm_data.data:
            supabase.table("task_logs").insert({"task_id": tm["id"], "work_date": today_jst, "status": "pending"}).execute()
        st.cache_data.clear(); st.rerun()
except: pass

l_data = get_task_logs_cached(today_jst)
l_data = sorted(l_data, key=lambda x: (x['task_master']['target_hour'] or 0, x['task_master']['target_minute'] or 0))

# 【修正要件③】active_taskを「今の時間」に限定
active_task = next((l for l in l_data if l['status'] == "in_progress" and l['staff_id'] == staff['id'] and l['task_master']['target_hour'] == now_jst.hour), None)

# モバイル判定（要因②対策：安全な判定）
width = streamlit_js_eval(js_expressions='window.innerWidth', key='W_WIDTH', want_output=True)
is_mobile = isinstance(width, (int, float)) and width < 768

# --- 共通関数：業務遂行モード ---
def render_task_execution(task):
    st.markdown(f"<div class='app-card'><h2 style='color:#75C9D7;margin:0;'>📍 遂行中: {task['task_master']['locations']['name']}</h2></div>", unsafe_allow_html=True)
    if st.button("⏸️ 中断してリストに戻る", use_container_width=True):
        supabase.table("task_logs").update({"status": "interrupted"}).eq("id", task['id']).execute(); st.cache_data.clear(); st.rerun()
    st.divider()
    qr_v_key = f"qr_v_{task['id']}"
    if qr_v_key not in st.session_state: st.session_state[qr_v_key] = False
    
    cam_input = st.camera_input("認証・報告カメラ", key=f"cam_{task['id']}")
    if cam_input:
        img = cv2.imdecode(np.asarray(bytearray(cam_input.read()), dtype=np.uint8), 1)
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if not st.session_state[qr_v_key]:
            if data == task['task_master']['locations']['qr_token']:
                st.session_state[qr_v_key] = True; st.success("QR確認成功！"); st.rerun()
            else: st.error("場所が違います")
        else:
            if st.button("✅ 報告して完了", type="primary", use_container_width=True):
                f_p = f"{task['id']}.jpg"
                supabase.storage.from_("task-photos").upload(f_p, cam_input.getvalue(), {"upsert":"true"})
                supabase.table("task_logs").update({"status":"completed","completed_at":now_jst.isoformat(),"photo_url":f_p}).eq("id",task['id']).execute()
                st.cache_data.clear(); del st.session_state[qr_v_key]; st.balloons(); st.rerun()

# --- B. サイドバー ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"<div style='text-align:center; padding:10px; color:#000000;'><b>{staff['name']} 様</b></div>", unsafe_allow_html=True)
    st.divider()
    menu_options = ["📋 本日の業務", "⚠️ 未完了タスク", "🕒 履歴"]
    if staff['role'] == 'admin': menu_options += ["📊 監視(Admin)", "📅 出勤簿(Admin)"]
    choice = st.sidebar.radio("MENU", menu_options, key="nav")
    for _ in range(8): st.write("")
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        supabase.table("staff").update({"session_key": None}).eq("id", staff['id']).execute()
        streamlit_js_eval(js_expressions='localStorage.clear()'); st.session_state.logged_in = False; st.rerun()

# --- C. メインエリアの条件分岐（要因①・③対策） ---

# 自動更新
if not active_task: st_autorefresh(interval=30000, key="global_ref")

st.markdown("<h1 style='color: #75C9D7; margin-top: 0; margin-bottom: 0;'>BE STONE</h1>", unsafe_allow_html=True)
st.caption(f"{now_jst.strftime('%Y/%m/%d %H:%M')} | {staff['name']}")

if choice == "📋 本日の業務":
    # 【修正要件①】モバイル作業中、かつ「本日の業務」選択時のみ画面をロックする
    if is_mobile and active_task and not on_break:
        render_task_execution(active_task)
        st.stop() # ここで止めるのはTaskページ内だけなので他のメニューは死なない

    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.subheader("🕙 TIME CARD")
    c1, c2, c3 = st.columns(3)
    if not curr_card:
        if c1.button("🚀 出勤打刻", use_container_width=True):
            supabase.table("timecards").insert({"staff_id": staff['id'], "staff_name": staff['name'], "clock_in_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.cache_data.clear(); st.rerun()
    else:
        st.write(f"出勤中: **{curr_card['clock_in_at'][11:16]}**")
        if not on_break:
            if c2.button("☕ 休憩", use_container_width=True):
                supabase.table("breaks").insert({"staff_id": staff['id'], "timecard_id": curr_card['id'], "break_start_at": now_jst.isoformat(), "work_date": today_jst}).execute(); st.rerun()
            if c3.button("🏁 退勤", use_container_width=True):
                supabase.table("timecards").update({"clock_out_at": now_jst.isoformat()}).eq("id", curr_card['id']).execute(); st.rerun()
        else:
            if c2.button("🏃 復帰", use_container_width=True, type="primary"):
                supabase.table("breaks").update({"break_end_at": now_jst.isoformat()}).eq("id", on_break['id']).execute(); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if curr_card and not on_break:
        if not is_mobile and active_task: render_task_execution(active_task)
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader(f"📋 今の時間帯の予定 ({now_jst.hour:02d}時台)")
        tasks_now = [l for l in l_data if l['task_master']['target_hour'] == now_jst.hour]
        if not tasks_now: st.info("予定はありません。")
        else:
            for l in tasks_now:
                st.markdown("<div style='border-bottom: 1px solid #EDF2F7; padding: 15px 0;'>", unsafe_allow_html=True)
                ca, cb = st.columns([3, 1])
                ca.write(f"**【{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d}】 {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
                if l['status'] in ["pending", "interrupted"]:
                    if cb.button("着手" if l['status']=="pending" else "再開", key=f"s_{l['id']}", use_container_width=True):
                        supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.cache_data.clear(); st.rerun()
                elif l['status'] == "in_progress": cb.warning("Busy")
                else: cb.success("OK")
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

elif choice == "⚠️ 未完了タスク":
    overdue = [l for l in l_data if l['task_master']['target_hour'] < now_jst.hour and l['status'] != "completed"]
    if not overdue: st.success("全て完了しています！")
    else:
        for l in overdue:
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            ca, cb = st.columns([3, 1])
            ca.write(f"**【遅延】{l['task_master']['target_hour']:02d}:{l['task_master']['target_minute']:02d} - {l['task_master']['locations']['name']}**\n{l['task_master']['task_name']}")
            if cb.button("リカバリー", key=f"rec_{l['id']}", use_container_width=True, type="primary"):
                supabase.table("task_logs").update({"status":"in_progress","staff_id":staff['id']}).eq("id",l['id']).execute(); st.cache_data.clear(); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

elif choice == "🕒 履歴":
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    res = supabase.table("timecards").select("*, breaks(*)").eq("staff_id", staff['id']).order("clock_in_at", desc=True).limit(10).execute()
    for r in res.data:
        c_in, c_out = datetime.datetime.fromisoformat(r['clock_in_at']), (datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None)
        br_m = sum([int((datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() // 60) for b in r.get('breaks', []) if b['break_end_at']])
        act_m = (int((c_out - c_in).total_seconds() // 60) - br_m) if c_out else 0
        h, m = divmod(act_m, 60)
        t_color = "red" if act_m >= 420 else "#000000"
        st.markdown(f"**📅 {c_in.strftime('%Y年%m月%d日')}** / {c_in.strftime('%H:%M')}〜{c_out.strftime('%H:%M') if c_out else '中'} / <span style='color:{t_color};'>実働：{h:02d}:{m:02d}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif "監視" in choice:
    l_adm = [l for l in l_data if l['status'] == 'completed']
    for l in l_adm:
        with st.container():
            st.markdown("<div class='app-card'>", unsafe_allow_html=True)
            st.write(f"**{l['task_master']['locations']['name']}** (完了: {l['completed_at'][11:16]})")
            st.image(f"{url}/storage/v1/object/public/task-photos/{l['photo_url']}")
            st.markdown("</div>", unsafe_allow_html=True)

elif "出勤簿" in choice:
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    all_s = supabase.table("staff").select("id, name").execute()
    s_dict = {s['name']: s['id'] for s in all_s.data}
    target = st.selectbox("STAFF", ["-- 全員 --"] + list(s_dict.keys()), key="adm_staff")
    s_d, e_d = st.date_input("START", datetime.date.today()-datetime.timedelta(days=30)), st.date_input("END", datetime.date.today())
    q = supabase.table("timecards").select("*, breaks(*)").gte("work_date", s_d.isoformat()).lte("work_date", e_d.isoformat())
    if target != "-- 全員 --": q = q.eq("staff_id", s_dict[target])
    data = q.order("work_date", desc=True).execute()
    if data.data:
        df_l = []
        for r in data.data:
            c_in = datetime.datetime.fromisoformat(r['clock_in_at'])
            c_out = datetime.datetime.fromisoformat(r['clock_out_at']) if r['clock_out_at'] else None
            br_m = sum([int((datetime.datetime.fromisoformat(b['break_end_at']) - datetime.datetime.fromisoformat(b['break_start_at'])).total_seconds() // 60) for b in r.get('breaks', []) if b['break_end_at']])
            act_m = (int((c_out - c_in).total_seconds() // 60) - br_m) if c_out else 0
            h, m = divmod(act_m, 60)
            df_l.append({"名前": r['staff_name'], "日付": r['work_date'], "出勤": c_in.strftime("%H:%M"), "退勤": c_out.strftime("%H:%M") if c_out else "未", "休憩(分)": br_m, "実働(00:00)": f"{h:02d}:{m:02d}", "分": act_m})
        df = pd.DataFrame(df_l)
        def style_red(row): return ['color: red' if row['分'] >= 420 else '' for _ in row]
        st.dataframe(df.drop(columns=['分']).style.apply(style_red, axis=1), use_container_width=True)