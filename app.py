# app.py — Streamlit版 genericBM（中央ロゴ見出し・3機能統合・mmMIG表記）
import os
import io
import zipfile
import tempfile
from datetime import datetime

import streamlit as st
from pdf_diff_core_small import generate_diff

# ---------- ページ設定 ----------
st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon="gBmicon.png",   # リポジトリ直下に gBmicon.png を置く
    layout="centered",
)

# ---------- ヘッダー（中央寄せ：ロゴ + タイトル + 説明） ----------
st.markdown(
    """
    <div style='text-align:center;'>
        <img src='gBmicon.png' width='120' style='margin-bottom:10px;'>
        <h1 style='font-size:2.2em; margin-bottom:4px;'>genericBM – PDF差分比較ツール（Web版）</h1>
        <p style='color:gray; font-size:1.0em; margin-top:0;'>
            修正前・修正後のPDF（またはフォルダZIP）をアップロードして差分を作成します。
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

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

# ====== タブ1：PDF 2枚比較 ======
with tab_single:
    c1, c2 = st.columns(2)
    with c1:
        before_pdf = st.file_uploader("修正前（Before）PDF", type=["pdf"], key="before_single")
    with c2:
        after_pdf  = st.file_uploader("修正後（After）PDF", type=["pdf"], key="after_single")

    if before_pdf and after_pdf:
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
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"エラーが発生しました：{e}")
    else:
        st.caption("※ 2つのPDFを選択してください。")

# ====== タブ2：フォルダ比較（ZIP） ======
with tab_folder:
    c1, c2 = st.columns(2)
    with c1:
        before_zip = st.file_uploader("Before フォルダのZIP（直下PDFのみ比較）", type=["zip"], key="before_zip")
    with c2:
        after_zip  = st.file_uploader("After フォルダのZIP（直下PDFのみ比較）",  type=["zip"], key="after_zip")

    st.caption("⚠️ フォルダはZIPにしてアップロードしてください。直下PDFのみ対象・ファイル名順に1:1で比較します。")

    if before_zip and after_zip:
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
                    mime="application/zip"
                )
            except Exception as e:
                st.error(f"エラーが発生しました：{e}")

# ====== タブ3：複数PDF 1:1 比較 ======
with tab_multi:
    c1, c2 = st.columns(2)
    with c1:
        before_list = st.file_uploader("Before 側のPDFを複数選択", type=["pdf"], accept_multiple_files=True, key="before_multi")
    with c2:
        after_list  = st.file_uploader("After 側のPDFを複数選択",  type=["pdf"], accept_multiple_files=True, key="after_multi")

    st.caption("ファイル名順にソートし、短い側の件数に合わせて 1:1 で比較します。")

    if before_list and after_list:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # 一時保存 & ファイル名順ソート
                def save_all(files, label):
                    saved = []
                    for f in files:
                        # 衝突回避のため接頭辞を付けて保存
                        p = os.path.join(tmpdir, f"{label}_{f.name}")
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

                out_mem = io.BytesIO()
                with zipfile.ZipFile(out_mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    prog = st.progress(0)
                    status = st.empty()
                    for i in range(total):
                        b = before_paths[i]; a = after_paths[i]
                        # 表示・ファイル名用に接頭辞を剥がす
                        bdisp = safe_base(os.path.basename(b).split("b_", 1)[-1])
                        adisp = safe_base(os.path.basename(a).split("a_", 1)[-1])

                        out_name = f"{bdisp}-{adisp}_diff.pdf"
                        out_tmp  = os.path.join(tmpdir, out_name)

                        status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_tmp, dpi=dpi)
                        zf.write(out_tmp, arcname=out_name)
                        prog.progress(int((i + 1) / total * 100))
                status.write("✅ すべての比較が完了しました。")
                prog.progress(100)

                date_tag = datetime.now().strftime("%Y%m%d")
                zip_name = f"multi_pairs_diff_{date_tag}.zip"
                st.success(f"📦 {total}件の比較結果をZIPにまとめました。")
                st.download_button(
                    "📥 結果ZIPをダウンロード",
                    data=out_mem.getvalue(),
                    file_name=zip_name,
                    mime="application/zip"
                )
            except Exception as e:
                st.error(f"エラーが発生しました：{e}")
    else:
        st.caption("※ Before 側と After 側で、それぞれ複数PDFを選択してください。")

# ---------- フッター ----------
st.markdown("---")
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "© genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
