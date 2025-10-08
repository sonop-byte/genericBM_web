# app.py — genericBM Web（1:1比較固定＋3ファイル対応）
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

    if before_files and after_files and st.button("比較を開始（1:1）", key="btn_two"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                def save_all(files, prefix):
                    paths = []
                    for f in files:
                        p = os.path.join(tmpdir, f"{prefix}_{f.name}")
                        save_uploaded_to(p, f)
                        paths.append(p)
                    return sorted(paths, key=lambda x: os.path.basename(x).lower())

                b_paths = save_all(before_files, "b")
                a_paths = save_all(after_files,  "a")

                total = min(len(b_paths), len(a_paths))
                if total == 0:
                    st.warning("比較対象がありません。"); st.stop()

                results = []
                prog = st.progress(0)
                status = st.empty()

                for i in range(total):
                    b = b_paths[i]
                    a = a_paths[i]
                    bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                    adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])
                    out_name = f"{bdisp}vs{adisp}.pdf"
                    out_tmp  = os.path.join(tmpdir, out_name)
                    status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                    generate_diff(b, a, out_tmp, dpi=dpi)
                    results.append((out_name, out_tmp))
                    prog.progress(int((i+1)/total*100))

                status.write("✅ 比較が完了しました。")
                prog.progress(100)

                st.subheader("📄 個別ダウンロード")
                for name, path in results:
                    with open(path, "rb") as f:
                        st.download_button(f"⬇️ {name}", f.read(), file_name=name, mime="application/pdf", key=f"dl_two_{name}")

                st.subheader("💾 ZIP一括ダウンロード")
                out_mem = io.BytesIO()
                with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, path in results:
                        zf.write(path, arcname=name)
                zip_name = f"genericBM_1to1_{datetime.now().strftime('%Y%m%d')}.zip"
                st.download_button("📥 ZIP一括ダウンロード", out_mem.getvalue(), file_name=zip_name, mime="application/zip")

            except Exception as e:
                st.error(f"エラー: {e}")
        st.stop()

# ---------------------------------------------------------------
# 📚 タブ2：3ファイル比較（Before1 vs AfterA・AfterB）
# ---------------------------------------------------------------
with tab_three:
    st.write("Before 1ファイル と After 2ファイルをアップロードしてください。")

    before_file = st.file_uploader("Before 側PDF（1つ）", type=["pdf"], key="before_three")
    after_files = st.file_uploader("After 側PDF（2つ）", type=["pdf"], accept_multiple_files=True, key="after_three")

    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                before_path = os.path.join(tmpdir, "before.pdf")
                save_uploaded_to(before_path, before_file)
                bdisp = safe_base(before_file.name)

                results = []
                prog = st.progress(0)
                status = st.empty()

                for i, a_file in enumerate(after_files, start=1):
                    a_path = os.path.join(tmpdir, f"after_{i}.pdf")
                    save_uploaded_to(a_path, a_file)
                    adisp = safe_base(a_file.name)

                    out_name = f"{bdisp}vs{adisp}.pdf"
                    out_tmp  = os.path.join(tmpdir, out_name)
                    status.write(f"🔄 生成中: {i}/2 — {bdisp} vs {adisp}")
                    generate_diff(before_path, a_path, out_tmp, dpi=dpi)
                    results.append((out_name, out_tmp))
                    prog.progress(int(i/2*100))

                status.write("✅ 比較が完了しました。")
                prog.progress(100)

                st.subheader("📄 個別ダウンロード")
                for name, path in results:
                    with open(path, "rb") as f:
                        st.download_button(f"⬇️ {name}", f.read(), file_name=name, mime="application/pdf", key=f"dl_three_{name}")

                st.subheader("💾 ZIP一括ダウンロード")
                out_mem = io.BytesIO()
                with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, path in results:
                        zf.write(path, arcname=name)
                zip_name = f"genericBM_1to2_{datetime.now().strftime('%Y%m%d')}.zip"
                st.download_button("📥 ZIP一括ダウンロード", out_mem.getvalue(), file_name=zip_name, mime="application/zip")

            except Exception as e:
                st.error(f"エラー: {e}")
        st.stop()
    elif after_files and len(after_files) != 2:
        st.info("After 側のPDFは2つアップロードしてください。")

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
