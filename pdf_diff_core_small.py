# app.py — genericBM（UI復元版・B案コア呼び出し）
# 見た目（文言・色・タブ名）をスクショ当時に戻しつつ、内部は generate_diff_bytes を使用

import io, zipfile
from datetime import datetime
import streamlit as st
import fitz

st.set_page_config(page_title="genericBM – PDF差分比較ツール（Web版）", layout="wide")

# ====== Header / Logo ======
# 手元にロゴがあれば ./assets/logo_gbm.png などに置いてください。無ければ自動スキップ。
logo_paths = ["./assets/logo_gbm.png", "./logo_gbm.png", "./assets/logo.png", "./logo.png"]
for _p in logo_paths:
    try:
        import os
        if os.path.exists(_p):
            st.image(_p, width=88)
            break
    except Exception:
        pass

st.title("genericBM – PDF差分比較ツール（Web版）")
st.caption("修正前・修正後のPDF（またはフォルダZIP）をアップロードして差分を作成します。")

# ====== Styles ======
st.markdown("""
<style>
.label-before { font-weight:700; color:#990099; margin:16px 0 6px 0; }
.label-after  { font-weight:700; color:#008000; margin:16px 0 6px 0; }
.footer       { color:#6b7280; font-size:0.9rem; margin-top:24px; text-align:center; }
.preview-wrap { max-width:1500px; margin:0 auto; }
hr { margin: 1rem 0; }
</style>
""", unsafe_allow_html=True)

# ====== 詳細設定（スクショ準拠：折りたたみ） ======
with st.expander("詳細設定", expanded=False):
    dpi = st.slider("DPI（出力解像度）", 72, 600, 200, 10)
# 既定値（エクスパンダ閉時）は200
if "dpi" not in locals():
    dpi = 200

today_tag = datetime.now().strftime("%Y%m%d")

# ====== Tabs（スクショ準拠の文言） ======
tab1, tab_zip, tab3 = st.tabs(["🧾 PDF 2枚比較", "📦 フォルダ比較（ZIP）", "📚 複数PDF 1:1 比較"])

def _previews_from_pdf_bytes(pdf_bytes: bytes):
    imgs = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as d:
        for i in range(d.page_count):
            pix = d.load_page(i).get_pixmap()
            imgs.append(pix.tobytes("png"))
    return imgs

# -------------------------------
# 🧾 PDF 2枚比較（スクショの文言）
# -------------------------------
with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="label-before">修正前（Before） PDF</div>', unsafe_allow_html=True)
        before = st.file_uploader("Before を選択", type=["pdf"], key="t1_before")

    with c2:
        st.markdown('<div class="label-after">修正後（After） PDF</div>', unsafe_allow_html=True)
        after = st.file_uploader("After を選択", type=["pdf"], key="t1_after")

    st.caption("※ 2つのPDFを選択してください。")

    run_2 = st.button("差分を実行（2ファイル）", type="primary", use_container_width=True)

    if run_2 and before and after:
        with st.spinner("差分生成中…"):
            diff_pdf = generate_diff_bytes(before.read(), after.read(), dpi=dpi, whiten=0, page_mode="min")
            previews = _previews_from_pdf_bytes(diff_pdf)

        st.markdown("#### プレビュー（幅1500px内）")
        st.markdown('<div class="preview-wrap">', unsafe_allow_html=True)
        for png in previews:
            st.image(png, use_column_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("#### ダウンロード")
        st.download_button(
            "個別DL：BeforevsAfter_diff.pdf",
            data=diff_pdf,
            file_name=f"BeforevsAfter_{today_tag}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    st.markdown('<div class="footer">© genericBM (OpenAI + mmMIG)</div>', unsafe_allow_html=True)

# -------------------------------
# 📦 フォルダ比較（ZIP）※見た目だけ復元（機能は未変更）
# -------------------------------
with tab_zip:
    st.info("このタブは見た目の復元のみ行っています（処理は未実装/据え置き）。必要になったら実装を入れます。")
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="label-before">修正前（Before） フォルダZIP</div>', unsafe_allow_html=True)
        st.file_uploader("Before（ZIP）を選択", type=["zip"], key="zip_before")
    with right:
        st.markdown('<div class="label-after">修正後（After） フォルダZIP</div>', unsafe_allow_html=True)
        st.file_uploader("After（ZIP）を選択", type=["zip"], key="zip_after")

    st.markdown('<div class="footer">© genericBM (OpenAI + mmMIG)</div>', unsafe_allow_html=True)

# -------------------------------
# 📚 複数PDF 1:1 比較（= Before1 vs After2 の機能そのまま）
# -------------------------------
with tab3:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="label-before">修正前（Before1） PDF</div>', unsafe_allow_html=True)
        before1 = st.file_uploader("Before1 を選択", type=["pdf"], key="t3_before1")
    with c2:
        st.markdown('<div class="label-after">修正後（After1） PDF</div>', unsafe_allow_html=True)
        after1 = st.file_uploader("After1 を選択", type=["pdf"], key="t3_after1")

    st.markdown('<div class="label-after">修正後（After2） PDF</div>', unsafe_allow_html=True)
    after2 = st.file_uploader("After2 を選択", type=["pdf"], key="t3_after2")

    run_3 = st.button("差分を実行（複数PDF 1:1）", type="primary", use_container_width=True)

    if run_3 and before1 and after1 and after2:
        with st.spinner("差分生成中…"):
            # Before1 vs After1、Before1 vs After2 をそれぞれ作る（従来機能）
            pdf_b1_a1 = generate_diff_bytes(before1.read(), after1.read(), dpi=dpi, whiten=0, page_mode="min")
            pdf_b1_a2 = generate_diff_bytes(before1.read(), after2.read(), dpi=dpi, whiten=0, page_mode="min")
            previews = _previews_from_pdf_bytes(pdf_b1_a1) + _previews_from_pdf_bytes(pdf_b1_a2)

        st.markdown("#### プレビュー（幅1500px内）")
        st.markdown('<div class="preview-wrap">', unsafe_allow_html=True)
        for png in previews:
            st.image(png, use_column_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("#### ダウンロード")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.download_button(
                "B1_vs_A1_diff.pdf をDL",
                data=pdf_b1_a1,
                file_name=f"B1_vs_A1_{today_tag}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        with col_a2:
            st.download_button(
                "B1_vs_A2_diff.pdf をDL",
                data=pdf_b1_a2,
                file_name=f"B1_vs_A2_{today_tag}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        # ZIP一括（従来どおり）
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"B1_vs_A1_{today_tag}.pdf", pdf_b1_a1)
            zf.writestr(f"B1_vs_A2_{today_tag}.pdf", pdf_b1_a2)
        zip_buf.seek(0)
        st.download_button(
            "ZIP一括DL：B1vsA1A2.zip",
            data=zip_buf,
            file_name=f"B1vsA1A2_{today_tag}.zip",
            mime="application/zip",
            use_container_width=True
        )

    st.markdown('<div class="footer">© genericBM (OpenAI + mmMIG)</div>', unsafe_allow_html=True)
