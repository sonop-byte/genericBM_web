# app.py — genericBM Web（クリック時プレビュー／プレビュー領域1500px／注記＆ラベル色）
# 機能:
# ・タブ2種：📄 2ファイル比較（1:1固定, 余剰は無視）／📚 3ファイル比較（Before1 vs After2）
# ・結果は st.session_state に保持（次のアップロードまで残る）
# ・個別DL + ZIP一括DL
# ・ファイル名クリックで下部にプレビュー（画像化、幅1500pxコンテナ）
# ・出力名は「BeforevsAfter_YYYYMMDD.pdf」
# ・実行フラグでワンショット実行（st.stop 未使用）
# ・DPIスライダーは常時表示
# ・2ファイル比較のラベル色: Before=#990099, After=#008000

import os
import io
import zipfile
import tempfile
import base64
from datetime import datetime
import unicodedata

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from pdf_diff_core_small import generate_diff

# ===== UI Colors =====
BEFORE_LABEL_COLOR = "#990099"
AFTER_LABEL_COLOR  = "#008000"

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
    layout="centered",   # 全体幅は従来どおり
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

# ===== 出力PDFの解像度（dpi） ← 常時表示 =====
dpi = st.slider(
    "出力PDFの解像度（dpi）",
    min_value=100, max_value=400, value=200, step=50,
    help="数値が高いほど精細になりますが、生成時間と出力サイズが増えます。"
)

# ===== ユーティリティ =====
def safe_base(path_or_name: str) -> str:
    """拡張子を除いたファイル名をNFCで返す"""
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return unicodedata.normalize("NFC", name)

def save_uploaded_to(path: str, uploaded) -> None:
    with open(path, "wb") as f:
        f.write(uploaded.read())

def add_date_suffix(filename: str) -> str:
    """末尾に _YYYYMMDD を追加"""
    base, ext = os.path.splitext(filename)
    return f"{base}_{datetime.now().strftime('%Y%m%d')}{ext}"

def show_pdf_inline(name: str, data_bytes: bytes):
    """PDFの先頭数ページを画像化してプレビュー表示（1500px幅の専用コンテナ・原寸基準）"""
    import fitz  # PyMuPDF
    from PIL import Image as PILImage

    PREVIEW_MAX_PAGES = 3
    PREVIEW_DPI = 144

    # PDF→PNG に変換（先頭数ページ）
    doc = fitz.open(stream=data_bytes, filetype="pdf")
    n_pages = min(PREVIEW_MAX_PAGES, doc.page_count)
    img_tags = []
    for i in range(n_pages):
        page = doc.load_page(i)
        zoom = PREVIEW_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        # max-width:100% → 原寸を超える拡大はしない（1500px枠に収まる）
        img_tags.append(
            f"<img src='data:image/png;base64,{b64}' "
            f"style='display:block;margin:12px auto;max-width:100%;height:auto;'/>"
        )
    doc.close()

    html = f"""
    <div style="max-width:1500px;margin:0 auto;border:1px solid #ddd;border-radius:8px;padding:8px 12px;">
      <div style="font-weight:600;margin-bottom:6px;">👁 プレビュー：{name}</div>
      {''.join(img_tags) if img_tags else '<div style="padding:10px;">プレビューできるページがありません。</div>'}
    </div>
    """
    # 高さはページ数から目安で計算（スクロール可）
    est_height = min(1200, 260 * max(1, n_pages) + 80)
    components.html(html, height=est_height, scrolling=True)

# ===== セッション初期化 =====
if "results_two" not in st.session_state:
    st.session_state.results_two = []   # [(name:str, bytes)]
if "results_three" not in st.session_state:
    st.session_state.results_three = [] # [(name:str, bytes)]
if "preview_file" not in st.session_state:
    st.session_state.preview_file = None  # (name, bytes) or None

# 実行フラグ（ワンショット実行用）
if "run_two" not in st.session_state:
    st.session_state.run_two = False
if "run_three" not in st.session_state:
    st.session_state.run_three = False

# ===== タブ構成 =====
tab_two, tab_three = st.tabs(["📄 2ファイル比較（1:1固定）", "📚 3ファイル比較（1対2）"])

# ---------------------------------------------------------------
# 📄 タブ1：2ファイル比較（ファイル名順で1:1固定・余剰は無視）
# ---------------------------------------------------------------
with tab_two:
    c1, c2 = st.columns(2)

    # ラベル色だけ変更。uploaderのラベルは隠す（CSSは使わない）
    with c1:
       st.markdown(f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF（複数可）</div>', unsafe_allow_html=True)
with tab_two:
    c1, c2 = st.columns(2)

    # ラベル色だけ変更。uploaderのラベルは隠す（CSSは使わない）
    with c1:
        st.markdown(f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF（複数可）</div>', unsafe_allow_html=True)
        before_files = st.file_uploader(
            label="",
            type=["pdf"],
            accept_multiple_files=True,
            key="before_two",
            label_visibility="collapsed"
        )

    with c2:
        st.markdown(f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600;">After 側PDF（複数可）</div>', unsafe_allow_html=True)
        after_files = st.file_uploader(
            label="",
            type=["pdf"],
            accept_multiple_files=True,
            key="after_two",
            label_visibility="collapsed"
        )

    # ボタン押下で実行フラグON
    if before_files and after_files and st.button("比較を開始（1:1）", key="btn_two"):
        st.session_state.run_two = True

    # 実行フラグがTrueのときだけ処理
    if st.session_state.run_two:
        st.session_state.results_two.clear()  # 新しい比較開始でリセット
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # 一時保存 & ファイル名順ソート
                b_paths = []
                for f in before_files:
                    p = os.path.join(tmpdir, f"b_{f.name}")
                    save_uploaded_to(p, f)
                    b_paths.append(p)
                a_paths = []
                for f in after_files:
                    p = os.path.join(tmpdir, f"a_{f.name}")
                    save_uploaded_to(p, f)
                    a_paths.append(p)
                b_paths.sort(key=lambda p: os.path.basename(p).lower())
                a_paths.sort(key=lambda p: os.path.basename(p).lower())

                total = min(len(b_paths), len(a_paths))  # 余剰は無視
                if total == 0:
                    st.info("比較対象がありません。")
                else:
                    prog = st.progress(0)
                    status = st.empty()
                    for i in range(total):
                        b = b_paths[i]
                        a = a_paths[i]
                        bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                        adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])
                        out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                        out_path = os.path.join(tmpdir, out_name)
                        status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_path, dpi=dpi)
                        with open(out_path, "rb") as fr:
                            st.session_state.results_two.append((out_name, fr.read()))
                        prog.progress(int((i+1)/total*100))
                    status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        # フラグを必ずOFFに
        st.session_state.run_two = False

    # 生成済みPDF一覧（保持して表示）
    if st.session_state.results_two:
        st.subheader("📄 生成済み差分PDF")
        st.caption("クリックでプレビュー表示")
        for name, data in st.session_state.results_two:
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👁 {name}", key=f"preview_two_{name}"):
                    st.session_state.preview_file = (name, data)  # ← クリック時だけセット
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

    # ボタン押下で実行フラグON
    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        st.session_state.run_three = True

    # 実行フラグがTrueのときだけ処理
    if st.session_state.run_three:
        st.session_state.results_three.clear()  # 新しい比較開始でリセット
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                before_path = os.path.join(tmpdir, "before.pdf")
                save_uploaded_to(before_path, before_file)
                bdisp = safe_base(before_file.name)

                prog = st.progress(0)
                status = st.empty()

                total = 2  # Afterは2つ想定
                for i, a_file in enumerate(after_files, start=1):
                    a_path = os.path.join(tmpdir, f"after_{i}.pdf")
                    save_uploaded_to(a_path, a_file)
                    adisp = safe_base(a_file.name)

                    out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                    out_tmp  = os.path.join(tmpdir, out_name)

                    status.write(f"🔄 生成中: {i}/{total} — {bdisp} vs {adisp}")
                    generate_diff(before_path, a_path, out_tmp, dpi=dpi)

                    with open(out_tmp, "rb") as fr:
                        st.session_state.results_three.append((out_name, fr.read()))
                    prog.progress(int(i/total*100))

                status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        # フラグを必ずOFFに
        st.session_state.run_three = False

    # 生成済みPDF一覧（保持して表示）
    if st.session_state.results_three:
        st.subheader("📄 生成済み差分PDF")
        st.caption("クリックでプレビュー表示")
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
# 👁 プレビュー表示（クリック時のみ、ページ下部に表示）
# ---------------------------------------------------------------
if st.session_state.preview_file:
    name, data = st.session_state.preview_file
    st.markdown("---")
    show_pdf_inline(name, data)

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
