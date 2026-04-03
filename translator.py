"""
translator.py — 翻译模块
支持三种后端：
  - claude：质量最高，理解上下文和语气，推荐视觉小说
  - deepl：速度快，日→中质量很好
  - google：免费，无需 key
"""

import os
import functools
from typing import Optional


# ── 上下文记忆（保留最近几句对话，帮助 Claude 理解语境）────────────────

class ContextBuffer:
    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        self._history: list[tuple[str, str]] = []  # [(原文, 译文), ...]

    def add(self, source: str, translated: str):
        self._history.append((source, translated))
        if len(self._history) > self.max_turns:
            self._history.pop(0)

    def format_for_prompt(self) -> str:
        if not self._history:
            return ""
        lines = ["【前文参考（勿翻译）】"]
        for src, tl in self._history:
            lines.append(f"  原：{src}")
            lines.append(f"  译：{tl}")
        return "\n".join(lines)


_context = ContextBuffer()


# ── Claude 翻译 ─────────────────────────────────────────────────────────

def translate_with_claude(text: str, target_lang: str) -> str:
    """
    用 Claude 翻译，带视觉小说专用提示词。
    需设置环境变量：ANTHROPIC_API_KEY
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    lang_name = {"zh-CN": "简体中文", "zh-TW": "繁体中文", "en": "英文"}.get(
        target_lang, target_lang
    )

    context_str = _context.format_for_prompt()

    system_prompt = f"""你是一名专业的视觉小说翻译，正在为玩家提供实时字幕翻译。

翻译规则：
1. 只输出译文，不要任何解释、标注或前缀
2. 保持角色的语气、语调和说话风格（如傲娇、温柔、元气等）
3. 保留日文特有的语气词感觉，但用{lang_name}自然表达
4. 人名、地名保持原文或常见译名
5. 如果是选项文字，保持简短
6. 译文要自然流畅，像{lang_name}母语者说的话

{context_str}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": f"请将以下文字翻译成{lang_name}：\n{text}"}],
    )

    translated = message.content[0].text.strip()
    _context.add(text, translated)
    return translated


# ── DeepL 翻译 ──────────────────────────────────────────────────────────

def translate_with_deepl(text: str, target_lang: str) -> str:
    """
    用 DeepL API 翻译（免费版每月 50 万字符）。
    需设置环境变量：DEEPL_API_KEY
    """
    import urllib.request
    import urllib.parse
    import json

    api_key = os.environ.get("DEEPL_API_KEY", "")
    if not api_key:
        raise ValueError("请设置环境变量 DEEPL_API_KEY")

    # 免费版用 api-free.deepl.com，付费版用 api.deepl.com
    endpoint = "https://api-free.deepl.com/v2/translate"

    tl = target_lang.split("-")[0].upper()
    if target_lang == "zh-CN":
        tl = "ZH"

    data = urllib.parse.urlencode({
        "text": text,
        "target_lang": tl,
        "source_lang": "JA",
    }).encode()

    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    return result["translations"][0]["text"]


# ── Google 翻译（免费，无需 key）───────────────────────────────────────

def translate_with_google(text: str, target_lang: str) -> str:
    """
    Google 翻译免费接口，无需 API key，有频率限制。
    """
    import urllib.request
    import urllib.parse
    import json

    tl = target_lang.replace("-", "_")
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={urllib.parse.quote(tl)}"
        f"&dt=t&q={urllib.parse.quote(text)}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())

    segments = data[0] or []
    return "".join(seg[0] for seg in segments if seg and seg[0])


# ── 统一入口 ────────────────────────────────────────────────────────────

def translate_text(
    text: str,
    target_lang: str = "zh-CN",
    backend: str = "claude",
) -> str:
    """
    统一翻译入口
    backend: "claude" | "deepl" | "google"
    """
    if not text.strip():
        return ""

    if backend == "claude":
        return translate_with_claude(text, target_lang)
    elif backend == "deepl":
        return translate_with_deepl(text, target_lang)
    elif backend == "google":
        return translate_with_google(text, target_lang)
    else:
        raise ValueError(f"未知翻译后端: {backend}，可选: claude, deepl, google")
