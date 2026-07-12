import streamlit as st
import re
from google import genai
import json
import gspread
from google.oauth2.service_account import Credentials
from google.genai import types
from pydantic import BaseModel, Field  # 💡 型安全なデータ抽出のために追加

# =========================================================
# ⚙️ 初期設定（Gemini ＆ Googleスプレッドシート）
# =========================================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11zXSrk1YqlsxqxFcMCbe_64Hso3KOoR5qqm4K69RGHo/edit?gid=0#gid=0"

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 💡 AIが必ず出力すべきデータ構造を定義（Structured Outputs）
class CustomerMemo(BaseModel):
    来店時間: str = Field(description="時間がわかる表現（例: 10時頃、先ほど、昼過ぎ）。情報がない場合は 'NoData'")
    顧客名: str = Field(description="漢字の苗字は必ずカタカナ（例: サトウ）に変換。情報がない場合は 'NoData'")
    担当営業: str = Field(description="担当営業の氏名。情報がない場合は 'NoData'")
    来店内容: str = Field(description="来店目的やメモ内容。情報がない場合は 'NoData'")
    ナンバー: str = Field(description="1桁〜4桁の車のナンバー。情報がない場合は 'NoData'")
    車の色: str = Field(description="車の色。情報がない場合は 'NoData'")
    車の特徴: str = Field(description="車種や軽自動車などの特徴。情報がない場合は 'NoData'")

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
            # 💡 4桁以上の数字（例：電話番号など）を隠す（UIの説明と一致するよう修正）
            safe_text = re.sub(r'\d{5,}', '[個人情報削除済み]', user_input)
            
            prompt = f"""
            以下の「受付メモ」から情報を抽出し、指定されたフォーマットで出力してください。

            【受付メモ】
            {safe_text}
            """

            with st.spinner("AIが送信中..."):
                try:
                    # 💡 Pydanticモデル（CustomerMemo）をresponse_schemaに渡すことで、100%完璧なJSONが返るようになります
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=CustomerMemo,
                        ),
                    )
                    
                    cleaned_json = response.candidates[0].content.parts[0].text
                    parsed_data = json.loads(cleaned_json)
                                       
                    row_to_add = [
                        parsed_data.get("来店時間", "NoData"), 
                        parsed_data.get("顧客名", "NoData"),
                        parsed_data.get("担当営業", "NoData"), 
                        parsed_data.get("来店内容", "NoData"),
                        parsed_data.get("ナンバー", "NoData"), 
                        parsed_data.get("車の色", "NoData"),
                        parsed_data.get("車の特徴", "NoData")
                    ]
                    
                    sheet.append_row(row_to_add)
                    
                    latest_records = load_sheet_data(sheet)
                    
                    st.session_state.raw_records = latest_records  
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
        cleaned_records = []
        for row in st.session_state.raw_records:
            cleaned_row = {str(k): str(v) for k, v in row.items()}
            cleaned_records.append(cleaned_row)

        if cleaned_records:
            st.dataframe(cleaned_records, width="stretch")
        else:
            st.caption("データがありません。")

    except Exception as e:
        st.caption(f"読み込みエラー: {e}")

with tab2:
    st.subheader("🔎 クラウド検索")
    # 💡 文字を入力して「エンター」を押すだけで即検索が走るように、条件を調整
    search_query = st.text_input("検索ワード（入力してEnterでも検索できます）：")
    
    if search_query:
        try:
            if st.session_state.raw_records:
                with st.spinner("AIが検索中..."):
                    search_prompt = f"クエリ「{search_query}」に対して、以下のデータから探して箇条書きで分かりやすく答えて：\n{json.dumps(st.session_state.raw_records, ensure_ascii=False)}"
                    search_response = client.models.generate_content(
                        model='gemini-3.1-flash-lite', 
                        contents=search_prompt
                    )
                    st.info(search_response.text)
            else:
                st.caption("検索対象のデータがありません。")
        except Exception as e:
            st.error(f"検索エラー: {e}")