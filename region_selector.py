"""
region_selector.py — 用鼠标拖拽选择截图区域
弹出一个全屏半透明遮罩，拖拽选出矩形区域，松开鼠标后返回坐标。
"""

import tkinter as tk


def select_region() -> tuple | None:
    """
    让用户用鼠标拖拽选择屏幕区域。
    返回 (x1, y1, x2, y2) 或 None（用户取消）。
    """
    result = {"region": None}

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.25)
    root.configure(cursor="crosshair", bg="black")
    root.title("拖拽选择对话框区域 — 按 ESC 取消")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # 提示文字
    canvas.create_text(
        root.winfo_screenwidth() // 2,
        40,
        text="拖拽选择游戏对话框区域  |  ESC 取消",
        fill="white",
        font=("Arial", 18),
    )

    state = {"start": None, "rect": None}

    def on_press(e):
        state["start"] = (e.x, e.y)
        if state["rect"]:
            canvas.delete(state["rect"])

    def on_drag(e):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            x0, y0, e.x, e.y,
            outline="#00aaff", width=2, fill="#00aaff", stipple="gray25",
        )

    def on_release(e):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = e.x, e.y
        # 标准化坐标
        region = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        # 过滤太小的选区
        if (region[2] - region[0]) > 20 and (region[3] - region[1]) > 10:
            result["region"] = region
        root.destroy()

    def on_escape(e):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.mainloop()
    return result["region"]


if __name__ == "__main__":
    r = select_region()
    print("选择的区域:", r)
