# app.py — genericBM（現時点・完全版）
# ・タブ名：📄 2ファイル比較（1対1）／📚 3ファイル比較（1対2）
# ・1対2タブの見出し色/太字は1対1と統一（Before: #990099 / After: #008000）
# ・差分PDFプレビュー：実寸の70%でページごと中央表示（A4/A3混在OK）
# ・1対1/1対2 ともに、生成後はファイル名クリックでプレビューを“追加表示”できる

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

from pdf_diff_core_small import generate_diff  # コア（ファイルパス版）

# ====== カラー定義 ======
BEFORE_LABEL_COLOR = "#990099"  # 紫
AFTER_LABEL_COLOR  = "#008000"  # 緑

# ====== ページ設定（アイコンがあれば使用） ======
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

# ====== ヘッダ ======
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

# ====== DPI スライダー ======
dpi = st.slider(
    "出力PDFの解像度（dpi）",
    min_value=100, max_value=400, value=200, step=50,
    help="数値が高いほど精細になりますが、生成時間と出力サイズが増えます。"
)

# ====== ユーティリティ ======
def safe_base(path_or_name: str) -> str:
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return unicodedata.normalize("NFC", name)

def save_uploaded_to(path: str, uploaded) -> None:
    with open(path, "wb") as f:
        f.write(uploaded.read())

def add_date_suffix(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    return f"{base}_{datetime.now().strftime('%Y%m%d')}{ext}"

# ====== プレビュー（実寸の70%・ページごと中央） ======
def show_pdf_inline(name: str, data_bytes: bytes) -> None:
    PREVIEW_MAX_PAGES = 3
    PREVIEW_DPI = 144
    SCALE = 0.7  # 70%

    doc = fitz.open(stream=data_bytes, filetype="pdf")
    n_pages = min(PREVIEW_MAX_PAGES, doc.page_count)

    pages = []  # [(w, h, b64), ...]
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
        return  # 👈 ここを忘れずに！

    html_parts = [
        f'<div style="text-align:center;font-weight:600;margin-bottom:6px;">👁 プレビュー：{name}</div>'
    ]
    for idx, (w, h, b64) in enumerate(pages, start=1):
        sw = int(w * SCALE)
        sh = int(h * SCALE)
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

    st.markdown("".join(html_parts), unsafe_allow_html=True)  # ✅ これが関数の中に入っていることが重要


# ====== 結果表示・DL・プレビュー管理 ======
def render_results_section(results, preview_state_key: str, zip_prefix: str, dl_key_prefix: str):
    """
    results: [(name, bytes)]
    preview_state_key: 'preview_files_two' or 'preview_files_three'
    zip_prefix: 'genericBM_1to1' / 'genericBM_1to2'
    dl_key_prefix: 'dl_two' / 'dl_three'
    """
    if not results:
        return

    st.subheader("📄 生成済み差分PDF")
    st.caption("クリックでプレビュー表示（複数可）")

    for name, data in results:
        col_l, col_r = st.columns([0.7, 0.3])

        # 左：プレビュー追加
        with col_l:
            if st.button(f"👁 {name}", key=f"{preview_state_key}_btn_{name}"):
                if not any(n == name for n, _ in st.session_state[preview_state_key]):
                    st.session_state[preview_state_key].append((name, data))

        # 右：DL + 閉じるボタン
        with col_r:
            c_dl, c_close = st.columns(2)
            with c_dl:
                st.download_button(
                    "⬇️ DL", data=data, file_name=name,
                    mime="application/pdf", key=f"{dl_key_prefix}_{name}"
                )
            with c_close:
                if any(n == name for n, _ in st.session_state[preview_state_key]):
                    if st.button("❌ 閉じる", key=f"close_{preview_state_key}_{name}"):
                        st.session_state[preview_state_key] = [
                            (n, d) for n, d in st.session_state[preview_state_key] if n != name
                        ]

    # ZIP 一括DL
    st.subheader("💾 ZIP一括ダウンロード")
    out_mem = io.BytesIO()
    with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in results:
            zf.writestr(name, data)
    st.download_button(
        "📥 ZIP一括DL", out_mem.getvalue(),
        file_name=f"{zip_prefix}_{datetime.now().strftime('%Y%m%d')}.zip",
        mime="application/zip"
    )

    # 🧹まとめて消す
    col_clear, _ = st.columns([0.25, 0.75])
    with col_clear:
        if st.button("🧹 プレビューをすべてクリア", key=f"clear_{preview_state_key}"):
            st.session_state[preview_state_key] = []

    # プレビュー表示（複数）
    if st.session_state[preview_state_key]:
        st.markdown("---")
        for name, data in st.session_state[preview_state_key]:
            show_pdf_inline(name, data)


        return

    html_parts = [
        f'<div style="text-align:center;font-weight:600;margin-bottom:6px;">👁 プレビュー：{name}</div>'
    ]
    for idx, (w, h, b64) in enumerate(pages, start=1):
        sw = int(w * SCALE)
        sh = int(h * SCALE)
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

# ====== セッション状態 ======
if "results_two" not in st.session_state:
    st.session_state.results_two = []
if "results_three" not in st.session_state:
    st.session_state.results_three = []
if "preview_file" not in st.session_state:
    st.session_state.preview_file = None  # （後方互換・未使用可）
if "preview_files_two" not in st.session_state:
    st.session_state.preview_files_two = []  # 1対1の複数プレビュー
if "preview_files_three" not in st.session_state:
    st.session_state.preview_files_three = []  # 1対2の複数プレビュー
if "run_two" not in st.session_state:
    st.session_state.run_two = False
if "run_three" not in st.session_state:
    st.session_state.run_three = False

# ====== タブ ======
tab_two, tab_three = st.tabs(["📄 2ファイル比較（1対1）", "📚 3ファイル比較（1対2）"])

# -------------------------------
# 📄 2ファイル比較（1対1）
# -------------------------------
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF（複数可）</div>',
            unsafe_allow_html=True
        )
        before_files = st.file_uploader(
            "", type=["pdf"], accept_multiple_files=True,
            key="before_two", label_visibility="collapsed"
        )
    with c2:
        st.markdown(
            f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600;">After 側PDF（複数可）</div>',
            unsafe_allow_html=True
        )
        after_files = st.file_uploader(
            "", type=["pdf"], accept_multiple_files=True,
            key="after_two", label_visibility="collapsed"
        )

    if before_files and after_files and st.button("比較を開始（1対1）", key="btn_two"):
        st.session_state.run_two = True

    if st.session_state.run_two:
        st.session_state.results_two.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                b_paths, a_paths = [], []
                for f in before_files:
                    p = os.path.join(tmpdir, f"b_{f.name}")
                    save_uploaded_to(p, f)
                    b_paths.append(p)
                for f in after_files:
                    p = os.path.join(tmpdir, f"a_{f.name}")
                    save_uploaded_to(p, f)
                    a_paths.append(p)

                b_paths.sort(key=lambda p: os.path.basename(p).lower())
                a_paths.sort(key=lambda p: os.path.basename(p).lower())

                total = min(len(b_paths), len(a_paths))
                if total == 0:
                    st.info("比較対象がありません。")
                else:
                    prog = st.progress(0)
                    status = st.empty()
                    for i in range(total):
                        b, a = b_paths[i], a_paths[i]
                        bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                        adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])
                        out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                        out_path = os.path.join(tmpdir, out_name)

                        status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_path, dpi=dpi)
                        with open(out_path, "rb") as fr:
                            st.session_state.results_two.append((out_name, fr.read()))
                        prog.progress(int((i + 1) / total * 100))
                    status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state.run_two = False

# ▼ 1対1：生成済み一覧・DL・複数プレビュー
if st.session_state.results_two:
    st.subheader("📄 生成済み差分PDF")
    st.caption("クリックでプレビュー表示（複数可）")

    for idx, (name, data) in enumerate(st.session_state.results_two):
        col_l, col_r = st.columns([0.7, 0.3])

        # 一意キー（プレビュー/ダウンロード/閉じる で共通に使う）
        preview_key = f"preview_two_{idx}_{abs(hash(name))%100000000}"
        dl_key      = f"dl_two_{idx}_{abs(hash(name))%100000000}"
        close_key   = f"close_two_{idx}_{abs(hash(name))%100000000}"

        with col_l:
            if st.button(f"👁 {name}", key=preview_key):
                if not any(n == name for n, _ in st.session_state.preview_files_two):
                    st.session_state.preview_files_two.append((name, data))

        with col_r:
            c_dl, c_close = st.columns(2)
            with c_dl:
                st.download_button("⬇️ DL", data=data, file_name=name,
                                   mime="application/pdf", key=dl_key)
            with c_close:
                # すでにプレビューにある場合だけ「❌ 閉じる」を表示
                if any(n == name for n, _ in st.session_state.preview_files_two):
                    if st.button("❌ 閉じる", key=close_key):
                        st.session_state.preview_files_two = [
                            (n, d) for n, d in st.session_state.preview_files_two if n != name
                        ]

    st.subheader("💾 ZIP一括ダウンロード")
    out_mem = io.BytesIO()
    with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in st.session_state.results_two:
            zf.writestr(name, data)
    zip_name = f"genericBM_1to1_{datetime.now().strftime('%Y%m%d')}.zip"
    st.download_button("📥 ZIP一括DL", out_mem.getvalue(),
                       file_name=zip_name, mime="application/zip")

    # 追加されたプレビューを順に表示
    if st.session_state.preview_files_two:
        st.markdown("---")
        for name, data in st.session_state.preview_files_two:
            show_pdf_inline(name, data)

# -------------------------------
# 📚 3ファイル比較（1対2）
# -------------------------------
with tab_three:
    st.markdown(
        f'<div style="color:{BEFORE_LABEL_COLOR}; font-weight:600;">Before 側PDF（1つ）</div>',
        unsafe_allow_html=True
    )
    before_file = st.file_uploader(
        "", type=["pdf"], key="before_three", label_visibility="collapsed"
    )

    st.markdown(
        f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600; margin-top:16px;">After 側PDF（2つ）</div>',
        unsafe_allow_html=True
    )
    after_files = st.file_uploader(
        "", type=["pdf"], accept_multiple_files=True,
        key="after_three", label_visibility="collapsed"
    )

    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        st.session_state.run_three = True

    if st.session_state.run_three:
        st.session_state.results_three.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                before_path = os.path.join(tmpdir, "before.pdf")
                save_uploaded_to(before_path, before_file)
                bdisp = safe_base(before_file.name)

                prog = st.progress(0)
                status = st.empty()
                total = 2
                for i, a_file in enumerate(after_files, start=1):
                    a_path = os.path.join(tmpdir, f"after_{i}.pdf")
                    save_uploaded_to(a_path, a_file)
                    adisp = safe_base(a_file.name)
                    out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                    out_tmp = os.path.join(tmpdir, out_name)

                    status.write(f"🔄 生成中: {i}/{total} — {bdisp} vs {adisp}")
                    generate_diff(before_path, a_path, out_tmp, dpi=dpi)

                    with open(out_tmp, "rb") as fr:
                        st.session_state.results_three.append((out_name, fr.read()))
                    prog.progress(int(i / total * 100))
                status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state.run_three = False

# ▼ 1対2：生成済み一覧・DL・複数プレビュー
if st.session_state.results_three:
    st.subheader("📄 生成済み差分PDF")
    st.caption("クリックでプレビュー表示（複数可）")

    for idx, (name, data) in enumerate(st.session_state.results_three):
        col_l, col_r = st.columns([0.7, 0.3])

        preview_key = f"preview_three_{idx}_{abs(hash(name))%100000000}"
        dl_key      = f"dl_three_{idx}_{abs(hash(name))%100000000}"
        close_key   = f"close_three_{idx}_{abs(hash(name))%100000000}"

        with col_l:
            if st.button(f"👁 {name}", key=preview_key):
                if not any(n == name for n, _ in st.session_state.preview_files_three):
                    st.session_state.preview_files_three.append((name, data))

        with col_r:
            c_dl, c_close = st.columns(2)
            with c_dl:
                st.download_button("⬇️ DL", data=data, file_name=name,
                                   mime="application/pdf", key=dl_key)
            with c_close:
                if any(n == name for n, _ in st.session_state.preview_files_three):
                    if st.button("❌ 閉じる", key=close_key):
                        st.session_state.preview_files_three = [
                            (n, d) for n, d in st.session_state.preview_files_three if n != name
                        ]

    st.subheader("💾 ZIP一括ダウンロード")
    out_mem = io.BytesIO()
    with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in st.session_state.results_three:
            zf.writestr(name, data)
    zip_name = f"genericBM_1to2_{datetime.now().strftime('%Y%m%d')}.zip"
    st.download_button("📥 ZIP一括DL", out_mem.getvalue(),
                       file_name=zip_name, mime="application/zip")

    if st.session_state.preview_files_three:
        st.markdown("---")
        for name, data in st.session_state.preview_files_three:
            show_pdf_inline(name, data)


# ====== 後方互換の単一プレビュー（不要なら削除可） ======
if (not st.session_state.get("preview_files_two")) and (not st.session_state.get("preview_files_three")):
    if st.session_state.get("preview_file"):
        name, data = st.session_state.preview_file
        st.markdown("---")
        show_pdf_inline(name, data)

# ====== フッター ======
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
