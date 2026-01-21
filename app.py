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

# --- 1. システム設定 (ブランド名・アイコン) ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("システム設定（Secrets）が見つかりません。")
    st.stop()

JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')
APP_TITLE = "BE STONE" # ブランド名を「BE STONE」に固定

st.set_page_config(
    page_title=APP_TITLE, 
    page_icon="logo.png" if os.path.exists("logo.png") else "💎", 
    layout="wide", 
    initial_sidebar_state="auto"
)

# --- 2. 究極のデザインCSS（メニュー文字漆黒・ボタン黒靄除去・上部余白撤廃） ---
st.markdown("""
    <style>
    :root { color-scheme: light !important; }
    .stApp { background-color: #F8F9FA !important; color: #000000 !important; }
    
    /* 上部余白の最小化（メニューボタンは残す） */
    .main .block-container { padding-top: 1.5rem !important; padding-bottom: 0rem !important; }
    header[data-testid="stHeader"] { background: rgba(0,0,0,0) !important; color: #000000 !important; visibility: visible !important; }

    /* 文字色を「漆黒」に強制固定 */
    .stMarkdown, p, h1, h2, h3, span, label, li, div { color: #000000 !important; }

    /* モバイルサイドバー設定：横幅75% / 文字色「漆黒」 / デカ文字 */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { 
            width: 75vw !important; 
            min-width: 75vw !important; 
            background-color: #FFFFFF !important; 
        }
        /* メニュー（ラジオボタン）内の全てのテキストを純黒に強制 */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p,
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label span {
            color: #000000 !important;
            font-size: 24px !important;
            font-weight: 900 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        /* 項目間の余白 */
        div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
            padding: 30px 10px !important;
            border-bottom: 2px solid #EDF2F7 !important;
        }
    }
    
    /* PC版：中央寄せレイアウト */
    @media (min-width: 769px) { .main .block-container { max-width: 850px !important; margin: auto !important; } }

    /* ボタン：ターコイズブルー (#75C9D7) / 白文字 / 黒靄物理消去 */
    div.stButton > button, [data-testid="stCameraInput"] button {
        background-color: #75C9D7 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        height: 3.5em !important;
        font-weight: bold !important;
        box-shadow: none !important;
        opacity: 1 !important;
        transition: none !important;
    }
    div.stButton > button * { color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; }
    div.stButton > button[key="logout_btn"] { background-color: #FC8181 !important; }

    /* 不要パーツ隠蔽 */
    div[data-testid="stSidebarNav"] { display: none !important; }
    footer { visibility: hidden !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ログイン・同期管理（永続化） ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'staff_info' not in st.session_state: st.session_state.staff_info = None

saved_id = streamlit_js_eval(js_expressions='localStorage.getItem("staff_id")', key='L_ID')
saved_key = streamlit_js_eval(js_expressions='localStorage.getItem("session_key")', key='L_KEY')

if not st.session_state.logged_in and saved_id and saved_key:
    if str(saved_id) != "null":
        try: