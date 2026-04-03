"""
ocr.py — OCR 模块
支持两种引擎：
  - manga_ocr：专为日语漫画/视觉小说优化，识别率极高
  - tesseract：通用，支持多语言
"""

import PIL.Image
from functools import lru_cache


# ── manga-ocr（懒加载，首次调用时才加载模型）────────────────────────────

@lru_cache(maxsize=1)
def _get_manga_ocr():
    """只加载一次模型（约 400MB，首次需要下载）"""
    try:
        from manga_ocr import MangaOcr
        print("[OCR] 正在加载 manga-ocr 模型（首次需要下载约 400MB）…")
        mocr = MangaOcr()
        print("[OCR] 模型加载完成")
        return mocr
    except ImportError:
        raise ImportError(
            "请先安装: pip install manga-ocr\n"
            "如果网络较慢，也可以手动下载模型：\n"
            "  huggingface-cli download kha-white/manga-ocr-base"
        )


def ocr_manga(img: PIL.Image.Image) -> str:
    """使用 manga-ocr 识别图像中的日文文字"""
    mocr = _get_manga_ocr()
    return mocr(img)


# ── Tesseract（通用 OCR）────────────────────────────────────────────────

def ocr_tesseract(img: PIL.Image.Image, lang: str = "jpn") -> str:
    """
    使用 Tesseract 识别文字
    lang: "jpn" 日文 | "eng" 英文 | "jpn+eng" 混合
    需要安装：
      - Windows: https://github.com/UB-Mannheim/tesseract/wiki
      - macOS:   brew install tesseract tesseract-lang
      - Linux:   sudo apt install tesseract-ocr tesseract-ocr-jpn
    """
    try:
        import pytesseract
    except ImportError:
        raise ImportError("请先安装: pip install pytesseract")

    # 预处理：放大 + 灰度，提升识别率
    w, h = img.size
    img_proc = img.resize((w * 2, h * 2), PIL.Image.LANCZOS).convert("L")

    config = "--psm 6"  # 假设为整块文字区域
    return pytesseract.image_to_string(img_proc, lang=lang, config=config).strip()


# ── 预处理：对话框文字常见优化 ─────────────────────────────────────────

def preprocess_for_vn(img: PIL.Image.Image) -> PIL.Image.Image:
    """
    视觉小说对话框预处理：
    - 裁掉顶部/底部可能的装饰边框（避免误识别）
    - 提高对比度
    """
    import PIL.ImageEnhance
    import PIL.ImageFilter

    # 裁掉上下各 5% 的边缘（通常是对话框边框装饰）
    w, h = img.size
    margin_v = int(h * 0.05)
    margin_h = int(w * 0.03)
    img = img.crop((margin_h, margin_v, w - margin_h, h - margin_v))

    # 提高对比度
    enhancer = PIL.ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    return img


# ── 统一入口 ────────────────────────────────────────────────────────────

def run_ocr(img: PIL.Image.Image, engine: str = "manga_ocr") -> str:
    """
    统一 OCR 入口
    engine: "manga_ocr" | "tesseract"
    """
    img = preprocess_for_vn(img)

    if engine == "manga_ocr":
        return ocr_manga(img)
    elif engine == "tesseract":
        return ocr_tesseract(img)
    else:
        raise ValueError(f"未知 OCR 引擎: {engine}，可选: manga_ocr, tesseract")