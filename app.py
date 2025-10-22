# app.py — genericBM Web 最終安定版（1対1専用 / DPI=72・96・144）
# 仕様：
# ・タブ：📄 2ファイル比較（1対1）のみ（1対2は削除）
# ・ラベル色：Before #990099 / After #008000
# ・DPI選択：72 / 96 / 144（初期値 144）
# ・1ファイル上限 50MB、合計上限 100MB（メモリ保護・無料枠≈1GB想定）
# ・1回の比較で最大3ペアまで処理
# ・プレビューは実寸の70%で最大3ページ表示、同時1件まで
# ・「比較を開始」時に前回の結果とプレビューをクリア

import os
import io
import zipfile
import tempfile
import base64
from datetime import datetime
import unicodedata

import streamlit as st
from PIL import Image
import fitz  # PyMuPDF

from pdf_diff_core_small import generate_diff  # 生成コア（ファイルパス版）

# ===== カラー =====
BEFORE_LABEL_COLOR = "#990099"
AFTER_LABEL_COLOR  = "#008000"

# ===== メモリ保護（無料枠 ≈1GB） =====
MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_TOTAL_MB = 100
MAX_TOTAL_BYTES = MAX_TOTAL_MB * 1024 * 1024
MAX_PAIRS_PER_RUN = 3   # 1回で比較する最大ペア
MAX_PREVIEWS = 1        # 同時プレビュー上限

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

# ===== ヘッダ =====
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

# ===== DPI（72 / 96 / 144 のみ） =====
dpi = st.select_slider(
    "出力PDFの解像度（dpi）",
    options=[72, 96, 144],
    value=144,
    help="数値が高いほど精細になりますが、処理時間とメモリ使用量が増加します。"
)

# ===== ユーティリティ =====
def safe_base(path_or_name: str) -> str:
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return unicodedata.normalize("NFC", name)

def save_uploaded_to(path: str, uploaded) -> None:
    with open(path, "wb") as f:
        f.write(uploaded.read())

def add_date_suffix(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    return f"{base}_{datetime.now().strftime('%Y%m%d')}{ext}"

def _too_large(files):
    """サイズ上限を超えるファイルを列挙"""
    if not files:
        return []
    if not isinstance(files, (list, tuple)):
        files = [files]
    bad = []
    for f in files:
        try:
            sz = getattr(f, "size", None)
            if sz is not None and sz > MAX_UPLOAD_BYTES:
                bad.append((f.name, sz / (1024*1024)))
        except Exception:
            pass
    return bad

def _total_bytes(files):
    """合計バイト数"""
    if not files:
        return 0
    if not isinstance(files, (list, tuple)):
        files = [files]
    total = 0
    for f in files:
        try:
            total += getattr(f, "size", 0) or 0
        except Exception:
            pass
    return total

def _render_size_errors(bads, label):
    if not bads:
        return
    lines = [f"**{label}** に {MAX_UPLOAD_MB}MB を超えるファイルがあります："]
    for n, mb in bads:
        lines.append(f"- {n} — {mb:.1f}MB（上限超）")
    st.error("\n".join(lines))

# ===== プレビュー（実寸70%、最大3ページ） =====
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
        html_parts.append(
            f"""
<div style="display:flex;justify-content:center;margin-bottom:24px;">
  <div style="width:{sw}px;border:1px solid #ddd;border-radius:8px;box-sizing:border-box;background:#fafafa;">
    <div style="font-size:0.9em;color:#666;text-align:right;margin:6px 8px 0 0;">
      Page {idx}（{int(SCALE*100)}%表示）
    </div>
    <div style="width:{sw}px;max-height:85vh;overflow:auto;margin:8px auto 12px auto;">
      <img src="data:image/png;base64,{b64}" width="{sw}" height="{sh}" style="display:block;margin:0 auto;" />
    </div>
  </div>
</div>
            """
        )
    st.markdown("".join(html_parts), unsafe_allow_html=True)

# ===== セッション初期化（1対1のみ） =====
for key in ["results_two", "preview_files_two"]:
    if key not in st.session_state:
        st.session_state[key] = []
st.session_state.setdefault("run_two", False)

# ===== タブ（1対1のみ） =====
(tab_two,) = st.tabs(["📄 2ファイル比較（1対1）"])

# -------------------------------
# 📄 2ファイル比較（1対1）
# -------------------------------
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF</div>', unsafe_allow_html=True)
        before_files_two = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="before_two", label_visibility="collapsed")
    with c2:
        st.markdown(f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600;">After 側PDF</div>', unsafe_allow_html=True)
        after_files_two = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="after_two", label_visibility="collapsed")

    # 上限チェック
    bad_before = _too_large(before_files_two)
    bad_after  = _too_large(after_files_two)
    total_bytes_two = _total_bytes(before_files_two) + _total_bytes(after_files_two)

    if bad_before: _render_size_errors(bad_before, "Before 側PDF")
    if bad_after:  _render_size_errors(bad_after,  "After 側PDF")
    if total_bytes_two > MAX_TOTAL_BYTES:
        st.error(f"合計 {total_bytes_two/(1024*1024):.1f}MB → 上限 {MAX_TOTAL_MB}MB を超えています。")

    allow_two = (
        before_files_two and after_files_two and
        not bad_before and not bad_after and
        total_bytes_two <= MAX_TOTAL_BYTES
    )

    # 実行トリガ
    if allow_two and st.button("比較を開始（1対1）", key="btn_two"):
        st.session_state.results_two.clear()
        st.session_state.preview_files_two.clear()
        st.session_state.run_two = True

    # 生成処理
    if st.session_state.run_two:
        st.session_state.results_two.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                b_paths, a_paths = [], []
                for f in before_files_two:
                    p = os.path.join(tmpdir, f"b_{f.name}"); save_uploaded_to(p, f); b_paths.append(p)
                for f in after_files_two:
                    p = os.path.join(tmpdir, f"a_{f.name}"); save_uploaded_to(p, f); a_paths.append(p)

                total_pairs = min(len(b_paths), len(a_paths), MAX_PAIRS_PER_RUN)
                prog = st.progress(0)
                status = st.empty()

                for i in range(total_pairs):
                    b, a = b_paths[i], a_paths[i]
                    out_name = add_date_suffix(f"{safe_base(b)}vs{safe_base(a)}.pdf")
                    out_path = os.path.join(tmpdir, out_name)
                    status.write(f"🔄 生成中: {i+1}/{total_pairs}")
                    generate_diff(b, a, out_path, dpi=dpi)
                    with open(out_path, "rb") as fr:
                        st.session_state.results_two.append((out_name, fr.read()))
                    prog.progress(int((i+1)/total_pairs*100))
                status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state.run_two = False

    # 結果表示
    if st.session_state.results_two:
        st.subheader("📄 生成済み差分PDF")
        for idx, (name, data) in enumerate(st.session_state.results_two):
            col_l, col_r = st.columns([0.7, 0.3])
            if col_l.button(f"👁 {name}", key=f"pv2_{idx}"):
                # プレビューは最新1件だけ残す設計
                st.session_state.preview_files_two = [(name, data)]
            col_r.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf")

        if st.session_state.preview_files_two:
            st.markdown("---")
            for name, data in st.session_state.preview_files_two:
                show_pdf_inline(name, data)

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>© genericBM (OpenAI + mmMIG)</div>",
    unsafe_allow_html=True
)
