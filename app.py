import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="NIPPO Pro - 期間抽出対応", page_icon="📑", layout="wide")
# --- 1. ページ設定 ---
st.set_page_config(page_title="NIPPO Pro", page_icon="📑", layout="wide")

# --- 追加：アプリの外観をプロ仕様にするCSS ---
st.markdown("""
    <style>
    /* 右上のメニューボタンを隠す */
    #MainMenu {visibility: hidden;}
    /* 下のフッター（Made with Streamlit）を隠す */
    footer {visibility: hidden;}
    /* ヘッダーの余計な線を消す */
    header {visibility: hidden;}
    /* 入力フォームの角を丸くする */
    .stTextInput>div>div>input {border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)
# --- 2. 接続 ---
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase = create_client(url, key)

if "user" not in st.session_state:
    st.session_state.user = None

# --- 認証画面 ---
def auth_screen():
    st.title("🔐 ログイン")
    choice = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    email = st.text_input("メールアドレス")
    password = st.text_input("パスワード", type="password")
    if st.button("実行"):
        try:
            if choice == "新規登録":
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("確認メールを送りました。")
            else:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")

# --- メインアプリ ---
def main_app():
    user = st.session_state.user
    st.sidebar.write(f"👤 {user.email}")
    if st.sidebar.button("ログアウト"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    tab1, tab2 = st.tabs(["✨ 日報登録", "🔎 閲覧・検索・一括出力"])

    # --- TAB 1: 登録 ---
    with tab1:
        with st.form("add"):
            st.subheader("日報登録")
            d = st.date_input("日付", value=datetime.now())
            n = st.text_input("担当者")
            l = st.text_input("場所")
            c = st.text_area("内容")
            if st.form_submit_button("保存"):
                supabase.table("nippo").insert({"date":str(d),"person":n,"location":l,"content":c,"user_id":user.id}).execute()
                st.success("保存完了")
                st.rerun()

    # --- TAB 2: 閲覧・期間抽出・一括編集 ---
    with tab2:
        st.subheader("データの抽出と管理")
        
        # 1. 期間指定フィルタ
        with st.container(border=True):
            f_col1, f_col2 = st.columns([2, 2])
            
            # 抽出期間の選択 (初期値は今月の1日〜今日)
            today = datetime.now()
            first_day_of_month = today.replace(day=1)
            
            with f_col1:
                date_range = st.date_input(
                    "📅 抽出期間を選択 (開始日 〜 終了日)",
                    value=(first_day_of_month, today),
                    help="カレンダーで開始日と終了日を選択してください。一週間分や一ヶ月分を自由に指定できます。"
                )
            
            with f_col2:
                search_kw = st.text_input("🔑 内容キーワードで絞り込み (任意)", placeholder="例: 打合せ 現場")

        # 期間が正しく選択されているか確認
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            
            # 2. Supabaseから指定期間のデータを一括取得
            res = supabase.table("nippo").select("*") \
                .eq("user_id", user.id) \
                .gte("date", str(start_date)) \
                .lte("date", str(end_date)) \
                .order("date", desc=True).execute()
            
            if res.data:
                df = pd.DataFrame(res.data)
                
                # キーワード絞り込み（手動）
                if search_kw:
                    patt = "|".join(search_kw.replace("　", " ").split(" "))
                    df = df[df["content"].str.contains(patt, na=False)]

                # --- 統計とCSV出力ボタン ---
                c1, c2 = st.columns([3, 1])
                c1.write(f"📊 **{start_date}** から **{end_date}** の表示結果: **{len(df)} 件**")
                
                # 【重要】表示されている全データをCSV化
                csv_all = df[["date", "person", "location", "content"]].rename(
                    columns={"date":"日付","person":"担当者","location":"場所","content":"内容"}
                ).to_csv(index=False).encode('utf-8-sig')
                
                c2.download_button(
                    label="📥 表示全データをCSV出力",
                    data=csv_all,
                    file_name=f"nippo_{start_date}_to_{end_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                st.info("💡 行をクリックすると、そのデータを下に個別編集・削除できます。")
                
                # 3. 選択機能付きデータフレーム
                event = st.dataframe(
                    df[["date", "person", "location", "content"]].rename(columns={"date":"日付","person":"担当者","location":"場所","content":"内容"}),
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    hide_index=True
                )

                # 4. 個別編集・削除処理
                if hasattr(event, 'selection') and len(event.selection.rows) > 0:
                    row_idx = event.selection.rows[0]
                    selected = df.iloc[row_idx]
                    
                    st.markdown("---")
                    st.subheader(f"🛠️ 選択中のデータを編集 (元の日付: {selected['date']})")
                    
                    with st.container(border=True):
                        u_date = st.date_input("修正日", value=datetime.strptime(selected['date'], '%Y-%m-%d'))
                        u_name = st.text_input("修正名", value=selected['person'])
                        u_loc = st.text_input("修正場所", value=selected['location'])
                        u_cont = st.text_area("修正内容", value=selected['content'])
                        
                        b1, b2 = st.columns(2)
                        if b1.button("🚀 この行を更新する"):
                            supabase.table("nippo").update({"date":str(u_date),"person":u_name,"location":u_loc,"content":u_cont}).eq("id", selected['id']).execute()
                            st.success("更新しました")
                            st.rerun()
                        if b2.button("🗑️ この行を削除する"):
                            supabase.table("nippo").delete().eq("id", selected['id']).execute()
                            st.success("削除しました")
                            st.rerun()
            else:
                st.warning(f"指定された期間 ({start_date} 〜 {end_date}) にデータはありません。")
        else:
            st.info("カレンダーで開始日と終了日の両方を選択してください。")

if st.session_state.user is None:
    auth_screen()
else:
    main_app()