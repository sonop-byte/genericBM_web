import io, zipfile
from datetime import datetime
import streamlit as st
import fitz
from pdf_diff_core_small import generate_diff_bytes

st.set_page_config(page_title="genericBM Web", layout="wide")

# ====== Style ======
st.markdown("""
<style>
.label-before { font-weight:700; color:#990099; margin:0 0 4px 0; }
.label-after { font-weight:700; color:#008000; margin:16px 0 4px 0; }
.footer { color:#6b7280; font-size:0.9rem; margin-top:12px; text-align:center; }
.preview-wrap { max-width:1500px; margin:0 auto; }
</style>
""", unsafe_allow_html=True)

st.title("genericBM Web")
st.caption("PDF差分ツール｜2ファイル比較 / 3ファイル比較｜DPI変更 / プレビュー / 個別DL / ZIP一括DL")

dpi = st.slider("DPI（出力解像度）", 72, 600, 200, 10)
today_tag = datetime.now().strftime("%Y%m%d")

tab1, tab2 = st.tabs(["📄 2ファイル比較（1:1）", "📚 3ファイル比較（Before1 vs After2）"])

def _previews_from_pdf_bytes(pdf_bytes: bytes):
    imgs = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as d:
        for i in range(d.page_count):
            pix = d.load_page(i).get_pixmap()
            imgs.append(pix.tobytes("png"))
    return imgs

# ===== 2ファイル比較 =====
with tab1:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="label-before">Before（旧版）</div>', unsafe_allow_html=True)
        before = st.file_uploader("Before を選択", type=["pdf"], key="t1_before")
    with c2:
        st.markdown('<div class="label-after">After（新版）</div>', unsafe_allow_html=True)
        after = st.file_uploader("After を選択", type=["pdf"], key="t1_after")

    if st.button("差分を実行（2ファイル）", type="primary", use_container_width=True) and before and after:
        with st.spinner("差分生成中…"):
            diff_pdf = generate_diff_bytes(before.read(), after.read(), dpi=dpi, whiten=0, page_mode="min")
            previews = _previews_from_pdf_bytes(diff_pdf)

        st.markdown("#### プレビュー")
        for png in previews:
            st.image(png, use_column_width=True)

        st.download_button(
            "個別DL：BeforevsAfter_diff.pdf",
            data=diff_pdf,
            file_name=f"BeforevsAfter_{today_tag}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    st.markdown('<div class="footer">© genericBM (OpenAI + mmMIG)</div>', unsafe_allow_html=True)

# ===== 3ファイル比較 =====
with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="label-before">Before1（旧版）</div>', unsafe_allow_html=True)
        before1 = st.file_uploader("Before1 を選択", type=["pdf"], key="t2_before1")
    with c2:
        st.markdown('<div class="label-after">After1（新版A）</div>', unsafe_allow_html=True)
        after1 = st.file_uploader("After1 を選択", type=["pdf"], key="t2_after1")

    st.markdown('<div class="label-after">After2（新版B）</div>', unsafe_allow_html=True)
    after2 = st.file_uploader("After2 を選択", type=["pdf"], key="t2_after2")

    if st.button("差分を実行（3ファイル：Before1 vs After2）", type="primary", use_container_width=True) and before1 and after1 and after2:
        with st.spinner("差分生成中…"):
            pdf_b1_a1 = generate_diff_bytes(before1.read(), after1.read(), dpi=dpi, whiten=0, page_mode="min")
            pdf_b1_a2 = generate_diff_bytes(before1.read(), after2.read(), dpi=dpi, whiten=0, page_mode="min")
            previews = _previews_from_pdf_bytes(pdf_b1_a1) + _previews_from_pdf_bytes(pdf_b1_a2)

        st.markdown("#### プレビュー")
        for png in previews:
            st.image(png, use_column_width=True)

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
