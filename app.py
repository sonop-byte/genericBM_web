import streamlit as st
import os
from pdf_diff_core_small import generate_diff

st.set_page_config(
    page_title="genericBM – PDF差分比較ツール",
    page_icon="🩺",
    layout="centered"
)

st.title("🩺 genericBM – PDF差分比較ツール")
st.caption("修正前・修正後のPDFをアップロードして、差分を視覚的に確認できます。")

# ファイルアップロード欄
before = st.file_uploader("📄 修正前（Before）PDF を選択", type=["pdf"])
after = st.file_uploader("📄 修正後（After）PDF を選択", type=["pdf"])

# DPI設定オプション（高度な設定）
dpi = st.slider("出力PDFの解像度（dpi）", min_value=100, max_value=400, value=200, step=50)

# 実行ボタン
if before and after:
    st.info("🔄 差分PDFを生成中... 少しお待ちください。")
    with open("before.pdf", "wb") as f:
        f.write(before.read())
    with open("after.pdf", "wb") as f:
        f.write(after.read())

    out_path = "diff.pdf"
    try:
        generate_diff("before.pdf", "after.pdf", out_path, dpi=dpi)
        st.success("✅ 差分PDFの生成が完了しました！")
        with open(out_path, "rb") as f:
            st.download_button(
                label="📥 差分PDFをダウンロード",
                data=f,
                file_name="diff.pdf",
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
else:
    st.warning("⚠️ 修正前・修正後のPDFを両方アップロードしてください。")

st.markdown("---")
st.caption("© genericBM (OpenAI + 医学書院 開発チーム用テスト)")
