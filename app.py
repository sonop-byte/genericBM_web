# app.py — genericBM Web（最適化・安定版）
import os
import io
import zipfile
import tempfile
import base64
from datetime import datetime
import unicodedata
import streamlit as st
from PIL import Image
import fitz
from pdf_diff_core_small import generate_diff

# ====== 定数・スタイル設定 ======
BEFORE_LABEL_COLOR = "#990099"
AFTER_LABEL_COLOR = "#008000"

ICON_PATH = "gBmicon.png"
icon_img = Image.open(ICON_PATH) if os.path.exists(ICON_PATH) else None

st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon=icon_img if icon_img else "🩺",
    layout="centered",
)

st.markdown("""
<div style='text-align:center;'>
    <img src='https://raw.githubusercontent.com/sonop-byte/genericBM_web/main/gBmicon.png'
         width='120' style='display:block; margin:auto; margin-bottom:10px;'>
    <h1 style='font-size:2.2em; margin-bottom:6px;'>genericBM – PDF差分比較ツール（Web版）</h1>
    <p style='color:gray; font-size:1.0em;'>修正前・修正後のPDFをアップロードして差分を作成します。</p>
</div>
""", unsafe_allow_html=True)

# ====== ユーティリティ関数 ======
def safe_base(path_or_name: str) -> str:
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return unicodedata.normalize("NFC", name)

def save_uploaded_to(path: str, uploaded) -> None:
    with open(path, "wb") as f:
        f.write(uploaded.read())

def add_date_suffix(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    return f"{base}_{datetime.now().strftime('%Y%m%d')}{ext}"

# ====== プレビュー関数 ======
def show_pdf_inline(name: str, data_bytes: bytes) -> None:
    PREVIEW_MAX_PAGES = 3
    PREVIEW_DPI = 144
    SCALE = 0.7

    doc = fitz.open(stream=data_bytes, filetype="pdf")
    n_pages = min(PREVIEW_MAX_PAGES, doc.page_count)
    pages = []

    for i in range(n_pages):
        page = doc.load_page(i)
        zoom = PREVIEW_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        pages.append((pix.width, pix.height, b64))
    doc.close()

    if not pages:
        st.markdown(
            f"""
<div style="padding:10px;border:1px solid #ccc;border-radius:8px;">
  <div style="font-weight:600;">👁 プレビュー：{name}</div>
  <div>プレビューできるページがありません。</div>
</div>
            """,
            unsafe_allow_html=True
        )
        return

    html_parts = [f'<div style="text-align:center;font-weight:600;margin-bottom:6px;">👁 プレビュー：{name}</div>']
    for idx, (w, h, b64) in enumerate(pages, start=1):
        sw, sh = int(w * SCALE), int(h * SCALE)
        html_parts.append(f"""
<div style="display:flex;justify-content:center;margin-bottom:24px;">
  <div style="width:{sw}px;border:1px solid #ddd;border-radius:8px;background:#fafafa;">
    <div style="font-size:0.9em;color:#666;text-align:right;margin:6px 8px 0 0;">Page {idx}（{int(SCALE*100)}%表示）</div>
    <div style="width:{sw}px;max-height:85vh;overflow:auto;margin:8px auto 12px auto;">
      <img src="data:image/png;base64,{b64}" width="{sw}" height="{sh}" style="display:block;margin:0 auto;" />
    </div>
  </div>
</div>
""")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

# ====== 結果表示・DL・プレビュー管理 ======
def render_results_section(results, preview_state_key: str, zip_prefix: str, dl_key_prefix: str):
    if not results:
        return
    st.subheader("📄 生成済み差分PDF")
    st.caption("クリックでプレビュー表示（複数可）")

    for name, data in results:
        col_l, col_r = st.columns([0.7, 0.3])
        with col_l:
            if st.button(f"👁 {name}", key=f"{preview_state_key}_btn_{name}"):
                if not any(n == name for n, _ in st.session_state[preview_state_key]):
                    st.session_state[preview_state_key].append((name, data))
        with col_r:
            c_dl, c_close = st.columns(2)
            with c_dl:
                st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf",
                                   key=f"{dl_key_prefix}_{name}")
            with c_close:
                if any(n == name for n, _ in st.session_state[preview_state_key]):
                    if st.button("❌ 閉じる", key=f"close_{preview_state_key}_{name}"):
                        st.session_state[preview_state_key] = [
                            (n, d) for n, d in st.session_state[preview_state_key] if n != name
                        ]

    st.subheader("💾 ZIP一括ダウンロード")
    out_mem = io.BytesIO()
    with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in results:
            zf.writestr(name, data)
    st.download_button("📥 ZIP一括DL", out_mem.getvalue(),
                       file_name=f"{zip_prefix}_{datetime.now().strftime('%Y%m%d')}.zip",
                       mime="application/zip")

    col_clear, _ = st.columns([0.25, 0.75])
    with col_clear:
        if st.button("🧹 プレビューをすべてクリア", key=f"clear_{preview_state_key}"):
            st.session_state[preview_state_key] = []

    if st.session_state[preview_state_key]:
        st.markdown("---")
        for name, data in st.session_state[preview_state_key]:
            show_pdf_inline(name, data)

# ====== セッション状態 ======
if "results_two" not in st.session_state:
    st.session_state.results_two = []
if "results_three" not in st.session_state:
    st.session_state.results_three = []
if "preview_files_two" not in st.session_state:
    st.session_state.preview_files_two = []
if "preview_files_three" not in st.session_state:
    st.session_state.preview_files_three = []

# ====== DPI設定スライダー ======
dpi = st.slider("出力PDFの解像度（dpi）", min_value=100, max_value=400, value=200, step=50)

# ====== タブ構成 ======
tab_two, tab_three = st.tabs(["📄 2ファイル比較（1対1）", "📚 3ファイル比較（1対2）"])

# ====== 1対1タブ ======
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF（複数可）</div>',
                    unsafe_allow_html=True)
        before_files = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="before_two",
                                        label_visibility="collapsed")
    with c2:
        st.markdown(f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600;">After 側PDF（複数可）</div>',
                    unsafe_allow_html=True)
        after_files = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="after_two",
                                       label_visibility="collapsed")

if before_files and after_files and st.button("比較を開始（1対1）", key="btn_two"):
    st.session_state.results_two.clear()
    # 新規生成時に既存プレビューを空にする場合は下行を残す／維持したいなら消す
    # st.session_state.preview_files_two = []

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # ファイルを保存＆ソート
            b_sorted = sorted(before_files, key=lambda f: f.name)
            a_sorted = sorted(after_files, key=lambda f: f.name)

            for b, a in zip(b_sorted, a_sorted):
                b_path = os.path.join(tmpdir, f"b_{b.name}")
                a_path = os.path.join(tmpdir, f"a_{a.name}")
                save_uploaded_to(b_path, b)
                save_uploaded_to(a_path, a)

                out_name = add_date_suffix(f"{safe_base(b.name)}vs{safe_base(a.name)}.pdf")
                out_path = os.path.join(tmpdir, out_name)
                generate_diff(b_path, a_path, out_path, dpi=dpi)

                with open(out_path, "rb") as fr:
                    st.session_state.results_two.append((out_name, fr.read()))
        except Exception as e:
            st.error(f"エラー: {e}")


    if st.session_state.results_two:
        render_results_section(st.session_state.results_two, "preview_files_two", "genericBM_1to1", "dl_two")

# ====== 1対2タブ ======
with tab_three:
    before_file = st.file_uploader("Before 側PDF（1つ）", type=["pdf"], key="before_three")
    after_files = st.file_uploader("After 側PDF（2つ）", type=["pdf"], accept_multiple_files=True, key="after_three")

    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        with tempfile.TemporaryDirectory() as tmpdir:
            st.session_state.results_three.clear()
            before_path = os.path.join(tmpdir, before_file.name)
            save_uploaded_to(before_path, before_file)
            for a in after_files:
                a_path = os.path.join(tmpdir, a.name)
                save_uploaded_to(a_path, a)
                out_name = add_date_suffix(f"{safe_base(before_file.name)}vs{safe_base(a.name)}.pdf")
                out_path = os.path.join(tmpdir, out_name)
                generate_diff(before_path, a_path, out_path, dpi=dpi)
                with open(out_path, "rb") as fr:
                    st.session_state.results_three.append((out_name, fr.read()))

    if st.session_state.results_three:
        render_results_section(st.session_state.results_three, "preview_files_three", "genericBM_1to2", "dl_three")

# ====== フッター ======
st.markdown("<hr><div style='text-align:center; font-size:0.85em; color:gray;'>© genericBM (OpenAI + mmMIG)</div>",
            unsafe_allow_html=True)
