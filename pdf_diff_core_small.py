# pdf_diff_core_small.py
import io
from typing import Optional, Tuple
import fitz
from PIL import Image, ImageChops, ImageOps

def _render_page_to_rgb(
    page: Optional[fitz.Page],
    dpi: int,
    target_px: Optional[Tuple[int, int]] = None
) -> Image.Image:
    """
    PDFのページをRGB画像へレンダリング。
    target_pxが指定されれば、その最大内接サイズに収めて白キャンバスへ配置。
    """
    if page is None:
        # 呼び出し側で target_px を用意している想定
        if target_px is None:
            # フォールバック（A4相当 72dpi）: 595x842pt -> 200dpi換算など本来は必要だが、
            # 呼び出し側が target_px を与える前提なので最小限に。
            return Image.new("RGB", (1200, 1700), (255, 255, 255))
        return Image.new("RGB", target_px, (255, 255, 255))

    rect = page.rect
    if target_px is None:
        # DPIスケールでそのままレンダリング
        zoom = dpi / 72.0
        pix = page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            colorspace=fitz.csRGB,
            alpha=False
        )
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # 指定ピクセルに収まるようにレンダリングして白キャンバスへ
    target_w, target_h = target_px
    scale = max(target_w / rect.width, target_h / rect.height)
    zoom = max(scale, 1.0)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom),
        colorspace=fitz.csRGB,
        alpha=False
    )
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = ImageOps.contain(img, (target_w, target_h))
    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    canvas.paste(img, ((target_w - img.width) // 2, (target_h - img.height) // 2))
    return canvas

def _size_in_px(rect: fitz.Rect, dpi: int) -> Tuple[int, int]:
    return (int(round(rect.width * dpi / 72.0)), int(round(rect.height * dpi / 72.0)))

def _colorize_with_brightness(
    rgb_image: Image.Image,
    target_color: Tuple[int, int, int],
    whiten: Optional[int] = None
) -> Image.Image:
    """
    グレースケールの明度を保持しつつ、指定色へトーンマッピング。
    whiten を設定するとその閾値以上の明部を白飛びさせる（背景の色付きを抑える用途）。
    """
    gray = rgb_image.convert("L")
    if whiten and whiten > 0:
        gray = gray.point(lambda v: 255 if v >= whiten else v, mode="L")

    w, h = rgb_image.size
    out = Image.new("RGB", (w, h))
    tr, tg, tb = target_color
    gpx, opx = gray.load(), out.load()

    for y in range(h):
        for x in range(w):
            v = gpx[x, y]  # 0..255
            # v が暗いほど target_color に近く、明るいほど白に近づける
            opx[x, y] = (
                int(tr + (255 - tr) * (v / 255.0)),
                int(tg + (255 - tg) * (v / 255.0)),
                int(tb + (255 - tb) * (v / 255.0)),
            )
    return out

def _encode_jpeg_bytes(img: Image.Image, quality: int = 70, subsampling: int = 2) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=subsampling, optimize=True)
    return buf.getvalue()

def generate_diff(
    before_pdf: str,
    after_pdf: str,
    out_pdf: str,
    dpi: int = 200,
    whiten: int = 0,
    page_mode: str = "min",
) -> None:
    """
    ファイルパスを受け取り、差分結果PDFを out_pdf へ保存（従来API）。
    合成色は Before:#990099 / After:#008000（= (153,0,153) / (0,128,0) ）。
    """
    doc_b = fitz.open(before_pdf)
    doc_a = fitz.open(after_pdf)
    n_b, n_a = doc_b.page_count, doc_a.page_count
    n = min(n_b, n_a) if page_mode == "min" else max(n_b, n_a)
    if n == 0:
        doc_b.close()
        doc_a.close()
        raise RuntimeError("ページがありません。")

    out = fitz.open()
    try:
        for i in range(n):
            page_b = doc_b.load_page(i) if i < n_b else None
            page_a = doc_a.load_page(i) if i < n_a else None
            base_rect = (page_b or page_a).rect
            target_px = _size_in_px(base_rect, dpi)

            img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=None) if page_b else Image.new("RGB", target_px, (255, 255, 255))
            if img_b.size != target_px:
                img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=target_px)

            img_a = _render_page_to_rgb(page_a, dpi=dpi, target_px=target_px) if page_a else Image.new("RGB", target_px, (255, 255, 255))

            # 色は厳密に #990099 / #008000
            col_b = _colorize_with_brightness(img_b, (153, 0, 153), whiten=whiten)
            col_a = _colorize_with_brightness(img_a, (0, 128, 0),   whiten=whiten)
            diff_img = ImageChops.multiply(col_b, col_a)

            w_px, h_px = diff_img.size
            w_pt, h_pt = w_px * 72.0 / dpi, h_px * 72.0 / dpi
            jpeg_bytes = _encode_jpeg_bytes(diff_img, quality=70, subsampling=2)

            page = out.new_page(width=w_pt, height=h_pt)
            page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=jpeg_bytes, keep_proportion=False)

        out.save(out_pdf, deflate=True)
    finally:
        out.close()
        doc_b.close()
        doc_a.close()

def generate_diff_bytes(
    before_pdf_bytes: bytes,
    after_pdf_bytes: bytes,
    dpi: int = 200,
    whiten: int = 0,
    page_mode: str = "min",
) -> bytes:
    """
    PDFバイト列を受け取り、差分結果PDFのバイト列を返す新API（Streamlit向け）。
    合成色は Before:#990099 / After:#008000。
    """
    doc_b = fitz.open(stream=before_pdf_bytes, filetype="pdf")
    doc_a = fitz.open(stream=after_pdf_bytes, filetype="pdf")
    n_b, n_a = doc_b.page_count, doc_a.page_count
    n = min(n_b, n_a) if page_mode == "min" else max(n_b, n_a)
    if n == 0:
        doc_b.close()
        doc_a.close()
        raise RuntimeError("ページがありません。")

    out = fitz.open()
    try:
        for i in range(n):
            page_b = doc_b.load_page(i) if i < n_b else None
            page_a = doc_a.load_page(i) if i < n_a else None
            base_rect = (page_b or page_a).rect
            target_px = _size_in_px(base_rect, dpi)

            img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=None) if page_b else Image.new("RGB", target_px, (255, 255, 255))
            if img_b.size != target_px:
                img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=target_px)

            img_a = _render_page_to_rgb(page_a, dpi=dpi, target_px=target_px) if page_a else Image.new("RGB", target_px, (255, 255, 255))

            col_b = _colorize_with_brightness(img_b, (153, 0, 153), whiten=whiten)  # #990099
            col_a = _colorize_with_brightness(img_a, (0, 128, 0),   whiten=whiten)  # #008000
            diff_img = ImageChops.multiply(col_b, col_a)

            w_px, h_px = diff_img.size
            w_pt, h_pt = w_px * 72.0 / dpi, h_px * 72.0 / dpi
            jpeg_bytes = _encode_jpeg_bytes(diff_img, quality=70, subsampling=2)

            page = out.new_page(width=w_pt, height=h_pt)
            page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=jpeg_bytes, keep_proportion=False)

        return out.tobytes(deflate=True)
    finally:
        out.close()
        doc_b.close()
        doc_a.close()

if __name__ == "__main__":
    import argparse, os
    p = argparse.ArgumentParser()
    p.add_argument("-b", "--before", required=True)
    p.add_argument("-a", "--after", required=True)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--whiten", type=int, default=0)
    p.add_argument("--page-mode", default="min")
    args = p.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    generate_diff(
        args.before, args.after, args.out,
        dpi=args.dpi, whiten=args.whiten, page_mode=args.page_mode
    )
    print(f"Done: {os.path.abspath(args.out)}")
