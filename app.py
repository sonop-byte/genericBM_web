# app.py — genericBM Web 軽量安定版（Streamlit 無料枠 ≈1GB 向け）
# 仕様（最終安定版に安全制限だけ追加）:
# - 📄 2ファイル比較（1対1） / 📚 3ファイル比較（1対2）
# - Before:#990099 / After:#008000
# - DPIスライダー(100〜400, 既定200) ※高DPIは警告表示、推奨=150以下
# - プレビュー: 実寸の70%で最大3ページ、複数追加表示可、❌個別閉じる
# - 比較開始時に前回の結果/プレビューをクリア（見出しも出ない）
# - 一時ファイルは TemporaryDirectory() から自動削除
# - メモリ保護（無料枠向け）:
#     1) 1ファイル上限=50MB
#     2) 合計上限=100MB（Before+After）
#     3) 1回の比較ペア数上限=3（1対1タブ）
#     4) 同時プレビュー上限=1件
#     5) DPIは150以下推奨（超えたら警告）

import os
import io
import zipfile
import tempfile
import base64
from datetime import datetime
import unicodedata
import time

import streamlit as st
from PIL import Image
import fitz  # PyMuPDF

from pdf_diff_core_small import generate_diff  # 生成コア（ファイルパス版）

# ====== カラー定義 ======
BEFORE_LABEL_COLOR = "#990099"  # 紫
AFTER_LABEL_COLOR  = "#008000"  # 緑

# ====== メモリ保護パラメータ（無料枠 ≈1GB 安定動作用） ======
MAX_UPLOAD_MB = 50                    # 1ファイルサイズ上限
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_TOTAL_MB = 100                    # Before+After 合計上限
MAX_TOTAL_BYTES = MAX_TOTAL_MB * 1024 * 1024
MAX_PAIRS_PER_RUN = 3                 # 1回に比較する最大ペア数（1対1タブ）
MAX_PREVIEWS = 1                      # 同時プレビュー上限（重さを抑制）
SAFE_DPI = 150                        # 推奨上限（超えたら警告）
TTL_SECONDS = 0                       # Web無料版ではセッションTTL削除なし（表示安定優先）

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

# ===== DPI =====
dpi = st.slider(
    "出力PDFの解像度（dpi）",
    min_value=100, max_value=400, value=200, step=50,
    help="数値が高いほど精細になりますが、生成時間と出力サイズが増えます。"
)
if dpi > SAFE_DPI:
    st.warning(f"高DPI設定（{dpi}dpi）は大容量PDFでメモリ不足を起こす場合があります。{SAFE_DPI}dpi 以下を推奨します。")

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

def _now_ts() -> float:
    return time.time()

def _ensure_with_ts(items):
    if TTL_SECONDS <= 0:
        return items
    fixed = []
    for it in items:
        if isinstance(it, (list, tuple)):
            if len(it) == 2:
                n, b = it
                fixed.append((n, b, _now_ts()))
            elif len(it) >= 3:
                n, b, ts = it[0], it[1], it[2]
                fixed.append((n, b, ts))
    return fixed

def _purge_expired(items):
    if TTL_SECONDS <= 0:
        return items
    now = _now_ts()
    kept = []
    for it in items:
        if len(it) >= 3:
            n, b, ts = it[0], it[1], it[2]
            if (now - ts) <= TTL_SECONDS:
                kept.append((n, b, ts))
    return kept

# ---- サイズチェック系 ----
def _too_large(files):
    """UploadedFile | list[UploadedFile] を受け取り、上限超の [(name, size_mb)] を返す"""
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
    """UploadedFile or list -> 合計バイト数"""
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
    """サイズ超過のエラー表示をまとめて出す"""
    if not bads:
        return
    lines = [f"**{label}** に {MAX_UPLOAD_MB}MB を超えるファイルがあります："]
    for n, mb in bads:
        lines.append(f"- {n} — {mb:.1f}MB（上限超）")
    st.error("\n".join(lines))

# ====== プレビュー（実寸の70%・最大3ページ） ======
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

# 形式統一 + TTLパージ（TTL=0 のときは素通し）
st.session_state.results_two = _purge_expired(_ensure_with_ts(st.session_state.results_two))
st.session_state.results_three = _purge_expired(_ensure_with_ts(st.session_state.results_three))
st.session_state.preview_files_two = _purge_expired(_ensure_with_ts(st.session_state.preview_files_two))
st.session_state.preview_files_three = _purge_expired(_ensure_with_ts(st.session_state.preview_files_three))

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
        before_files_two = st.file_uploader(
            "", type=["pdf"], accept_multiple_files=True,
            key="before_two", label_visibility="collapsed"
        )
    with c2:
        st.markdown(
            f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600;">After 側PDF（複数可）</div>',
            unsafe_allow_html=True
        )
        after_files_two = st.file_uploader(
            "", type=["pdf"], accept_multiple_files=True,
            key="after_two", label_visibility="collapsed"
        )

    # --- 1ファイル上限チェック ---
    bad_before = _too_large(before_files_two)
    bad_after  = _too_large(after_files_two)
    if bad_before:
        _render_size_errors(bad_before, "Before 側PDF")
    if bad_after:
        _render_size_errors(bad_after, "After 側PDF")

    # --- 合計サイズチェック ---
    total_bytes_two = _total_bytes(before_files_two) + _total_bytes(after_files_two)
    if total_bytes_two > MAX_TOTAL_BYTES:
        st.error(
            f"今回アップロードされたPDFの合計が {total_bytes_two/(1024*1024):.1f}MB です。"
            f"上限 {MAX_TOTAL_MB}MB を超えています。"
        )

    allow_two = (
        before_files_two and after_files_two
        and not bad_before and not bad_after
        and total_bytes_two <= MAX_TOTAL_BYTES
    )

    if allow_two and st.button("比較を開始（1対1）", key="btn_two"):
        # 前回の結果をクリア
        st.session_state.results_two.clear()
        st.session_state.preview_files_two.clear()
        st.session_state.run_two = True

    if st.session_state.run_two:
        st.session_state.results_two.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                b_paths, a_paths = [], []
                for f in before_files_two:
                    p = os.path.join(tmpdir, f"b_{f.name}")
                    save_uploaded_to(p, f)
                    b_paths.append(p)
                for f in after_files_two:
                    p = os.path.join(tmpdir, f"a_{f.name}")
                    save_uploaded_to(p, f)
                    a_paths.append(p)

                b_paths.sort(key=lambda p: os.path.basename(p).lower())
                a_paths.sort(key=lambda p: os.path.basename(p).lower())

                total_pairs = min(len(b_paths), len(a_paths))
                if total_pairs == 0:
                    st.info("比較対象がありません。")
                else:
                    # 1回の比較ペア数を制限
                    if total_pairs > MAX_PAIRS_PER_RUN:
                        st.warning(f"一度に比較できる上限は {MAX_PAIRS_PER_RUN} ペアです。残りは次の回で実行してください。")
                        total_pairs = MAX_PAIRS_PER_RUN

                    prog = st.progress(0)
                    status = st.empty()
                    for i in range(total_pairs):
                        b, a = b_paths[i], a_paths[i]
                        bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                        adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])
                        out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                        out_path = os.path.join(tmpdir, out_name)

                        status.write(f"🔄 生成中: {i+1}/{total_pairs} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_path, dpi=dpi)
                        with open(out_path, "rb") as fr:
                            # TTLを使わないので (name, bytes) で保持
                            st.session_state.results_two.append((out_name, fr.read()))
                        prog.progress(int((i + 1) / total_pairs * 100))
                    status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state.run_two = False

    # 生成済みの一覧 & DL & プレビュー
    if (not st.session_state.run_two) and st.session_state.results_two:
        st.subheader("📄 生成済み差分PDF")
        st.caption("クリックでプレビュー表示（複数可）")

        for idx, (name, data) in enumerate(st.session_state.results_two):
            col_l, col_r = st.columns([0.7, 0.3])
            # 一意キー（同名でも衝突しない）
            preview_key = f"preview_two_{idx}_{abs(hash(name))%100000000}"
            dl_key = f"dl_two_{idx}_{abs(hash(name))%100000000}"
            close_key = f"close_two_{idx}_{abs(hash(name))%100000000}"

            with col_l:
                if st.button(f"👁 {name}", key=preview_key):
                    if not any(n == name for (n, _) in st.session_state.preview_files_two):
                        st.session_state.preview_files_two.append((name, data))
                        # 同時プレビューを制限
                        if len(st.session_state.preview_files_two) > MAX_PREVIEWS:
                            st.session_state.preview_files_two = st.session_state.preview_files_two[-MAX_PREVIEWS:]

            with col_r:
                c_dl, c_close = st.columns(2)
                with c_dl:
                    st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=dl_key)
                with c_close:
                    if any(n == name for (n, _) in st.session_state.preview_files_two):
                        if st.button("❌ 閉じる", key=close_key):
                            st.session_state.preview_files_two = [(n, d) for (n, d) in st.session_state.preview_files_two if n != name]

        # ZIP一括DL
        st.subheader("💾 ZIP一括ダウンロード")
        out_mem = io.BytesIO()
        with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state.results_two:
                zf.writestr(name, data)
        zip_name = f"genericBM_1to1_{datetime.now().strftime('%Y%m%d')}.zip"
        st.download_button("📥 ZIP一括DL", out_mem.getvalue(), file_name=zip_name, mime="application/zip")

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
    before_file_three = st.file_uploader(
        "", type=["pdf"], key="before_three", label_visibility="collapsed"
    )

    st.markdown(
        f'<div style="color:{AFTER_LABEL_COLOR}; font-weight:600; margin-top:16px;">After 側PDF（2つ）</div>',
        unsafe_allow_html=True
    )
    after_files_three = st.file_uploader(
        "", type=["pdf"], accept_multiple_files=True,
        key="after_three", label_visibility="collapsed"
    )

    # --- 1ファイル上限チェック ---
    bad_before3 = _too_large(before_file_three)
    bad_after3  = _too_large(after_files_three)
    if bad_before3:
        _render_size_errors(bad_before3, "Before 側PDF")
    if bad_after3:
        _render_size_errors(bad_after3, "After 側PDF")

    # --- 合計サイズチェック ---
    total_bytes_three = _total_bytes(before_file_three) + _total_bytes(after_files_three)
    if total_bytes_three > MAX_TOTAL_BYTES:
        st.error(
            f"今回アップロードされたPDFの合計が {total_bytes_three/(1024*1024):.1f}MB です。"
            f"上限 {MAX_TOTAL_MB}MB を超えています。"
        )

    can_run_three = (
        before_file_three is not None
        and after_files_three is not None
        and len([f for f in after_files_three if f is not None]) == 2
        and not bad_before3 and not bad_after3
        and total_bytes_three <= MAX_TOTAL_BYTES
    )

    if can_run_three and st.button("比較を開始（1対2）", key="btn_three"):
        # 前回の結果をクリア
        st.session_state.results_three.clear()
        st.session_state.preview_files_three.clear()
        st.session_state.run_three = True

    if st.session_state.run_three:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                valid_after = [f for f in (after_files_three or []) if f is not None]
                st.session_state.results_three.clear()

                before_path = os.path.join(tmpdir, "before.pdf")
                save_uploaded_to(before_path, before_file_three)
                bdisp = safe_base(before_file_three.name)

                prog = st.progress(0)
                status = st.empty()
                total = 2
                for i, a_file in enumerate(valid_after[:2], start=1):
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

    # 生成済みの一覧 & DL & プレビュー
    if (not st.session_state.run_three) and st.session_state.results_three:
        st.subheader("📄 生成済み差分PDF")
        st.caption("クリックでプレビュー表示（複数可）")

        for idx, (name, data) in enumerate(st.session_state.results_three):
            col_l, col_r = st.columns([0.7, 0.3])
            preview_key = f"preview_three_{idx}_{abs(hash(name))%100000000}"
            dl_key = f"dl_three_{idx}_{abs(hash(name))%100000000}"
            close_key = f"close_three_{idx}_{abs(hash(name))%100000000}"

            with col_l:
                if st.button(f"👁 {name}", key=preview_key):
                    if not any(n == name for (n, _) in st.session_state.preview_files_three):
                        st.session_state.preview_files_three.append((name, data))
                        # 同時プレビューを制限
                        if len(st.session_state.preview_files_three) > MAX_PREVIEWS:
                            st.session_state.preview_files_three = st.session_state.preview_files_three[-MAX_PREVIEWS:]

            with col_r:
                c_dl, c_close = st.columns(2)
                with c_dl:
                    st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=dl_key)
                with c_close:
                    if any(n == name for (n, _) in st.session_state.preview_files_three):
                        if st.button("❌ 閉じる", key=close_key):
                            st.session_state.preview_files_three = [(n, d) for (n, d) in st.session_state.preview_files_three if n != name]

        # ZIP一括DL
        st.subheader("💾 ZIP一括ダウンロード")
        out_mem = io.BytesIO()
        with zipfile.ZipFile(out_mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state.results_three:
                zf.writestr(name, data)
        zip_name = f"genericBM_1to2_{datetime.now().strftime('%Y%m%d')}.zip"
        st.download_button(
            "📥 ZIP一括DL", out_mem.getvalue(),
            file_name=zip_name, mime="application/zip"
        )

# ====== フッター ======
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)

# 💡 運用ヒント（無料枠の安定動作用）
st.info("""
**安定動作のヒント（Streamlit無料枠 ≈1GB）**
- 1回の合計サイズは **100MB以下** を推奨
- DPIは **150以下** を推奨
- 1対1タブでは **一度に最大3ペア** まで
- プレビューは **同時1件** まで（必要に応じて ❌ で閉じる）
""")
