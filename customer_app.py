import streamlit as st
import re
# ⭕ 今日の最初に使っていた、1,500回使える古い方のライブラリに戻します！
import google.generativeai as genai
import json
import gspread
from google.oauth2.service_account import Credentials

# =========================================================
# ⚙️ 初期設定（Gemini ＆ Googleスプレッドシート）
# =========================================================
# 1. あなたのスプレッドシートのURL
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11zXSrk1YqlsxqxFcMCbe_64Hso3KOoR5qqm4K69RGHo/edit?gid=0#gid=0"

# 2. 【古い書き方】Geminiの初期化（1,500回使えるモード）
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# 3. Googleスプレッドシートへの接続関数
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

# ---------------------------------------------------------
# 【タブ1：受付メモ入力】
# ---------------------------------------------------------
with tab1:
    st.info("🔒 **安心セキュリティ**: 4桁以上の数字（電話番号）は手元で自動消去されます。")
    
    if "input_key" not in st.session_state:
        st.session_state.input_key = 0
    if "success_msg" not in st.session_state:
        st.session_state.success_msg = False
    
    user_input = st.text_area(
        "ここにスマホで雑に喋ってください：",
        placeholder="（例）10時頃に青いタントで来た佐藤さん、ナンバー55。車検の見積もり。担当は鈴木。",
        height=120,
        key=f"user_input_area_{st.session_state.input_key}"
    )

    if st.button("① データを安全に仕分けてスプレッドシートに保存"):
        if user_input:
            st.write("---")
            safe_text = re.sub(r'\d{5,}', '[電話番号削除済み]', user_input)
            
            prompt = f"""
            以下の「受付メモ」から、指定された7つの項目だけを正確に抜き出し、必ず指定された形式の【JSONフォーマットのみ】で出力してください。余計な挨拶や説明は一切不要です。

            【重要ルール】
            - 【来店時間】は、メモの中から「10時頃」「先ほど」「昼過ぎ」など、時間が分かる表現を抜き出してください。
            - 顧客名は、漢字（例：佐藤）が含まれている場合、必ず【カタカナの苗字だけ（例：サトウ）】に変換してください。
            - ナンバーは、1桁〜4桁の数字を抜き出してください。
            - 【車の色】（例：赤、青、シルバーなど）がわかる場合は、色だけを抜き出してください。
            - 【車の特徴】（例：インサイト、タント、軽自動車など）を抜き出してください。

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

            with st.spinner("AIが仕分け＆スプレッドシートへ送信中..."):
                try:
                    # 💡 【古い書き方】1,500回使える gemini-1.5-flash を呼び出します！
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt)
                    
                    cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
                    parsed_data = json.loads(cleaned_json)
                    
                    sheet = connect_to_sheet()
                    row_to_add = [
                        parsed_data.get("来店時間", ""),
                        parsed_data.get("顧客名", ""),
                        parsed_data.get("担当営業", ""),
                        parsed_data.get("来店内容", ""),
                        parsed_data.get("ナンバー", ""),
                        parsed_data.get("車の色", ""),
                        parsed_data.get("車の特徴", "")
                    ]
                    sheet.append_row(row_to_add)
                    
                    st.session_state.input_key += 1
                    st.session_state.success_msg = True
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
        else:
            st.warning("テキストを入力してください。")

    if st.session_state.success_msg:
        st.success("☁️ Googleスプレッドシートへのリアルタイム保存が成功しました！")
        st.balloons()
        st.session_state.success_msg = False

    st.write("---")
    st.subheader("📋 スプレッドシート上の受付データ一覧")
    try:
        sheet = connect_to_sheet()
        all_records = sheet.get_all_records() 
        if all_records:
            st.dataframe(all_records, use_container_width=True)
        else:
            st.caption("スプレッドシートにデータがまだありません。")
    except Exception as e:
        st.caption(f"スプレッドシートのデータを読み込めませんでした: {e}")

# ---------------------------------------------------------
# 【タブ2：営業用・爆速検索】
# ---------------------------------------------------------
with tab2:
    st.subheader("🔎 「あの車だれ？」をスプレッドシートから爆速検索")
    
    if "search_key" not in st.session_state:
        st.session_state.search_key = 0
        
    search_query = st.text_input(
        "検索ワードを喋るか入力してください：", 
        placeholder="（例）10時頃に来た青い軽自動車",
        key=f"search_input_field_{st.session_state.search_key}"
    )
    
    if "last_search_result" not in st.session_state:
        st.session_state.last_search_result = ""
    
    if st.button("AIで検索する"):
        try:
            sheet = connect_to_sheet()
            current_db = sheet.get_all_records()
            
            if not current_db:
                st.warning("スプレッドシートにデータが1件もありません。")
            elif search_query:
                search_prompt = f"""
                あなたは優秀な店舗受付アシスタントです。
                営業さんから「{search_query}」という雑な質問（検索クエリ）が来ました。
                以下の【クラウド受付リスト】の中から、該当する可能性が最も高い顧客のデータを特定し、営業さんに優しく教えてあげてください。

                【クラウド受付リスト】
                {json.dumps(current_db, ensure_ascii=False, indent=2)}

                【回答のルール】
                - 該当する人が見つかった場合、その人の「顧客名」「担当営業」「来店内容」「車の特徴」を分かりやすく箇条書きで教えてください。
                - もし似たような車が複数ある場合は、「こちらの2件が該当しそうです」と候補を挙げてください。
                - 全く該当するデータがない場合は、「申し訳ありません、その特徴に合うお車は現在のリストに見当たりませんでした」と答えてください。
                """
                
                with st.spinner("AIがクラウドデータと照合中..."):
                    # 💡 検索も 1.5-flash で回数無制限（1,500回）
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    search_response = model.generate_content(search_prompt)
                    
                    st.session_state.last_search_result = search_response.text
                    st.session_state.search_key += 1
                    st.rerun()
            else:
                st.warning("検索ワードを入力してください。")
        except Exception as e:
            st.error(f"検索エラーが発生しました: {e}")

    if st.session_state.last_search_result:
        st.write("---")
        st.subheader("💡 AIからの回答")
        st.info(st.session_state.last_search_result)
        
        if st.button("検索結果を閉じる"):
            st.session_state.last_search_result = ""
            st.rerun()