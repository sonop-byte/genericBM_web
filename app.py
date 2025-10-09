import os, io, zipfile, tempfile, base64, unicodedata
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from pdf_diff_core_small import generate_diff

# ===== Config =====
BEFORE_LABEL_COLOR = "#990099"
AFTER_LABEL_COLOR  = "#008000"
ICON_PATH = "gBmicon.png"

# ===== Page =====
icon_img = None
if os.path.exists(ICON_PATH):
    try: icon_img = Image.open(ICON_PATH)
    except Exception: pass

st.set_page_config(page_title="genericBM – PDF差分比較ツール",
                   page_icon=icon_img if icon_img else "🩺",
                   layout="centered")

st.markdown("""
<div style='text-align:center;'>
  <img src='https://raw.githubusercontent.com/sonop-byte/genericBM_web/main/gBmicon.png'
       width='120' style='display:block;margin:auto;margin-bottom:10px;'>
  <h1 style='font-size:2.2em;margin-bottom:6px;'>genericBM – PDF差分比較ツール（Web版）</h1>
  <p style='color:gray;font-size:1.0em;'>修正前・修正後のPDFをアップロードして差分を作成します。</p>
</div>
""", unsafe_allow_html=True)

dpi = st.slider("出力PDFの解像度（dpi）", 100, 400, 200, 50,
                help="高いほど精細ですが生成時間とサイズが増えます。")

# ===== Utils =====
def safe_base(p: str) -> str:
    return unicodedata.normalize("NFC", os.path.splitext(os.path.basename(p))[0])

def save_uploaded_to(path: str, up) -> None:
    with open(path, "wb") as f: f.write(up.read())

def add_date_suffix(name: str) -> str:
    b, e = os.path.splitext(name)
    return f"{b}_{datetime.now().strftime('%Y%m%d')}{e}"

def show_pdf_inline(name: str, data: bytes):
    import fitz
    from PIL import Image as PILImage
    PREVIEW_MAX_PAGES, PREVIEW_DPI = 3, 144
    doc = fitz.open(stream=data, filetype="pdf")
    n = min(PREVIEW_MAX_PAGES, doc.page_count)
    imgs = []
    for i in range(n):
        pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(PREVIEW_DPI/72, PREVIEW_DPI/72), alpha=False)
        im = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO(); im.save(buf, format="PNG")
        imgs.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    doc.close()
    body = "".join(f"<img src='data:image/png;base64,{b64}' style='display:block;margin:12px auto;max-width:100%;height:auto;'/>" for b64 in imgs)
    html = f"""
    <div style="max-width:1500px;margin:0 auto;border:1px solid #ddd;border-radius:8px;padding:8px 12px;">
      <div style="font-weight:600;margin-bottom:6px;">👁 プレビュー：{name}</div>
      {body or '<div style="padding:10px;">プレビューできるページがありません。</div>'}
    </div>"""
    h = min(1200, 260 * max(1, n) + 80)
    components.html(html, height=h, scrolling=True)

# ===== State =====
st.session_state.setdefault("results_two", [])
st.session_state.setdefault("results_three", [])
st.session_state.setdefault("preview_file", None)
st.session_state.setdefault("run_two", False)
st.session_state.setdefault("run_three", False)

# ===== Tabs =====
tab_two, tab_three = st.tabs(["📄 2ファイル比較（1:1固定）", "📚 3ファイル比較（1対2）"])

# --- Tab: 2-file (1:1, ignore extras)
with tab_two:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="color:{BEFORE_LABEL_COLOR};font-weight:600;">Before 側PDF（複数可）</div>', unsafe_allow_html=True)
        before_files = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="before_two", label_visibility="collapsed")
    with c2:
        st.markdown(f'<div style="color:{AFTER_LABEL_COLOR};font-weight:600;">After 側PDF（複数可）</div>', unsafe_allow_html=True)
        after_files  = st.file_uploader("", type=["pdf"], accept_multiple_files=True, key="after_two", label_visibility="collapsed")

    if before_files and after_files and st.button("比較を開始（1:1）", key="btn_two"):
        st.session_state["run_two"] = True

    if st.session_state["run_two"]:
        st.session_state["results_two"].clear()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                b_paths = []
                for f in before_files:
                    p = os.path.join(tmp, f"b_{f.name}"); save_uploaded_to(p, f); b_paths.append(p)
                a_paths = []
                for f in after_files:
                    p = os.path.join(tmp, f"a_{f.name}"); save_uploaded_to(p, f); a_paths.append(p)
                b_paths.sort(key=lambda p: os.path.basename(p).lower())
                a_paths.sort(key=lambda p: os.path.basename(p).lower())

                total = min(len(b_paths), len(a_paths))
                if total == 0:
                    st.info("比較対象がありません。")
                else:
                    prog, status = st.progress(0), st.empty()
                    for i in range(total):
                        b, a = b_paths[i], a_paths[i]
                        bdisp, adisp = safe_base(b.split("b_",1)[-1]), safe_base(a.split("a_",1)[-1])
                        out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                        out_path = os.path.join(tmp, out_name)
                        status.write(f"🔄 生成中: {i+1}/{total} — {bdisp} vs {adisp}")
                        generate_diff(b, a, out_path, dpi=dpi)
                        with open(out_path, "rb") as fr:
                            st.session_state["results_two"].append((out_name, fr.read()))
                        prog.progress(int((i+1)/total*100))
                    status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state["run_two"] = False

    if st.session_state["results_two"]:
        st.subheader("📄 生成済み差分PDF"); st.caption("クリックでプレビュー表示")
        for name, data in st.session_state["results_two"]:
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👁 {name}", key=f"pv2_{name}"):
                    st.session_state["preview_file"] = (name, data)
            with c2:
                st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=f"dl2_{name}")

        st.subheader("💾 ZIP一括ダウンロード")
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state["results_two"]:
                zf.writestr(name, data)
        st.download_button("📥 ZIP一括DL", mem.getvalue(),
                           file_name=f"genericBM_1to1_{datetime.now().strftime('%Y%m%d')}.zip",
                           mime="application/zip")

# --- Tab: 3-file (1 vs 2)
with tab_three:
    before_file = st.file_uploader("Before 側PDF（1つ）", type=["pdf"], key="b3")
    after_files  = st.file_uploader("After 側PDF（2つ）", type=["pdf"], accept_multiple_files=True, key="a3")

    if before_file and after_files and len(after_files) == 2 and st.button("比較を開始（1対2）", key="btn_three"):
        st.session_state["run_three"] = True

    if st.session_state["run_three"]:
        st.session_state["results_three"].clear()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                b_path = os.path.join(tmp, "before.pdf"); save_uploaded_to(b_path, before_file)
                bdisp  = safe_base(before_file.name)
                prog, status = st.progress(0), st.empty()
                for i, af in enumerate(after_files, start=1):
                    a_path = os.path.join(tmp, f"after_{i}.pdf"); save_uploaded_to(a_path, af)
                    adisp  = safe_base(af.name)
                    out_name = add_date_suffix(f"{bdisp}vs{adisp}.pdf")
                    out_tmp  = os.path.join(tmp, out_name)
                    status.write(f"🔄 生成中: {i}/2 — {bdisp} vs {adisp}")
                    generate_diff(b_path, a_path, out_tmp, dpi=dpi)
                    with open(out_tmp, "rb") as fr:
                        st.session_state["results_three"].append((out_name, fr.read()))
                    prog.progress(int(i/2*100))
                status.write("✅ 比較が完了しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
        st.session_state["run_three"] = False

    if st.session_state["results_three"]:
        st.subheader("📄 生成済み差分PDF"); st.caption("クリックでプレビュー表示")
        for name, data in st.session_state["results_three"]:
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👁 {name}", key=f"pv3_{name}"):
                    st.session_state["preview_file"] = (name, data)
            with c2:
                st.download_button("⬇️ DL", data=data, file_name=name, mime="application/pdf", key=f"dl3_{name}")

        st.subheader("💾 ZIP一括ダウンロード")
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in st.session_state["results_three"]:
                zf.writestr(name, data)
        st.download_button("📥 ZIP一括DL", mem.getvalue(),
                           file_name=f"genericBM_1to2_{datetime.now().strftime('%Y%m%d')}.zip",
                           mime="application/zip")

# --- Preview (bottom)
if st.session_state["preview_file"]:
    name, data = st.session_state["preview_file"]
    st.markdown("---")
    show_pdf_inline(name, data)

# --- Footer
st.markdown("---")
st.markdown(
    "<div style='text-align:center;font-size:0.85em;color:gray;'>© genericBM (OpenAI + mmMIG)</div>",
    unsafe_allow_html=True
)
