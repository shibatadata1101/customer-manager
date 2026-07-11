import streamlit as st
import re
from google import genai
import json
import gspread
from google.oauth2.service_account import Credentials
from google.genai import types

# =========================================================
# ⚙️ 初期設定（Gemini ＆ Googleスプレッドシート）
# =========================================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11zXSrk1YqlsxqxFcMCbe_64Hso3KOoR5qqm4K69RGHo/edit?gid=0#gid=0"

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 💡 接続の無駄遣いを防ぐキャッシュ化（セグフォ・フリーズ対策）
@st.cache_resource
def get_cached_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(SPREADSHEET_URL)
    return sh.get_worksheet(0)

def load_sheet_data(sheet):
    try:
        return sheet.get_all_records()
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return []

# スプレッドシートへ接続
sheet = get_cached_sheet()

# 💡 起動時に1回だけデータをセッションに読み込んでおく（name error の防止）
if "raw_records" not in st.session_state:
    st.session_state.raw_records = load_sheet_data(sheet)

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
            
            prompt = f"""
            以下の「受付メモ」から、指定された7つの項目だけを正確に抜き出し、必ず指定された形式の【JSONフォーマットのみ】で出力してください。余計な挨拶や説明は一切不要です。

            【重要ルール】
            - 【来店時間】は、メモの中から「10時頃」「先ほど」「昼過ぎ」など、時間が分かる表現を抜き出してください。
            - 顧客名は、漢字（例：佐藤）が含まれている場合、必ず【カタカナの苗字だけ（例：サトウ）】に変換してください。
            - ナンバーは、1桁〜4桁の数字を抜き出してください。
            - 【車の色】（例：赤、青、シルバーなど）がわかる場合は、色だけを抜き出してください。
            - 【車の特徴】（例：インサイト、タント、軽自動車など）を抜き出してください。
            - **該当する情報がメモ内に書かれていない項目は、空欄やnullにせず、必ず `"NoData"` という文字列を入れてください。**

            【受付メモ】
            {safe_text}

            【出力フォーマット（JSON）】
            {{
                "来店時間": "...",
                "顧客名": "...",
                "担当営業": "...",
                "来店内容": "...",
                "ナンバー": "...",
                "車の色": "...",
                "車の特徴": "..."
            }}
            """

            with st.spinner("AIが送信中..."):
                try:
                    # 1. AIの処理
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        ),
                    )
                    
                    cleaned_json = response.candidates[0].content.parts[0].text
                    parsed_data = json.loads(cleaned_json)
                                       
                    row_to_add = [
                        parsed_data.get("来店時間", "NoData"), parsed_data.get("顧客名", "NoData"),
                        parsed_data.get("担当営業", "NoData"), parsed_data.get("来店内容", "NoData"),
                        parsed_data.get("ナンバー", "NoData"), parsed_data.get("車の色", "NoData"),
                        parsed_data.get("車の特徴", "NoData")
                    ]
                    
                    # 2. スプレッドシートへ書き込み
                    sheet.append_row(row_to_add)
                    
                    # 3. 最新のデータを裏で読み込んでおく
                    latest_records = load_sheet_data(sheet)
                    
                    # ==========================================
                    # 🔥 全て【終わってから】最後の1回だけ状態を更新！
                    # ==========================================
                    st.session_state.raw_records = latest_records  # 最新データに置き換え
                    st.session_state.input_key += 1               # 入力欄をクリアする指示
                    st.session_state.success_msg = True            # 成功メッセージを出す指示
                    
                    st.rerun()  # ここで満を持して1回だけ画面をリフレッシュ！

                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

    if st.session_state.success_msg:
        st.success("☁️ 保存が成功しました！")
        st.session_state.success_msg = False

    st.write("---")
    st.subheader("📋 受付データ一覧")
    
    try:
        # 💡 表示用のデータは、常に安全なセッション（st.session_state.raw_records）から読む
        cleaned_records = []
        for row in st.session_state.raw_records:
            cleaned_row = {str(k): str(v) for k, v in row.items()}
            cleaned_records = cleaned_records + [cleaned_row]

        # 警告を出さない新しい書き方（width="stretch"）に変えて画面に表示！
        if cleaned_records:
            st.dataframe(cleaned_records, width="stretch")
        else:
            st.caption("データがありません。")

    except Exception as e:
        st.caption(f"読み込みエラー: {e}")

with tab2:
    st.subheader("🔎 クラウド検索")
    search_query = st.text_input("検索ワード：")
    if st.button("AIで検索する"):
        try:
            # 💡 検索もシートを毎回再読込せず、手元の最新データから超高速で探すように修正（フリーズ対策）
            if search_query and st.session_state.raw_records:
                search_prompt = f"クエリ「{search_query}」に対して、以下のデータから探して箇条書きで答えて：\n{json.dumps(st.session_state.raw_records, ensure_ascii=False)}"
                search_response = client.models.generate_content(
                    model='gemini-3.1-flash-lite', 
                    contents=search_prompt
                )
                st.info(search_response.text)
        except Exception as e:
            st.error(f"検索エラー: {e}")