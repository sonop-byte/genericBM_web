import io, os
from typing import List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image, ImageChops, ImageOps

def _render_page_to_rgb(page: fitz.Page, dpi: int, target_px: Optional[Tuple[int,int]]) -> Image.Image:
    if target_px is not None:
        rect = page.rect
        target_w, target_h = target_px
        scale = max(target_w/rect.width, target_h/rect.height)
        zoom = max(scale, 1.0)
    else:
        zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if target_px is not None and (img.width != target_px[0] or img.height != target_px[1]):
        img = ImageOps.contain(img, target_px)
        canvas = Image.new("RGB", target_px, (255,255,255))
        canvas.paste(img, ((target_px[0]-img.width)//2, (target_px[1]-img.height)//2))
        return canvas
    return img

def _size_in_px(rect: fitz.Rect, dpi: int) -> Tuple[int,int]:
    return (int(round(rect.width*dpi/72.0)), int(round(rect.height*dpi/72.0)))

def _colorize_with_brightness(rgb_image: Image.Image, target_color: Tuple[int,int,int], whiten: Optional[int]=None) -> Image.Image:
    gray = rgb_image.convert("L")
    if whiten is not None and whiten > 0:
        gray = gray.point(lambda v: 255 if v >= whiten else v, mode="L")
    w, h = rgb_image.size
    out = Image.new("RGB", (w, h))
    tr, tg, tb = target_color
    gpx, opx = gray.load(), out.load()
    for y in range(h):
        for x in range(w):
            v = gpx[x, y]
            r = int(tr + (255 - tr) * (v/255.0))
            g = int(tg + (255 - tg) * (v/255.0))
            b = int(tb + (255 - tb) * (v/255.0))
            opx[x, y] = (r, g, b)
    return out

def _save_pages_as_pdf_jpeg(images: List[Image.Image], out_pdf_path: str, dpi: int, quality: int, subsampling: str, progressive: bool):
    pdf = fitz.open()
    try:
        for im in images:
            if im.mode != "RGB":
                im = im.convert("RGB")
            w_px, h_px = im.size
            w_pt, h_pt = w_px*72.0/dpi, h_px*72.0/dpi
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True,
                    subsampling=subsampling, progressive=progressive)
            page = pdf.new_page(width=w_pt, height=h_pt)
            page.insert_image(fitz.Rect(0, 0, w_pt, h_pt),
                              stream=buf.getvalue(), keep_proportion=False)
        pdf.save(out_pdf_path, deflate=True, garbage=4, clean=True)
    finally:
        pdf.close()

def generate_diff(before_pdf: str, after_pdf: str, out_pdf: str,
                  dpi: int=240, whiten: int=0, page_mode: str="min",
                  jpeg_quality: int=80, jpeg_subsampling: str="4:2:0",
                  progressive_jpeg: bool=True) -> None:
    doc_b = fitz.open(before_pdf)
    doc_a = fitz.open(after_pdf)
    n_b, n_a = doc_b.page_count, doc_a.page_count
    n = min(n_b, n_a) if page_mode == "min" else max(n_b, n_a)
    if n == 0:
        raise RuntimeError("ページがありません。")
    pages_out: List[Image.Image] = []
    for i in range(n):
        page_b = doc_b.load_page(i) if i < n_b else None
        page_a = doc_a.load_page(i) if i < n_a else None
        base_rect = (page_b or page_a).rect
        target_px = _size_in_px(base_rect, dpi)
        img_b = _render_page_to_rgb(page_b, dpi=dpi, target_px=target_px) if page_b else Image.new("RGB", target_px, (255,255,255))
        img_a = _render_page_to_rgb(page_a, dpi=dpi, target_px=target_px) if page_a else Image.new("RGB", target_px, (255,255,255))
        col_b = _colorize_with_brightness(img_b, (255,0,255), whiten=whiten)
        col_a = _colorize_with_brightness(img_a, (0,255,0),   whiten=whiten)
        diff_img = ImageChops.multiply(col_b, col_a)
        pages_out.append(diff_img)
    _save_pages_as_pdf_jpeg(pages_out, out_pdf, dpi=dpi,
                            quality=jpeg_quality, subsampling=jpeg_subsampling,
                            progressive=progressive_jpeg)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="PDF Diff（軽量版：JPEG埋め込み）")
    p.add_argument("-b","--before", required=True)
    p.add_argument("-a","--after",  required=True)
    p.add_argument("-o","--out",    required=True)
    p.add_argument("--dpi", type=int, default=240)
    p.add_argument("--whiten", type=int, default=0)
    p.add_argument("--page-mode", choices=["min","max"], default="min")
    p.add_argument("--jpeg-quality", type=int, default=80)
    p.add_argument("--jpeg-subsampling", default="4:2:0")
    p.add_argument("--jpeg-progressive", action="store_true", default=True)
    args = p.parse_args()
    generate_diff(args.before, args.after, args.out, dpi=args.dpi,
                  whiten=args.whiten, page_mode=args.page_mode,
                  jpeg_quality=args.jpeg_quality,
                  jpeg_subsampling=args.jpeg_subsampling,
                  progressive_jpeg=args.jpeg_progressive)
    print(f"\n✅ Done (small): {os.path.abspath(args.out)}\n")
