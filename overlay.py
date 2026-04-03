"""
overlay.py — 视觉小说实时翻译覆盖层
======================================
工作流程：
  1. 用鼠标框选游戏对话框区域（只截取这块，减少 OCR 干扰）
  2. 监听屏幕变化 / 按快捷键 → 截图 → manga-ocr 识别 → Claude/DeepL 翻译
  3. 用一个透明置顶 tkinter 窗口显示译文，悬浮在游戏画面之上
  4. 鼠标点击穿透覆盖层，游戏交互完全不受影响

依赖安装：
  pip install pillow manga-ocr anthropic imagehash keyboard pywin32
  （macOS 用 pyobjc-framework-Quartz 代替 pywin32）
"""

import threading
import time
import hashlib
import tkinter as tk
from tkinter import font as tkfont
from dataclasses import dataclass, field
from typing import Optional
import queue

import PIL.Image
import PIL.ImageGrab
import imagehash
import keyboard

from ocr import run_ocr
from translator import translate_text
from region_selector import select_region

# ─── 配置 ──────────────────────────────────────────────────────────────────

@dataclass
class Config:
    # 截图区域（x1, y1, x2, y2），None = 先弹出选择框
    capture_region: Optional[tuple] = None

    # 翻译目标语言
    target_lang: str = "zh-CN"

    # 轮询间隔（秒）：每隔多久检测屏幕变化
    poll_interval: float = 0.8

    # 图像差异阈值：低于此值认为画面没变化（0~64，越大越宽松）
    change_threshold: int = 5

    # 覆盖层样式
    overlay_bg: str = "#0d1117"          # 背景色
    overlay_fg: str = "#e8f4fd"          # 译文颜色
    overlay_orig_fg: str = "#5a8aa8"     # 原文颜色
    overlay_alpha: float = 0.88          # 窗口透明度 (0~1)
    overlay_font_size: int = 16
    overlay_orig_font_size: int = 12
    overlay_padding: int = 16
    overlay_radius: int = 12             # 圆角（用 Canvas 模拟）

    # 覆盖层位置（相对屏幕）："auto" = 贴近对话框上方，或手动指定
    overlay_anchor: str = "auto"         # auto | top | bottom | custom
    overlay_custom_y: int = 50           # anchor=custom 时距屏幕顶部距离

    # 快捷键
    hotkey_translate: str = "ctrl+shift+t"   # 手动触发翻译
    hotkey_toggle: str = "ctrl+shift+h"      # 显示/隐藏覆盖层
    hotkey_reselect: str = "ctrl+shift+r"    # 重新选择截图区域

    # OCR 引擎："manga_ocr"（推荐日文）| "tesseract"
    ocr_engine: str = "manga_ocr"

    # 翻译后端："claude" | "deepl" | "google"
    translate_backend: str = "claude"


# ─── 覆盖层窗口 ────────────────────────────────────────────────────────────

class TranslatorOverlay:
    """
    透明置顶窗口。
    - Windows: WS_EX_LAYERED + WS_EX_TRANSPARENT 实现鼠标穿透
    - macOS:   NSPanel + ignoresMouseEvents
    鼠标事件完全穿透到下面的游戏窗口，游戏交互零影响。
    """

    def __init__(self, config: Config):
        self.config = config
        self.visible = True
        self._current_text = ""
        self._current_orig = ""
        self._update_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._start_update_loop()

    def _setup_window(self):
        cfg = self.config
        root = self.root

        root.title("VN Translator Overlay")
        root.overrideredirect(True)          # 无边框无标题栏
        root.attributes("-topmost", True)    # 始终置顶
        root.attributes("-alpha", cfg.overlay_alpha)
        root.configure(bg=cfg.overlay_bg)
        root.resizable(False, False)

        # ── 鼠标穿透（Windows）─────────────────────────────
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            # WS_EX_LAYERED | WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
        except Exception:
            pass  # 非 Windows 平台跳过

        # ── 鼠标穿透（macOS）──────────────────────────────
        try:
            root.tk.call(
                "::tk::unsupported::MacWindowStyle",
                "style", root._w, "help", "noActivates"
            )
        except Exception:
            pass

        # 初始定位
        self._reposition()

    def _build_ui(self):
        cfg = self.config
        self.canvas = tk.Canvas(
            self.root,
            bg=cfg.overlay_bg,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        base_font = tkfont.Font(
            family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif",
            size=cfg.overlay_font_size,
        )
        orig_font = tkfont.Font(
            family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif",
            size=cfg.overlay_orig_font_size,
        )

        # 译文（主体）
        self.tl_text = self.canvas.create_text(
            cfg.overlay_padding, cfg.overlay_padding,
            anchor="nw",
            fill=cfg.overlay_fg,
            font=base_font,
            width=0,   # 自动换行宽度，后续动态设置
            text="",
        )
        # 原文（小字）
        self.orig_text = self.canvas.create_text(
            cfg.overlay_padding, cfg.overlay_padding + 30,
            anchor="nw",
            fill=cfg.overlay_orig_fg,
            font=orig_font,
            width=0,
            text="",
        )

    def _reposition(self):
        """根据 anchor 设置覆盖层位置"""
        cfg = self.config
        sw = self.root.winfo_screenwidth()

        overlay_w = min(sw - 80, 900)
        overlay_h = 120  # 初始高度，内容更新时会动态调整

        x = (sw - overlay_w) // 2

        if cfg.overlay_anchor == "auto" and cfg.capture_region:
            # 贴近对话框上方 20px
            y = cfg.capture_region[1] - overlay_h - 20
            y = max(10, y)
        elif cfg.overlay_anchor == "bottom":
            sh = self.root.winfo_screenheight()
            y = sh - overlay_h - 40
        elif cfg.overlay_anchor == "custom":
            y = cfg.overlay_custom_y
        else:
            y = 10  # top

        self.root.geometry(f"{overlay_w}x{overlay_h}+{x}+{y}")
        self._overlay_w = overlay_w

    def update_translation(self, original: str, translated: str):
        """线程安全地更新显示内容（可从任何线程调用）"""
        self._update_queue.put((original, translated))

    def _start_update_loop(self):
        """每 100ms 检查一次队列，在主线程更新 UI"""
        def loop():
            while not self._update_queue.empty():
                try:
                    orig, tl = self._update_queue.get_nowait()
                    self._apply_update(orig, tl)
                except queue.Empty:
                    break
            self.root.after(100, loop)

        self.root.after(100, loop)

    def _apply_update(self, original: str, translated: str):
        cfg = self.config
        pad = cfg.overlay_padding
        w = self._overlay_w - pad * 2

        # 更新文字
        self.canvas.itemconfigure(self.tl_text, text=translated, width=w)
        self.canvas.itemconfigure(self.orig_text, text=f"▸ {original}", width=w)

        # 动态计算高度，重新定位原文
        self.root.update_idletasks()
        tl_bbox = self.canvas.bbox(self.tl_text)
        tl_h = (tl_bbox[3] - tl_bbox[1]) if tl_bbox else 24

        orig_y = pad + tl_h + 8
        self.canvas.coords(self.orig_text, pad, orig_y)

        orig_bbox = self.canvas.bbox(self.orig_text)
        orig_h = (orig_bbox[3] - orig_bbox[1]) if orig_bbox else 16

        total_h = orig_y + orig_h + pad

        # 调整窗口高度
        sw = self.root.winfo_screenwidth()
        overlay_w = min(sw - 80, 900)
        x = (sw - overlay_w) // 2
        cur_geo = self.root.geometry()
        y = int(cur_geo.split("+")[2])
        self.root.geometry(f"{overlay_w}x{total_h}+{x}+{y}")
        self.canvas.configure(width=overlay_w, height=total_h)

        # 圆角背景（用矩形近似）
        self.canvas.delete("bg_rect")
        self.canvas.create_rectangle(
            0, 0, overlay_w, total_h,
            fill=cfg.overlay_bg,
            outline="#1e3a4f",
            width=1,
            tags="bg_rect",
        )
        self.canvas.tag_lower("bg_rect")

    def toggle_visibility(self):
        self.visible = not self.visible
        self.root.attributes("-alpha", self.config.overlay_alpha if self.visible else 0)

    def run(self):
        self.root.mainloop()


# ─── 截图 + 变化检测 ───────────────────────────────────────────────────────

class ScreenMonitor:
    """
    轮询截图，用感知哈希检测画面是否变化。
    变化时通知回调。
    """

    def __init__(self, config: Config, on_change):
        self.config = config
        self.on_change = on_change
        self._last_hash = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def capture_now(self) -> PIL.Image.Image:
        region = self.config.capture_region
        if region:
            img = PIL.ImageGrab.grab(bbox=region)
        else:
            img = PIL.ImageGrab.grab()
        return img

    def _loop(self):
        while self._running:
            try:
                img = self.capture_now()
                h = imagehash.phash(img)
                if self._last_hash is None:
                    self._last_hash = h
                elif abs(h - self._last_hash) > self.config.change_threshold:
                    self._last_hash = h
                    self.on_change(img)
            except Exception as e:
                print(f"[Monitor] 截图错误: {e}")
            time.sleep(self.config.poll_interval)


# ─── 主控制器 ──────────────────────────────────────────────────────────────

class TranslatorApp:
    def __init__(self):
        self.config = Config()
        self.overlay = None
        self.monitor = None
        self._translating = False
        self._last_source_text = ""

    def setup(self):
        print("请用鼠标框选游戏对话框区域…")
        region = select_region()
        if region:
            self.config.capture_region = region
            print(f"已选择区域: {region}")
        else:
            print("未选择区域，将截取全屏")

        self.overlay = TranslatorOverlay(self.config)
        self.monitor = ScreenMonitor(self.config, self._on_screen_change)

        # 注册快捷键
        keyboard.add_hotkey(self.config.hotkey_translate, self._manual_trigger)
        keyboard.add_hotkey(self.config.hotkey_toggle, self.overlay.toggle_visibility)
        keyboard.add_hotkey(self.config.hotkey_reselect, self._reselect_region)

        print(f"快捷键: {self.config.hotkey_translate} 手动翻译 | "
              f"{self.config.hotkey_toggle} 显示/隐藏 | "
              f"{self.config.hotkey_reselect} 重选区域")

        self.monitor.start()
        self.overlay.run()   # 阻塞主线程（tkinter 主循环）

    def _on_screen_change(self, img: PIL.Image.Image):
        """屏幕变化时，在后台线程执行 OCR + 翻译"""
        if self._translating:
            return  # 上一次还没翻译完，跳过
        threading.Thread(target=self._process_image, args=(img,), daemon=True).start()

    def _manual_trigger(self):
        img = self.monitor.capture_now()
        threading.Thread(target=self._process_image, args=(img,), daemon=True).start()

    def _process_image(self, img: PIL.Image.Image):
        self._translating = True
        try:
            # Step 1: OCR
            text = run_ocr(img, engine=self.config.ocr_engine)
            text = text.strip()

            if not text or text == self._last_source_text:
                return  # 内容没变化，不重复翻译

            self._last_source_text = text
            print(f"[OCR] {text[:60]}{'…' if len(text) > 60 else ''}")

            # Step 2: 翻译
            translated = translate_text(
                text,
                target_lang=self.config.target_lang,
                backend=self.config.translate_backend,
            )
            print(f"[翻译] {translated[:60]}{'…' if len(translated) > 60 else ''}")

            # Step 3: 更新覆盖层
            self.overlay.update_translation(text, translated)

        except Exception as e:
            print(f"[错误] {e}")
        finally:
            self._translating = False

    def _reselect_region(self):
        self.monitor.stop()
        region = select_region()
        if region:
            self.config.capture_region = region
        self.monitor.start()


# ─── 入口 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = TranslatorApp()
    app.setup()