# app.py  — Streamlit版 genericBM（mmMIG 表記・自動ファイル名対応）
import os
import tempfile
import streamlit as st
from pdf_diff_core_small import generate_diff

st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon="🩺",
    layout="centered"
)

st.title("🩺 genericBM – PDF差分比較ツール（Web版）")
st.caption("修正前・修正後のPDFをアップロードして、差分を視覚的に確認できます。")

# アップローダ
col1, col2 = st.columns(2)
with col1:
    before = st.file_uploader("📄 修正前（Before）PDF", type=["pdf"], key="before")
with col2:
    after = st.file_uploader("📄 修正後（After）PDF", type=["pdf"], key="after")

# オプション（必要なら調整）
with st.expander("詳細設定", expanded=False):
    dpi = st.slider("出力PDFの解像度（dpi）", min_value=100, max_value=400, value=200, step=50)
    st.caption("数値が高いほど精細になりますが、生成時間と出力サイズが増えます。")

# 実行
if before and after:
    # 一時ディレクトリを使って安全に保存
    with tempfile.TemporaryDirectory() as tmpdir:
        # 元ファイル名（拡張子除去）
        before_name = os.path.splitext(os.path.basename(before.name))[0]
        after_name  = os.path.splitext(os.path.basename(after.name))[0]

        before_path = os.path.join(tmpdir, "before.pdf")
        after_path  = os.path.join(tmpdir, "after.pdf")

        # 入力を保存
        with open(before_path, "wb") as f:
            f.write(before.read())
        with open(after_path, "wb") as f:
            f.write(after.read())

        # 出力ファイル名：<before>-<after>_diff.pdf
        out_filename = f"{before_name}-{after_name}_diff.pdf"
        out_path = os.path.join(tmpdir, out_filename)

        st.info("🔄 差分PDFを生成中... 少しお待ちください。")
        try:
            generate_diff(before_path, after_path, out_path, dpi=dpi)
            st.success("✅ 差分PDFの生成が完了しました！")

            # ダウンロードボタン：自動生成名をそのまま使用
            with open(out_path, "rb") as f:
                st.download_button(
                    label="📥 差分PDFをダウンロード",
                    data=f.read(),
                    file_name=out_filename,
                    mime="application/pdf",
                )
        except Exception as e:
            st.error(f"エラーが発生しました：{e}")
else:
    st.warning("⚠️ 修正前・修正後のPDFを両方アップロードしてください。")

st.markdown("---")
# ▼ フッター表記を mmMIG に変更
st.markdown(
    "<div style='text-align:center; font-size:0.85em; color:gray;'>"
    "genericBM (OpenAI + mmMIG)"
    "</div>",
    unsafe_allow_html=True
)
