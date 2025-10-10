import io
from typing import Optional, Tuple
import fitz
from PIL import Image, ImageChops, ImageOps

def _render_page_to_rgb(page: fitz.Page, dpi: int, target_px: Optional[Tuple[int,int]]=None) -> Image.Image:
    rect = page.rect
    if target_px is None:
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    target_w, target_h = target_px
    scale = max(target_w/rect.width, target_h/rect.height)
    zoom = max(scale, 1.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = ImageOps.contain(img, (target_w, target_h))
    canvas = Image.new("RGB", (target_w, target_h), (255,255,255))
    canvas.paste(img, ((target_w-img.width)//2, (target_h-img.height)//2))
    return canvas

def _size_in_px(rect: fitz.Rect, dpi: int) -> Tuple[int,int]:
    return (int(round(rect.width*dpi/72.0)), int(round(rect.height*dpi/72.0)))

def _colorize_with_brightness(rgb_image: Image.Image, target_color: Tuple[int,int,int], whiten: Optional[int]=None) -> Image.Image:
    gray = rgb_image.convert("L")
    if whiten and whiten > 0:
        gray = gray.point(lambda v: 255 if v >= whiten else v, mode="L")
    w, h = rgb_image.size
    out = Image.new("RGB", (w, h))
    tr, tg, tb = target_color
    gpx, opx = gray.load(), out.load()
    for y in range(h):
        for x in range(w):
            v = gpx[x, y]
            opx[x, y] = (
                int(tr + (255 - tr) * (v/255.0)),
                int(tg + (255 - tg) * (v/255.0)),
                int(tb + (255 - tb) * (v/255.0)),
            )
    return out

def _encode_jpeg_bytes(img: Image.Image, quality: int = 70, subsampling: int = 2) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=subsampling, optimize=True)
    return buf.getvalue()

def generate_diff(before_pdf: str, after_pdf: str, out_pdf: str, dpi: int = 200, whiten: int = 0, page_mode: str = "min") -> None:
    doc_b = fitz.open(before_pdf)
    doc_a = fitz.open(after_pdf)
    n_b, n_a = doc_b.page_count, doc_a.page_count
    n = min(n_b, n_a) if page_mode == "min" else max(n_b, n_a)
    if n == 0:
        raise RuntimeError("ページがありません。")

    out = fitz.open()
    try:
        for i in range(n):
            page_b = doc_b.load_page(i) if i < n_b else None
            page_a = doc_a.load_page(i) if i < n_a else None
            base_rect = (page_b or page_a).rect
            target_px = _size_in_px(base_rect, dpi)

            img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=None) if page_b else Image.new("RGB", target_px, (255,255,255))
            if img_b.size != target_px:
                img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=target_px)
            img_a = _render_page_to_rgb(page_a, dpi=dpi, target_px=target_px) if page_a else Image.new("RGB", target_px, (255,255,255))

            col_b = _colorize_with_brightness(img_b, (153,0,153), whiten=whiten)   # #990099
            col_a = _colorize_with_brightness(img_a, (0,128,0),   whiten=whiten)   # #008000
            diff_img = ImageChops.multiply(col_b, col_a)

            w_px, h_px = diff_img.size
            w_pt, h_pt = w_px*72.0/dpi, h_px*72.0/dpi
            jpeg_bytes = _encode_jpeg_bytes(diff_img, quality=70, subsampling=2)
            page = out.new_page(width=w_pt, height=h_pt)
            page.insert_image(fitz.Rect(0,0,w_pt,h_pt), stream=jpeg_bytes, keep_proportion=False)

        out.save(out_pdf, deflate=True)
    finally:
        out.close()
        doc_b.close()
        doc_a.close()

def generate_diff_bytes(before_pdf_bytes: bytes, after_pdf_bytes: bytes, dpi: int = 200, whiten: int = 0, page_mode: str = "min") -> bytes:
    """PDFバイト列から差分PDFのバイト列を返す軽量ラッパー"""
    doc_b = fitz.open(stream=before_pdf_bytes, filetype="pdf")
    doc_a = fitz.open(stream=after_pdf_bytes, filetype="pdf")
    n_b, n_a = doc_b.page_count, doc_a.page_count
    n = min(n_b, n_a) if page_mode == "min" else max(n_b, n_a)
    if n == 0:
        doc_b.close(); doc_a.close()
        raise RuntimeError("ページがありません。")

    out = fitz.open()
    try:
        for i in range(n):
            page_b = doc_b.load_page(i) if i < n_b else None
            page_a = doc_a.load_page(i) if i < n_a else None
            base_rect = (page_b or page_a).rect
            target_px = _size_in_px(base_rect, dpi)

            img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=None) if page_b else Image.new("RGB", target_px, (255,255,255))
            if img_b.size != target_px:
                img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=target_px)
            img_a = _render_page_to_rgb(page_a, dpi=dpi, target_px=target_px) if page_a else Image.new("RGB", target_px, (255,255,255))

            col_b = _colorize_with_brightness(img_b, (153,0,153), whiten=whiten)
            col_a = _colorize_with_brightness(img_a, (0,128,0),   whiten=whiten)
            diff_img = ImageChops.multiply(col_b, col_a)

            w_px, h_px = diff_img.size
            w_pt, h_pt = w_px*72.0/dpi, h_px*72.0/dpi
            jpeg_bytes = _encode_jpeg_bytes(diff_img, quality=70, subsampling=2)
            page = out.new_page(width=w_pt, height=h_pt)
            page.insert_image(fitz.Rect(0,0,w_pt,h_pt), stream=jpeg_bytes, keep_proportion=False)

        return out.tobytes(deflate=True)
    finally:
        out.close()
        doc_b.close()
        doc_a.close()
