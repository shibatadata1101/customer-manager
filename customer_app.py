import streamlit as st
import re
from google import genai
import json
import gspread
from google.oauth2.service_account import Credentials

# =========================================================
# ⚙️ 初期設定（Gemini ＆ Googleスプレッドシート）
# =========================================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11zXSrk1YqlsxqxFcMCbe_64Hso3KOoR5qqm4K69RGHo/edit?gid=0#gid=0"

# 一番確実な金庫（Secrets）からの読み込み
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def connect_to_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(SPREADSHEET_URL)
    return sh.get_worksheet(0)

# =========================================================
# 📱 画面の構築 (Streamlit UI)
# =========================================================
st.title("📱 爆速・顧客受付＆検索システム")

tab1, tab2 = st.tabs(["📝 受付メモ入力", "🔍 営業用・爆速検索"])

with tab1:
    st.info("🔒 **安心セキュリティ**: 4桁以上の数字は自動消去されます。")
    
    if "input_key" not in st.session_state:
        st.session_state.input_key = 0
    if "success_msg" not in st.session_state:
        st.session_state.success_msg = False
    
    user_input = st.text_area("ここにスマホで雑に喋ってください：", height=120, key=f"input_{st.session_state.input_key}")

    if st.button("① データを安全に仕分けてスプレッドシートに保存"):
        if user_input:
            safe_text = re.sub(r'\d{5,}', '[電話番号削除済み]', user_input)
            
            prompt = f"以下の受付メモから、指定のJSON形式（来店時間、顧客名、担当営業、来店内容、ナンバー、車の色、車の特徴）で出力してください：\n{safe_text}"

            with st.spinner("AIが送信中..."):
                try:
                    # 無料枠でも世界中で一番安定して稼働しているモデルです
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=prompt,
                    )
                    
                    cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
                    parsed_data = json.loads(cleaned_json)
                    
                    sheet = connect_to_sheet()
                    row_to_add = [
                        parsed_data.get("来店時間", ""), parsed_data.get("顧客名", ""),
                        parsed_data.get("担当営業", ""), parsed_data.get("来店内容", ""),
                        parsed_data.get("ナンバー", ""), parsed_data.get("車の色", ""),
                        parsed_data.get("車の特徴", "")
                    ]
                    sheet.append_row(row_to_add)
                    st.session_state.input_key += 1
                    st.session_state.success_msg = True
                    st.rerun()
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

    if st.session_state.success_msg:
        st.success("☁️ 保存が成功しました！")
        st.session_state.success_msg = False

    st.write("---")
    st.subheader("📋 受付データ一覧")
    try:
        sheet = connect_to_sheet()
        st.dataframe(sheet.get_all_records(), use_container_width=True)
    except Exception as e:
        st.caption(f"読み込みエラー: {e}")

with tab2:
    st.subheader("🔎 クラウド検索")
    search_query = st.text_input("検索ワード：")
    if st.button("AIで検索する"):
        try:
            sheet = connect_to_sheet()
            current_db = sheet.get_all_records()
            if search_query and current_db:
                search_prompt = f"クエリ「{search_query}」に対して、以下のデータから探して箇条書きで答えて：\n{json.dumps(current_db, ensure_ascii=False)}"
                search_response = client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=search_prompt
                )
                st.info(search_response.text)
        except Exception as e:
            st.error(f"検索エラー: {e}")