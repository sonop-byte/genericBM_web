# app.py — genericBM Web（中央ロゴ・サイドバーなし・3機能統合）
import os
import io
import zipfile
import tempfile
from datetime import datetime

import streamlit as st
from PIL import Image
from pdf_diff_core_small import generate_diff

# ===== ページ設定（favicon はローカル画像を安全に読込） =====
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

# ===== ヘッダー（中央寄せ：ロゴ＋タイトル＋説明） =====
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
            修正前・修正後のPDF（またはフォルダZIP）をアップロードして差分を作成します。
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# ===== 共通オプション =====
with st.expander("詳細設定", expanded=False):
    dpi = st.slider("出力PDFの解像度（dpi）", min_value=100, max_value=400, value=200, step=50)
    st.caption("数値が高いほど精細になりますが、生成時間と出力サイズが増えます。")

# ===== ユーティリティ =====
def safe_base(path_or_name: str) -> str:
    """拡張子除去したベース名（入力がパスでもファイル名にして処理）"""
    return os.path.splitext(os.path.basename(path_or_name))[0]

def collect_top_level_pdfs(root_dir: str):
    """直下のみのPDFパスをファイル名順で返す"""
    items = [f for f in os.listdir(root_dir) if os.path.isfile(os.path.join(root_dir, f))]
    pdfs = [os.path.join(root_dir, f) for f in items if f.lower().endswith(".pdf")]
    pdfs.sort(key=lambda p: os.path.basename(p).lower())
    return pdfs

def extract_zip_to_root(tmpdir: str, uploaded_zip, label: str):
    """
    ZIPを展開し、比較ルートを返す。
    - Macで作成したZIPの日本語ファイル名文字化けを自動修正。
    """
    zip_tmp_path = os.path.join(tmpdir, f"{label}.zip")
    with open(zip_tmp_path, "wb") as f:
        f.write(uploaded_zip.read())

    extract_dir = os.path.join(tmpdir, f"{label}_unzipped")
    os.makedirs(extract_dir, exist_ok=True)

    # --- 文字化け対策：エンコーディングを判定して再作成 ---
    with zipfile.ZipFile(zip_tmp_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            # CP437 → CP932（Windows日本語）→ UTF-8 に変換を試みる
            try:
                fixed_name = name.encode("cp437").decode("cp932")
                info.filename = fixed_name
            except Exception:
                pass  # 変換できなければそのまま
            zf.extract(info, extract_dir)

    # --- 通常のルート推定処理 ---
    top_paths = [os.path.join(extract_dir, x) for x in os.listdir(extract_dir)]
    top_files = [p for p in top_paths if os.path.isfile(p)]
    top_dirs_all = [p for p in top_paths if os.path.isdir(p)]

    top_pdfs = [p for p in top_files if p.lower().endswith(".pdf")]
    if top_pdfs:
        return extract_dir

    top_dirs = [d for d in top_dirs_all if os.path.basename(d) != "__MACOSX"]

    dirs_with_pdfs = []
    for d in top_dirs:
        files_in_d = [os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
        pdfs_in_d = [p for p in files_in_d if p.lower().endswith(".pdf")]
        if pdfs_in_d:
            dirs_with_pdfs.append(d)
    if len(dirs_with_pdfs) == 1:
        return dirs_with_pdfs[0]

    if len(top_dirs) == 1:
        return top_dirs[0]

    return extract_dir

# ====== タブ（3機能） ======
tab_single, tab_folder, tab_multi = st.tabs([
    "📄 PDF 2枚比較",
    "🗂 フォルダ比較（ZIP）",
    "📚 複数PDF 1:1 比較",
])

# === タブ1：単一PDF 2枚比較 ===
with tab_single:
    c1, c2 = st.columns(2)
    with c1:
        before_pdf = st.file_uploader("修正前（Before）PDF", type=["pdf"], key="before_single")
    with c2:
        after_pdf  = st.file_uploader("修正後（After）PDF",  type=["pdf"], key="after_single")

    if before_pdf and after_pdf and st.button("比較を開始（2枚）", key="btn_single"):
        with tempfile.TemporaryDirectory() as tmpdir:
            before_path = os.path.join(tmpdir, "before.pdf")
            after_path  = os.path.join(tmpdir, "after.pdf")
            with open(before_path, "wb") as f:
                f.write(before_pdf.read())
            with open(after_path, "wb") as f:
                f.write(after_pdf.read())

            before_name = safe_base(before_pdf.name)
            after_name  = safe_base(after_pdf.name)
            out_filename = f"{before_name}-{after_name}_diff.pdf"
            out_path = os.path.join(tmpdir, out_filename)

            st.info("🔄 差分PDFを生成中…")
            try:
                generate_diff(before_path, after_path, out_path, dpi=dpi)
                st.success("✅ 差分PDFの生成が完了しました！")
                with open(out_path, "rb") as f:
                    st.download_button(
                        "📥 差分PDFをダウンロード",
                        f.read(),
                        file_name=out_filename,
                        mime="application/pdf",
                        key="dl_single"
                    )
            except Exception as e:
                st.error(f"エラーが発生しました：{e}")
        st.stop()  # 再実行防止

# === タブ2：フォルダ比較（ZIP） ===
with tab_folder:
    c1, c2 = st.columns(2)
    with c1:
        before_zip = st.file_uploader("Before フォルダのZIP（直下PDFのみ比較）", type=["zip"], key="before_zip")
    with c2:
        after_zip  = st.file_uploader("After フォルダのZIP（直下PDFのみ比較）",  type=["zip"], key="after_zip")

    st.caption("⚠️ フォルダはZIPにしてアップロードしてください。直下PDFのみ対象・ファイル名順に1:1で比較します。")

    if before_zip and after_zip and st.button("比較を開始（ZIPフォルダ）", key="btn_zip"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                before_root = extract_zip_to_root(tmpdir, before_zip, "before")
                after_root  = extract_zip_to_root(tmpdir,  after_zip,  "after")

                before_pdfs = collect_top_level_pdfs(before_root)
                after_pdfs  = collect_top_level_pdfs(after_root)
                if not before_pdfs:
                    st.error("Before 側にPDFが見つかりませんでした（直下のみ対象）。"); st.stop()
                if not after_pdfs:
                    st.error("After 側にPDFが見つかりませんでした（直下のみ対象）。"); st.stop()

                total = min(len(before_pdfs), len(after_pdfs))
                if total == 0:
                    st.error("比較できるペアがありません。"); st.stop()

                out_mem = io.BytesIO()
                with zipfile.ZipFile(out_mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    prog = st.progress(0)
                    status = st.empty()
                    for i in range(total):
                        b = before_pdfs[i]; a = after_pdfs[i]
                        bname = safe_base(b); aname = safe_base(a)
                        out_name = f"{bname}-{aname}_diff.pdf"
                        out_tmp  = os.path.join(tmpdir, out_name)

                        status.write(f"🔄 生成中: {i+1}/{total} — {bname} vs {aname}")
                        generate_diff(b, a, out_tmp, dpi=dpi)
                        zf.write(out_tmp, arcname=out_name)
                        prog.progress(int((i + 1) / total * 100))
                status.write("✅ すべての比較が完了しました。")
                prog.progress(100)

                before_label = safe_base(before_zip.name)
                after_label  = safe_base(after_zip.name)
                date_tag = datetime.now().strftime("%Y%m%d")
                zip_name = f"{before_label}-{after_label}_diff_{date_tag}.zip"

                st.success(f"📦 {total}件の比較結果をZIPにまとめました。")
                st.download_button(
                    "📥 結果ZIPをダウンロード",
                    data=out_mem.getvalue(),
                    file_name=zip_name,
                    mime="application/zip",
                    key="dl_zip"
                )
            except Exception as e:
                st.error(f"エラーが発生しました：{e}")
        st.stop()  # 再実行防止

# === タブ3：複数PDF 1:1 比較（ZIP＋個別DL両対応） ===
with tab_multi:
    c1, c2 = st.columns(2)
    with c1:
        before_list = st.file_uploader("Before 側のPDFを複数選択", type=["pdf"], accept_multiple_files=True, key="before_multi")
    with c2:
        after_list  = st.file_uploader("After 側のPDFを複数選択",  type=["pdf"], accept_multiple_files=True, key="after_multi")

    st.caption("ファイル名順にソートし、短い側の件数に合わせて 1:1 で比較します。")

    if before_list and after_list and len(before_list) > 0 and len(after_list) > 0:
        if st.button("比較を開始（複数1:1）", key="btn_multi"):
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    # 一時保存＆ファイル名順ソート
                    def save_all(files, prefix):
                        saved = []
                        for f in files:
                            p = os.path.join(tmpdir, f"{prefix}_{f.name}")
                            with open(p, "wb") as out:
                                out.write(f.read())
                            saved.append(p)
                        saved.sort(key=lambda x: os.path.basename(x).lower())
                        return saved

                    before_paths = save_all(before_list, "b")
                    after_paths  = save_all(after_list,  "a")

                    total = min(len(before_paths), len(after_paths))
                    if total == 0:
                        st.error("比較できるペアがありません。"); st.stop()

                    results = []  # (表示名, 出力パス) のタプル
                    prog = st.progress(0)
                    status = st.empty()

                    for i in range(total):
                        b = before_paths[i]; a = after_paths[i]
                        # 表示用名（接頭辞 b_/a_ を剥がす）
                        bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                        adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])

                        out_name = f"{bdisp}-{adisp}_diff.pdf"
                        out_tmp  = os.path.join(tmpdir, out_name)

                        status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_tmp, dpi=dpi)
                        results.append((out_name, out_tmp))
                        prog.progress(int((i + 1) / total * 100))

                    status.write("✅ すべての比較が完了しました。")
                    prog.progress(100)

                    # 個別DL
                    st.subheader("📄 個別ダウンロード")
                    for name, path in results:
                        with open(path, "rb") as f:
                            st.download_button(
                                label=f"⬇️ {name}",
                                data=f.read(),
                                file_name=name,
                                mime="application/pdf",
                                key=f"dl_{name}"
                            )

                    # ZIP一括DL
                    st.subheader("💾 ZIP一括ダウンロード")
                    out_mem = io.BytesIO()
                    with zipfile.ZipFile(out_mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for name, path in results:
                            zf.write(path, arcname=name)
                    date_tag = datetime.now().strftime("%Y%m%d")
                    zip_name = f"multi_pairs_diff_{date_tag}.zip"
                    st.download_button(
                        "📥 すべてまとめてダウンロード（ZIP）",
                        data=out_mem.getvalue(),
                        file_name=zip_name,
                        mime="application/zip",
                        key="dl_multi_zip"
                    )
                except Exception as e:
                    st.error(f"エラーが発生しました：{e}")
            st.stop()  # 再実行防止

# ===== フッター =====
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
