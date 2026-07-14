import streamlit as st
import re
from google import genai
import json
import gspread
from google.oauth2.service_account import Credentials
from google.genai import types
import os
import unicodedata

# =========================================================
# ⚙️ 初期設定（Gemini ＆ Googleスプレッドシート ＆ 苗字データ）
# =========================================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11zXSrk1YqlsxqxFcMCbe_64Hso3KOoR5qqm4K69RGHo/edit?gid=0#gid=0"
NAMES_FILE = "names.txt"

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 💡 文字の表記ゆれ（半角・全角、大文字・小文字）を吸収する正規化関数
def normalize_text(text):
    if not text:
        return ""
    # 全角英数字・カタカナを半角/標準に変換し、小文字に統一
    return unicodedata.normalize('NFKC', str(text)).lower()

# 💡 苗字データ（CSV）のキャッシュ読み込み関数
@st.cache_data
def load_common_names(file_path=NAMES_FILE):
    if os.path.exists(file_path):
        names = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "," not in line:
                    continue
                parts = line.split(",")
                kanji_name = parts[0].strip()
                if kanji_name:
                    names.append(kanji_name)
        return sorted(names, key=len, reverse=True)
    else:
        default_names = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤"]
        return sorted(default_names, key=len, reverse=True)

COMMON_NAMES = load_common_names(NAMES_FILE)

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

sheet = get_cached_sheet()

if "raw_records" not in st.session_state:
    st.session_state.raw_records = load_sheet_data(sheet)

# 💡 確認画面の状態を管理するためのセッション初期化
if "confirm_mode" not in st.session_state:
    st.session_state.confirm_mode = False
if "safe_text" not in st.session_state:
    st.session_state.safe_text = ""

# =========================================================
# 🔒 マスキングロジックの定義
# =========================================================
def mask_sensitive_data(text, names_list):
    if not text:
        return "", {}
    
    masked_text = text
    replacements = {}
    
    # 1. 5桁以上の数字を削除
    masked_text = re.sub(r'\d{5,}', '', masked_text)
    
    # 2. 苗字の置換（先に置換して保護）
    name_count = 1
    honorifics = ["さん", "様", "君", "くん", "営業", "氏"]
    for name in names_list:
        for hon in honorifics:
            target = f"{name}{hon}"
            if target in masked_text:
                placeholder = f"[NAME_{name_count}]"
                replacements[placeholder] = name
                masked_text = masked_text.replace(target, f"{placeholder}{hon}")
                name_count += 1
                break
    
    # 3. 車のナンバー置換（時間 12:00 を避ける）
    i = 0
    num_count = 1
    while i < len(masked_text):
        if masked_text[i] == '[':
            close_idx = masked_text.find(']', i)
            if close_idx != -1:
                i = close_idx + 1
                continue
        
        if masked_text[i:i+1].isdigit():
            j = i
            while j < len(masked_text) and masked_text[j].isdigit():
                j += 1
            num_str = masked_text[i:j]
            
            # 1〜4桁 かつ コロンに隣接していない場合のみ
            if 1 <= len(num_str) <= 4:
                is_time = (i > 0 and masked_text[i-1] == ':') or (j < len(masked_text) and masked_text[j] == ':')
                
                if not is_time:
                    placeholder = f"[NUMBER_{num_count}]"
                    replacements[placeholder] = num_str
                    masked_text = masked_text[:i] + placeholder + masked_text[j:]
                    i += len(placeholder)
                    num_count += 1
                    continue
            i = j
        else:
            i += 1
                
    return masked_text, replacements
    if not text:
        return "", {}
    
    masked_text = text
    replacements = {}
    
    # 1. 5桁以上の数字を削除
    masked_text = re.sub(r'\d{5,}', '', masked_text)
    
    # 2. 苗字の置換（先に置換して保護する）
    name_count = 1
    honorifics = ["さん", "様", "君", "くん", "営業", "氏"]
    for name in names_list:
        for hon in honorifics:
            target = f"{name}{hon}"
            if target in masked_text:
                placeholder = f"[NAME_{name_count}]"
                replacements[placeholder] = name
                masked_text = masked_text.replace(target, f"{placeholder}{hon}")
                name_count += 1
                break
    
    # 3. 車のナンバー置換（時間表記 12:00 を避けるロジック）
    # 文章を1文字ずつ見て、数字のかたまりを探す
    i = 0
    num_count = 1
    while i < len(masked_text):
        # プレースホルダーの中身はスキップ
        if masked_text[i] == '[':
            close_idx = masked_text.find(']', i)
            if close_idx != -1:
                i = close_idx + 1
                continue
        
        # 数字を見つけたら
        if masked_text[i:i+1].isdigit():
            # 数字のかたまりを取得
            j = i
            while j < len(masked_text) and masked_text[j].isdigit():
                j += 1
            num_str = masked_text[i:j]
            
            # 1〜4桁かつ、コロンに隣接していない場合のみナンバーとみなす
            if 1 <= len(num_str) <= 4:
                is_time = False
                # 直前または直後にコロンがあれば時間とみなしてスキップ
                if (i > 0 and masked_text[i-1] == ':') or (j < len(masked_text) and masked_text[j] == ':'):
                    is_time = True
                
                if not is_time:
                    placeholder = f"[NUMBER_{num_count}]"
                    replacements[placeholder] = num_str
                    masked_text = masked_text[:i] + placeholder + masked_text[j:]
                    i += len(placeholder)
                    num_count += 1
                    continue
            i = j
        else:
            i += 1
                
    return masked_text, replacements

# =========================================================
# 📱 画面の構築 (Streamlit UI)
# =========================================================
st.set_page_config(page_title="爆速・顧客受付＆検索システム", page_icon="📱")
st.title("📱 爆速・顧客受付＆検索システム")

with st.sidebar:
    st.header("🔒 セキュリティ管理")
    st.success(f"読み込み済みの苗字数: {len(COMMON_NAMES)} 件")
    if not os.path.exists(NAMES_FILE):
        st.warning("※ names.txt が見つからないため、デフォルトの主要苗字を使用中")

tab1, tab2 = st.tabs(["📝 受付メモ入力", "🔍 営業用・爆速検索"])

with tab1:
    st.info("🔒 **安心セキュリティ**: 個人情報は自動でマスクされ、確認してから送信できます。")
    
    if "input_key" not in st.session_state:
        st.session_state.input_key = 0
    if "success_msg" not in st.session_state:
        st.session_state.success_msg = False
    
    # 1. 通常入力モード
    if not st.session_state.confirm_mode:
        user_input = st.text_area("ここにスマホで雑に喋ってください：", height=120, key=f"input_{st.session_state.input_key}")

        # 💡 【バグ修正①】「確認画面へ進む」ボタンをifのブロック内に正しく配置
        if st.button("確認画面へ進む"):
            # 関数を呼び出して「マスク後の文章」と「新しい対応表」を受け取る
            safe_text, current_replacements = mask_sensitive_data(user_input, COMMON_NAMES)
            
            # セッション状態にそれぞれ保存する
            st.session_state.safe_text = safe_text
            st.session_state.replacements = current_replacements
            
            st.session_state.confirm_mode = True
            st.rerun()
                
    # 2. マスキング後の確認モード
    else:
        st.subheader("👀 マスキング結果の確認")
        st.caption("以下の内容（個人情報が隠された状態）でAIに送信し、スプレッドシートに保存します。")
        
        # マスキングされたテキストを分かりやすく枠内に表示
        st.info(st.session_state.safe_text)
        
        # 横並びのボタン
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🚀 問題ないのでAIに送信して保存", type="primary"):
                with st.spinner("AIが送信中..."):
                    try:
                        prompt = f"""
                        以下の「受付メモ」から、指定された7つの項目だけを正確に抜き出し、必ず指定された形式の【JSONフォーマットのみ】で出力してください。余計な挨拶や説明は一切不要です。

                        【重要ルール】
                        - 【来店時間】は、メモの中から「10時頃」「先ほど」「昼過ぎ」など、時間が分かる表現を抜き出してください。
                        -  顧客名は、すでに [NAME_X] (例: [NAME_1]) にマスクされている場合は、その文字列（例: "[NAME_1]"）をそのまま正確に抽出してください。情報が完全にない場合や不明な場合は "NoData" にしてください。余計な変換は一切不要です。
                        - 【ナンバー】は、メモ内に [NUMBER_X] というマスクがある場合は、ナンバーの記載があったと判断し、そのまま `"[NUMBER_X]"` という文字列を抽出してください。完全に情報がない場合は `"NoData"` にしてください。
                        - 【車の色】（例：赤、青、シルバーなど）がわかる場合は、色だけを抜き出してください。
                        - 【車の特徴】（例：インサイト、タント、軽自動車など）を抜き出してください。
                        - **該当する情報がメモ内に書かれていない項目は、空欄やnullにせず、必ず `"NoData"` という文字列を入れてください。**

                        【受付メモ】
                        {st.session_state.safe_text}

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

                        # AIの処理
                        response = client.models.generate_content(
                            model='gemini-3.1-flash-lite',
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                            ),
                        )
                        
                        # AIの回答を受け取った後
                        cleaned_json = response.candidates[0].content.parts[0].text
                        parsed_data = json.loads(cleaned_json)

                        # 裏に残しておいた連番の対応表を取得
                        replacements = st.session_state.get("replacements", {})

                        for key in parsed_data:
                            val = str(parsed_data[key])
                            # 完全一致で復元！
                            # [NUMBER_1] や [NAME_1] があれば元の値に書き換える
                            if val in replacements:
                                parsed_data[key] = replacements[val]
                            # 💡 重要：もしAIが「14:00」をそのまま返しているなら、
                            # それは書き換えられずにそのままスプレッドシートに保存されます（これでOK）
                                           
                        row_to_add = [
                            parsed_data.get("来店時間", "NoData"), parsed_data.get("顧客名", "NoData"),
                            parsed_data.get("担当営業", "NoData"), parsed_data.get("来店内容", "NoData"),
                            parsed_data.get("ナンバー", "NoData"), parsed_data.get("車の色", "NoData"),
                            parsed_data.get("車の特徴", "NoData")
                        ]
                        
                        # スプレッドシートへ書き込み
                        sheet.append_row(row_to_add)
                        
                        # 最新データ取得
                        latest_records = load_sheet_data(sheet)
                        
                        # セッション状態をリセットして通常画面に戻す
                        st.session_state.raw_records = latest_records  
                        st.session_state.input_key += 1               
                        st.session_state.success_msg = True            
                        st.session_state.confirm_mode = False  # 確認モード終了
                        st.session_state.safe_text = ""        # 一時テキスト消去
                        
                        st.rerun()  

                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
                        
        with col2:
            if st.button("❌ やり直す（入力を修正する）"):
                # 保存せずに確認モードをオフにする（入力内容は残ります）
                st.session_state.confirm_mode = False
                st.session_state.safe_text = ""
                st.rerun()

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
            with st.expander(f"📋 過去の受付データを見る（全 {len(cleaned_records)} 件）"):
                headers = list(cleaned_records[0].keys())
                markdown_table = "| " + " | ".join(headers) + " |\n"
                markdown_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                
                for row in cleaned_records:
                    safe_values = [str(val).replace("|", " ") for val in row.values()]
                    markdown_table += "| " + " | ".join(safe_values) + " |\n"
                    
                st.markdown(markdown_table)
        else:
            st.caption("データがありません。")

    except Exception as e:
        st.caption(f"読み込みエラー: {e}")
    
    st.write("---")
    st.subheader("⚠️ データの管理")

    clear_confirm = st.checkbox("本当にスプレッドシートのデータをすべて削除しますか？（元に戻せません）")

    if clear_confirm:
        st.info("🔓 安全装置が解除されました。ボタンを押すと一括削除が実行されます。")
        if st.button("🚨 受付データをすべてクリアする", type="primary"):
            with st.spinner("スプレッドシートをクリア中..."):
                try:
                    # 💡 【バグ修正②】データをクリアした上でヘッダーをきれいに再生成する
                    sheet.resize(rows=1) 
                    headers = ["来店時間", "顧客名", "担当営業", "来店内容", "ナンバー", "車の色", "車の特徴"]
                    sheet.update(range_name="A1:G1", values=[headers])
                    sheet.resize(rows=100) 
                    
                    st.session_state.raw_records = []
                    st.success("💥 すべてのデータをクリアしました！")
                    st.rerun() 
                except Exception as clear_e:
                    st.error(f"クリア処理中にエラーが発生しました: {clear_e}")
    else:
        st.button("🚨 受付データをすべてクリアする", disabled=True, type="primary")

with tab2:
    st.subheader("🔎 安全なローカル検索")
    
    # 💡 検索窓を自動クリアするための背番号（キー）を準備
    if "search_key" not in st.session_state:
        st.session_state.search_key = 0
        
    # 💡 現在の検索ワードを一時保存する場所を準備
    if "current_query" not in st.session_state:
        st.session_state.current_query = ""

    # 💡 keyを指定することで、背番号を増やした瞬間に検索窓を強制空欄にリセット
    search_query = st.text_input(
        "検索ワード（入力してEnterで検索）：", 
        key=f"search_{st.session_state.search_key}",
        placeholder="顧客名、ナンバー、車の特徴など..."
    )
    
    # ユーザーが文字を入力してエンターを押した瞬間
    if search_query:
        st.session_state.current_query = search_query
        st.session_state.search_key += 1
        st.rerun()

    # 💡 退避させておいたワードを使って、ローカル（手元）だけで高速検索
    if st.session_state.current_query:
        st.write(f"🔍 検索中: **{st.session_state.current_query}**")
        
        # 検索キーワードを正規化
        normalized_query = normalize_text(st.session_state.current_query)
        
        if st.session_state.raw_records:
            # 💡 【高速・安全】全データをループし、いずれかの列にキーワードが含まれる行を抽出
            hit_records = []
            for row in st.session_state.raw_records:
                # 行内のすべての値を結合して一つのテキストにし、正規化して検索
                row_combined_text = " ".join([str(val) for val in row.values()])
                normalized_row_text = normalize_text(row_combined_text)
                
                if normalized_query in normalized_row_text:
                    # スプレッドシートのキー（ヘッダー）と値をきれいな辞書形式にして保存
                    clean_row = {str(k): str(v) for k, v in row.items()}
                    hit_records.append(clean_row)

            # 💡 検索結果の表示
            if hit_records:
                st.success(f"🎉 {len(hit_records)} 件のデータが見つかりました。")
                
                # 検索結果をマークダウンのテーブルで綺麗に表示
                headers = list(hit_records[0].keys())
                markdown_table = "| " + " | ".join(headers) + " |\n"
                markdown_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                
                for row in hit_records:
                    safe_values = [str(val).replace("|", " ") for val in row.values()]
                    markdown_table += "| " + " | ".join(safe_values) + " |\n"
                    
                st.markdown(markdown_table)
            else:
                st.warning(" 該当するデータが見つかりませんでした。")
        else:
            st.caption("検索対象のデータがありません。")
            
        # 検索をリセットするボタン
        if st.button("検索をクリア"):
            st.session_state.current_query = ""
            st.rerun()