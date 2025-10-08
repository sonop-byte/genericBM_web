# app.py — Streamlit版 genericBM（中央ロゴ見出し・3機能統合・mmMIG表記）
import os
import io
import zipfile
import tempfile
from datetime import datetime

import streamlit as st
from PIL import Image
from pdf_diff_core_small import generate_diff

# ページ設定（アイコン画像を PIL 画像オブジェクトとして渡す）
ICON_PATH = "gBmicon.png"
# 確認用例外を出す if not found
if not os.path.exists(ICON_PATH):
    raise FileNotFoundError(f"Icon file not found: {ICON_PATH}")

icon_img = Image.open(ICON_PATH)

st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon=icon_img,
    layout="centered",
)

# ---- ヘッダー（ロゴ + タイトル + 説明）----
st.markdown(
    """
    <div style='text-align:center;'>
        <img src='https://raw.githubusercontent.com/sonop-byte/genericBM_web/main/gBmicon.png'
             width='120'
             style='display:block; margin-left:auto; margin-right:auto; margin-bottom:10px;'>
        <h1 style='font-size:2.4em; margin-bottom:6px; text-align:center;'>
            genericBM – PDF差分比較ツール（Web版）
        </h1>
        <p style='color:gray; font-size:1.05em; margin-top:0; text-align:center;'>
            修正前・修正後のPDF（またはフォルダZIP）をアップロードして差分を作成します。
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# --- サイドバー：比較モード選択 ---
st.sidebar.header("🧩 比較モード")
compare_mode = st.sidebar.selectbox(
    "比較モードを選択してください",
    ["single_pdf", "multiple_pdf", "zip_folder"],
    format_func=lambda x: {
        "single_pdf": "📄 単一PDF比較",
        "multiple_pdf": "📚 複数PDF 1:1 比較",
        "zip_folder": "🗂 フォルダZIP比較"
    }[x]
)

# （以降はこれまでのタブ／処理ロジックをそのまま続ける…）
# ---------- 共通設定 ----------
with st.expander("詳細設定", expanded=False):
    dpi = st.slider("出力PDFの解像度（dpi）", min_value=100, max_value=400, value=200, step=50)
    st.caption("数値が高いほど精細になりますが、生成時間と出力サイズが増えます。")

# ---------- ユーティリティ ----------
def safe_base(name: str) -> str:
    return os.path.splitext(os.path.basename(name))[0]

def collect_top_level_pdfs(root_dir: str):
    """直下のみのPDFをファイル名順で取得"""
    items = [f for f in os.listdir(root_dir) if os.path.isfile(os.path.join(root_dir, f))]
    pdfs = [os.path.join(root_dir, f) for f in items if f.lower().endswith(".pdf")]
    pdfs.sort(key=lambda p: os.path.basename(p).lower())
    return pdfs

def extract_zip_to_root(tmpdir: str, uploaded_zip, label: str):
    """ZIPを展開し、直下PDFがあればそのディレクトリ、なければ単一サブディレクトリ、さもなければ展開先を返す"""
    zip_tmp_path = os.path.join(tmpdir, f"{label}.zip")
    with open(zip_tmp_path, "wb") as f:
        f.write(uploaded_zip.read())
    extract_dir = os.path.join(tmpdir, f"{label}_unzipped")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_tmp_path, 'r') as zf:
        zf.extractall(extract_dir)
    top = [os.path.join(extract_dir, x) for x in os.listdir(extract_dir)]
    top_pdfs = [p for p in top if os.path.isfile(p) and p.lower().endswith(".pdf")]
    if top_pdfs:
        return extract_dir
    top_dirs = [d for d in top if os.path.isdir(d)]
    if len(top_dirs) == 1:
        return top_dirs[0]
    return extract_dir

# ---------- タブ ----------
tab_single, tab_folder, tab_multi = st.tabs([
    "📄 PDF 2枚比較",
    "🗂 フォルダ比較（ZIP）",
    "📚 複数PDF 1:1 比較",
])

# ====== 📚 複数PDF 1:1 比較機能 ======
if compare_mode == "multiple_pdf":

    before_files = st.file_uploader("Before側PDF（複数可）", type="pdf", accept_multiple_files=True)
    after_files  = st.file_uploader("After側PDF（複数可）", type="pdf", accept_multiple_files=True)

    if before_files and after_files and len(before_files) == len(after_files):

        if st.button("比較を開始"):
            results = []

            for b_file, a_file in zip(sorted(before_files, key=lambda f: f.name),
                                      sorted(after_files, key=lambda f: f.name)):

                diff_name = f"{b_file.name.replace('.pdf','')}-{a_file.name.replace('.pdf','')}_diff.pdf"
                out_path = os.path.join(tempfile.gettempdir(), diff_name)

                with st.spinner(f"🔍 {b_file.name} と {a_file.name} を比較中..."):
                    # 差分生成関数（既存のgenerate_diff）を呼ぶ
                    generate_diff(b_file, a_file, out_path)
                    results.append((diff_name, out_path))

            # ====== ✅ 結果出力セクション ======
            st.success(f"✅ 比較が完了しました（{len(results)}件）")

            # --- ZIPにまとめて出力 ---
            zip_path = os.path.join(tempfile.gettempdir(), "genericBM_results.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                for name, path in results:
                    zf.write(path, name)

            # --- 個別DLボタン ---
            st.subheader("📄 個別ダウンロード")
            for name, path in results:
                with open(path, "rb") as f:
                    st.download_button(
                        label=f"⬇️ {name}",
                        data=f,
                        file_name=name,
                        mime="application/pdf"
                    )

            # --- ZIP一括DLボタン ---
            st.subheader("💾 ZIP一括ダウンロード")
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="📥 すべてまとめてダウンロード（ZIP）",
                    data=f,
                    file_name="genericBM_results.zip",
                    mime="application/zip"
                )

            # ✅ 比較作業をここで止める（ループ防止）
            st.stop()

    elif before_files or after_files:
        st.warning("Before側とAfter側で同じ数のPDFをアップロードしてください。")

# ---------- フッター ----------
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
