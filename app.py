# app.py — genericBM Web（ファイル保持＋プレビュー＋日付追加）
import os
import io
import zipfile
import tempfile
from datetime import datetime
import unicodedata
import streamlit as st
from PIL import Image
from pdf_diff_core_small import generate_diff

# ===== ページ設定 =====
ICON_PATH = "gBmicon.png"
icon_img = None
if os.path.exists(ICON_PATH):
    try:
        icon_img = Image.open(ICON_PATH)
    except Exception:
        icon_img = None

st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon=icon_img if icon_img else "🩺",
    layout="centered",
)

# ===== ヘッダー =====
st.markdown(
    """
    <div style='text-align:center;'>
        <img src='https://raw.githubusercontent.com/sonop-byte/genericBM_web/main/gBmicon.png'
             width='120'
             style='display:block; margin:auto; margin-bottom:10px;'>
        <h1 style='font-size:2.2em; margin-bottom:6px;'>genericBM – PDF差分比較ツール（Web版）</h1>
        <p style='color:gray; font-size:1.0em;'>修正前・修正後のPDFをアップロードして差分を作成します。</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ===== 共通設定 =====
with st.expander("詳細設定", expanded=False):
    dpi = st.slider("出力PDFの解像度（dpi）", 100, 400, 200, 50)
    st.caption("数値が高いほど精細になりますが、生成時間と出力サイズが増えます。")

def safe_base(path_or_name: str) -> str:
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return unicodedata.normalize("NFC", name)

def save_uploaded_to(path: str, uploaded):
    with open(path, "wb") as f:
        f.write(uploaded.read())

def add_date_suffix(filename: str) -> str:
    """ファイル名の末尾に_YYYYMMDDを追加"""
    base, ext = os.path.splitext(filename)
    date_tag = datetime.now().strftime("%Y%m%d")
    return f"{base}_{date_tag}{ext}"

# ===== セッション初期化 =====
for k in ["results_two", "results_three", "preview_file"]:
    if k not in st.session_state:
        st.session_state[k] = []

# ✅ 比較実行フラグを追加
if "run_two" not in st.session_state:
    st.session_state.run_two = False
if "run_three" not in st.session_state:
    st.session_state.run_three = False

# ===== タブ構成 =====
tab_two, tab_three = st.tabs(["📄 2ファイル比較（1:1固定）", "📚 3ファイル比較（1対2）"])

# ---------------------------------------------------------------
# 📄 タブ1：2ファイル比較（ファイル名順で1:1固定）
# ---------------------------------------------------------------
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        before_files = st.file_uploader("Before 側PDF（複数可）", type=["pdf"], accept_multiple_files=True, key="before_two")
    with c2:
        after_files  = st.file_uploader("After 側PDF（複数可）",  type=["pdf"], accept_multiple_files=True, key="after_two")

 # ボタンでフラグON
if before_files and after_files and st.button("比較を開始（1:1）", key="btn_two"):
    st.session_state.run_two = True

# フラグがONのときだけ処理 → 処理後にOFF
if st.session_state.run_two:
    st.session_state.results_two.clear()
    with tempfile.TemporaryDirectory() as tmpdir:
        ...
    st.session_state.run_two = False   # <- ここがポイント

        st.subheader("📄 生成済み差分PDF")
        for name, data in st.session_state.results_two:
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👁 {name}", key=f"preview_two_{name}"):
                    st.session_state.preview_file = (name, data)
            with c2:
                st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=f"dl_two_{name}")

        # ZIP一括DL
        st.subheader("💾 ZIP一括ダウンロード")
        out_mem = io.BytesIO()
        with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state.results_two:
                zf.writestr(name, data)
        zip_name = f"genericBM_1to1_{datetime.now().strftime('%Y%m%d')}.zip"
        st.download_button("📥 ZIP一括DL", out_mem.getvalue(), file_name=zip_name, mime="application/zip")

# ---------------------------------------------------------------
# 📚 タブ2：3ファイル比較（Before1 vs AfterA・AfterB）
# ---------------------------------------------------------------
with tab_three:
    before_file = st.file_uploader("Before 側PDF（1つ）", type=["pdf"], key="before_three")
    after_files = st.file_uploader("After 側PDF（2つ）", type=["pdf"], accept_multiple_files=True, key="after_three")

    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        st.session_state.results_three.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                before_path = os.path.join(tmpdir, "before.pdf")
                save_uploaded_to(before_path, before_file)
                bdisp = safe_base(before_file.name)

                prog = st.progress(0)
                status = st.empty()

                for i, a_file in enumerate(after_files, start=1):
                    a_path = os.path.join(tmpdir, f"after_{i}.pdf")
                    save_uploaded_to(a_path, a_file)
                    adisp = safe_base(a_file.name)
                    out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                    out_tmp  = os.path.join(tmpdir, out_name)
                    status.write(f"🔄 生成中: {i}/2 — {bdisp} vs {adisp}")
                    generate_diff(before_path, a_path, out_tmp, dpi=dpi)
                    with open(out_tmp, "rb") as f:
                        data = f.read()
                    st.session_state.results_three.append((out_name, data))
                    prog.progress(int(i/2*100))

                status.write("✅ 比較が完了しました。")
                prog.progress(100)

            except Exception as e:
                st.error(f"エラー: {e}")
        st.stop()

    # 生成済みPDF一覧（保持）
    if st.session_state.results_three:
        st.subheader("📄 生成済み差分PDF")
        for name, data in st.session_state.results_three:
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👁 {name}", key=f"preview_three_{name}"):
                    st.session_state.preview_file = (name, data)
            with c2:
                st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=f"dl_three_{name}")

        # ZIP一括DL
        st.subheader("💾 ZIP一括ダウンロード")
        out_mem = io.BytesIO()
        with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state.results_three:
                zf.writestr(name, data)
        zip_name = f"genericBM_1to2_{datetime.now().strftime('%Y%m%d')}.zip"
        st.download_button("📥 ZIP一括DL", out_mem.getvalue(), file_name=zip_name, mime="application/zip")

# ---------------------------------------------------------------
# 👁 プレビュー表示
# ---------------------------------------------------------------
if st.session_state.preview_file:
    name, data = st.session_state.preview_file
    st.markdown("---")
    st.subheader(f"👁 プレビュー表示：{name}")
    st.download_button("⬇️ このファイルをダウンロード", data=data, file_name=name, mime="application/pdf", key="preview_dl")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{data.decode("latin1")}" width="100%" height="600px"></iframe>',
        unsafe_allow_html=True,
    )

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
