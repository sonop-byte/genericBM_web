# app.py — genericBM Web（2ファイル比較タブ＋3ファイル比較タブ）
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
    page_icon=icon_img if icon_img is not None else "🩺",
    layout="centered",
)

# ===== ヘッダー =====
st.markdown(
    """
    <div style='text-align:center;'>
        <img src='https://raw.githubusercontent.com/sonop-byte/genericBM_web/main/gBmicon.png'
             width='120'
             style='display:block; margin-left:auto; margin-right:auto; margin-bottom:10px;'>
        <h1 style='font-size:2.2em; margin-bottom:6px; text-align:center;'>
            genericBM – PDF差分比較ツール（Web版）
        </h1>
        <p style='color:gray; font-size:1.0em; margin-top:0; text-align:center;'>
            修正前・修正後のPDFをアップロードして差分を作成します。
        </p>
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
tab_two, tab_three = st.tabs(["📄 2ファイル比較", "📚 3ファイル同時比較"])

# ---------------------------------------------------------------
# 📄 タブ1：2ファイル比較（単一でも複数でもOK）
# ---------------------------------------------------------------
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        before_files = st.file_uploader("Before 側PDF（1つまたは複数）", type=["pdf"], accept_multiple_files=True, key="before_two")
    with c2:
        after_files  = st.file_uploader("After 側PDF（1つまたは複数）",  type=["pdf"], accept_multiple_files=True, key="after_two")

    if before_files and after_files and st.button("比較を開始（2ファイル比較）", key="btn_two"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                def save_all(files, prefix):
                    paths = []
                    for f in files:
                        p = os.path.join(tmpdir, f"{prefix}_{f.name}")
                        save_uploaded_to(p, f)
                        paths.append(p)
                    paths.sort(key=lambda x: os.path.basename(x).lower())
                    return paths

                b_paths = save_all(before_files, "b")
                a_paths = save_all(after_files,  "a")

                pairs = []
                if len(b_paths) == 1 and len(a_paths) == 1:
                    pairs = [(b_paths[0], a_paths[0])]
                elif len(b_paths) == 1 and len(a_paths) > 1:
                    for a in a_paths:
                        pairs.append((b_paths[0], a))
                elif len(b_paths) > 1 and len(a_paths) == 1:
                    for b in b_paths:
                        pairs.append((b, a_paths[0]))
                else:
                    total = min(len(b_paths), len(a_paths))
                    pairs = list(zip(b_paths[:total], a_paths[:total]))

                if not pairs:
                    st.error("比較できるペアがありません。"); st.stop()

                results = []
                prog = st.progress(0)
                status = st.empty()

                for i, (b, a) in enumerate(pairs, start=1):
                    bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                    adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])
                    out_name = f"{bdisp}vs{adisp}.pdf"
                    out_tmp  = os.path.join(tmpdir, out_name)
                    status.write(f"🔄 生成中: {i}/{len(pairs)} — {bdisp} vs {adisp}")
                    generate_diff(b, a, out_tmp, dpi=dpi)
                    results.append((out_name, out_tmp))
                    prog.progress(int(i / len(pairs) * 100))

                status.write("✅ すべての比較が完了しました。")
                prog.progress(100)

                st.subheader("📄 個別ダウンロード")
                for name, path in results:
                    with open(path, "rb") as f:
                        st.download_button(
                            label=f"⬇️ {name}",
                            data=f.read(),
                            file_name=name,
                            mime="application/pdf",
                            key=f"dl_two_{name}"
                        )

                st.subheader("💾 ZIP一括ダウンロード")
                out_mem = io.BytesIO()
                with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, path in results:
                        zf.write(path, arcname=name)
                zip_name = f"genericBM_two_{datetime.now().strftime('%Y%m%d')}.zip"
                st.download_button(
                    "📥 まとめてダウンロード（ZIP）",
                    data=out_mem.getvalue(),
                    file_name=zip_name,
                    mime="application/zip",
                    key="dl_two_zip"
                )
            except Exception as e:
                st.error(f"エラー: {e}")
        st.stop()

# ---------------------------------------------------------------
# 📚 タブ2：3ファイル同時比較
# ---------------------------------------------------------------
with tab_three:
    three_files = st.file_uploader("PDFを2〜3個選択してください（最大3）", type=["pdf"], accept_multiple_files=True, key="three_tab")

    if three_files and 2 <= len(three_files) <= 3:
        names = [f.name for f in three_files]
        base_choice = st.selectbox("基準ファイルを選択", names, index=0)

        if st.button("比較を開始（3ファイル）", key="btn_three_tab"):
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    tmp_map = {}
                    for f in three_files:
                        p = os.path.join(tmpdir, f.name)
                        save_uploaded_to(p, f)
                        tmp_map[f.name] = p

                    base_path = tmp_map[base_choice]
                    targets = [n for n in names if n != base_choice]

                    results = []
                    prog = st.progress(0)
                    status = st.empty()

                    for i, tname in enumerate(targets, start=1):
                        tpath = tmp_map[tname]
                        bdisp = safe_base(base_choice)
                        adisp = safe_base(tname)
                        out_name = f"{bdisp}vs{adisp}.pdf"
                        out_tmp  = os.path.join(tmpdir, out_name)
                        status.write(f"🔄 生成中: {i}/{len(targets)} — {bdisp} vs {adisp}")
                        generate_diff(base_path, tpath, out_tmp, dpi=dpi)
                        results.append((out_name, out_tmp))
                        prog.progress(int(i / len(targets) * 100))

                    status.write("✅ すべての比較が完了しました。")
                    prog.progress(100)

                    st.subheader("📄 個別ダウンロード")
                    for name, path in results:
                        with open(path, "rb") as f:
                            st.download_button(
                                label=f"⬇️ {name}",
                                data=f.read(),
                                file_name=name,
                                mime="application/pdf",
                                key=f"dl_three_{name}"
                            )

                    st.subheader("💾 ZIP一括ダウンロード")
                    out_mem = io.BytesIO()
                    with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
                        for name, path in results:
                            zf.write(path, arcname=name)
                    zip_name = f"genericBM_three_{datetime.now().strftime('%Y%m%d')}.zip"
                    st.download_button(
                        "📥 まとめてダウンロード（ZIP）",
                        data=out_mem.getvalue(),
                        file_name=zip_name,
                        mime="application/zip",
                        key="dl_three_zip"
                    )
                except Exception as e:
                    st.error(f"エラー: {e}")
            st.stop()

    elif three_files and len(three_files) == 1:
        st.info("PDFは2〜3個まとめて選択してください。")
    elif three_files and len(three_files) > 3:
        st.warning("3個まで対応しています。4個以上は2ファイル比較タブをご利用ください。")

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
