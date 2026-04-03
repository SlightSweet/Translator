# VN Translator — 视觉小说实时翻译覆盖层

## 工作原理

```
游戏画面
   │
   ▼  变化检测（感知哈希，无需每帧比较）
截图（只截对话框区域）
   │
   ▼  manga-ocr（专为日文 VN 优化）
识别文字
   │
   ▼  Claude / DeepL / Google
翻译
   │
   ▼
透明置顶窗口（鼠标穿透，游戏交互完全不受影响）
```

**关键技术：鼠标穿透**
覆盖层窗口使用 Windows `WS_EX_TRANSPARENT` 扩展样式，鼠标点击事件直接穿透到下方的游戏窗口，游戏的点击、键盘输入完全正常。

---

## 安装

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key（选择一个）

**方案 A — Claude（推荐，语境理解最好）**
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-xxxxxxx

# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-xxxxxxx
```

**方案 B — DeepL（速度快）**
```bash
set DEEPL_API_KEY=your-deepl-key
```

**方案 C — Google（免费，无需 key）**
在 `overlay.py` 中设置：
```python
config.translate_backend = "google"
```

### 3. manga-ocr 模型（首次运行自动下载）
模型约 400MB，国内网络较慢时可手动下载：
```bash
pip install huggingface_hub
huggingface-cli download kha-white/manga-ocr-base
```

---

## 使用

```bash
python overlay.py
```

1. **启动后**：弹出全屏遮罩，用鼠标拖拽框选游戏对话框区域
2. **框选完成**：覆盖层出现在对话框上方，开始自动翻译
3. **快捷键**：
   - `Ctrl+Shift+T` — 手动触发翻译（对话没变化时用）
   - `Ctrl+Shift+H` — 显示/隐藏覆盖层
   - `Ctrl+Shift+R` — 重新选择截图区域

---

## 配置项（overlay.py 顶部 Config 类）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `poll_interval` | 0.8 | 检测屏幕变化的间隔（秒） |
| `change_threshold` | 5 | 变化灵敏度（0-64，越小越灵敏） |
| `ocr_engine` | manga_ocr | OCR 引擎：`manga_ocr` / `tesseract` |
| `translate_backend` | claude | 翻译后端：`claude` / `deepl` / `google` |
| `target_lang` | zh-CN | 目标语言：`zh-CN` / `zh-TW` / `en` |
| `overlay_alpha` | 0.88 | 覆盖层透明度（0~1） |
| `overlay_anchor` | auto | 覆盖层位置：`auto`（对话框上方）/ `bottom` / `top` |
| `overlay_font_size` | 16 | 译文字号 |

---

## 常见问题

**Q: 对话框位置每次不同怎么办？**
A: 用 `Ctrl+Shift+R` 重新框选，或将 `overlay_anchor` 改为 `bottom` 固定在屏幕底部。

**Q: OCR 识别率不好？**
A: manga-ocr 对日文效果最好。如果游戏是英文 VN，改用 tesseract：
```python
config.ocr_engine = "tesseract"
```

**Q: 翻译延迟太高？**
A: 改用 `deepl` 或 `google` 后端，或减少 `poll_interval`。

**Q: macOS 上鼠标穿透不工作？**
A: macOS 需要 Accessibility 权限。系统偏好设置 → 安全性与隐私 → 辅助功能，允许 Terminal/Python。
