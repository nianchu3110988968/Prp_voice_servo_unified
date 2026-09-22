from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "论文初稿"
DOCX_PATH = PAPER_DIR / "毛绒陪伴机器人语音与动作系统设计_正式版.docx"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")

INK = "#23313F"
MUTED = "#536272"
LINE = "#526170"
WHITE = "#FFFFFF"
ORANGE = "#FCEAD8"
ORANGE_DARK = "#C96B28"
BLUE = "#E2EFFA"
BLUE_DARK = "#3976A8"
GREEN = "#E5F2E4"
GREEN_DARK = "#4B8B52"
PURPLE = "#EEE5F6"
PURPLE_DARK = "#7A55A1"
GRAY = "#F4F6F8"
GRAY_DARK = "#768492"
RED = "#B84D45"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def rounded_box(draw: ImageDraw.ImageDraw, xy, fill, outline=LINE, width=4, radius=28):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def centered_text(draw: ImageDraw.ImageDraw, xy, text: str, fnt, fill=INK, spacing=12):
    left, top, right, bottom = xy
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, spacing=spacing, align="center")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text(
        ((left + right - w) / 2, (top + bottom - h) / 2 - bbox[1]),
        text,
        font=fnt,
        fill=fill,
        spacing=spacing,
        align="center",
    )


def arrow(draw: ImageDraw.ImageDraw, points, color=LINE, width=8, head=22):
    draw.line(points, fill=color, width=width, joint="curve")
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    if x1 > x0:
        tip = [(x1, y1), (x1 - head, y1 - head * 0.65), (x1 - head, y1 + head * 0.65)]
    elif x1 < x0:
        tip = [(x1, y1), (x1 + head, y1 - head * 0.65), (x1 + head, y1 + head * 0.65)]
    elif y1 > y0:
        tip = [(x1, y1), (x1 - head * 0.65, y1 - head), (x1 + head * 0.65, y1 - head)]
    else:
        tip = [(x1, y1), (x1 - head * 0.65, y1 + head), (x1 + head * 0.65, y1 + head)]
    draw.polygon(tip, fill=color)


def label(draw: ImageDraw.ImageDraw, center, text: str, size=30, fill=WHITE, outline="#D8DEE4"):
    fnt = font(size)
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, spacing=6, align="center")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = center
    pad_x, pad_y = 18, 9
    rounded_box(draw, (x - w / 2 - pad_x, y - h / 2 - pad_y, x + w / 2 + pad_x, y + h / 2 + pad_y), fill, outline, 2, 16)
    draw.multiline_text((x - w / 2, y - h / 2 - bbox[1]), text, font=fnt, fill=MUTED, spacing=6, align="center")


def layer_band(draw, y, title, detail, fill, accent):
    x1, x2, h = 95, 2305, 190
    rounded_box(draw, (x1, y, x2, y + h), fill, outline=accent, width=4, radius=26)
    draw.rounded_rectangle((x1, y, x1 + 470, y + h), radius=26, fill=accent)
    draw.rectangle((x1 + 440, y, x1 + 500, y + h), fill=accent)
    centered_text(draw, (x1 + 28, y + 20, x1 + 442, y + h - 20), title, font(42, True), WHITE)
    centered_text(draw, (x1 + 535, y + 20, x2 - 38, y + h - 20), detail, font(35), INK, 14)


def draw_architecture(path: Path):
    img = Image.new("RGB", (2400, 1355), WHITE)
    d = ImageDraw.Draw(img)
    bands = [
        (45, "用户交互层", "用户说话与唤醒  ·  听取语音回复  ·  观察四肢和尾巴动作", ORANGE, ORANGE_DARK),
        (295, "设备感知与执行层", "ESP32-S3  ·  INMP441麦克风  ·  MAX98357A功放与喇叭  ·  PCA9685与五路舵机", BLUE, BLUE_DARK),
        (545, "通信与业务调度层", "Wi-Fi与HTTP  ·  FastAPI AI bridge  ·  PCM/WAV处理  ·  JSON结果汇总", GREEN, GREEN_DARK),
        (795, "AI能力层", "faster-whisper语音识别  ·  Ollama对话生成  ·  糯糯角色配置  ·  SAPI或GPT-SoVITS语音合成", PURPLE, PURPLE_DARK),
    ]
    for args in bands:
        layer_band(d, *args)
    for y, txt in [(235, "声音输入 / 语音回复 / 动作反馈"), (485, "16 kHz PCM上传 / WAV与动作下发"), (735, "识别文字 / 回复、情绪、动作与音频")]:
        arrow(d, [(1200, y - 5), (1200, y + 55)], width=7, head=19)
        label(d, (1625, y + 25), txt, size=27)

    rounded_box(d, (95, 1050, 2305, 1295), GRAY, outline=GRAY_DARK, width=3, radius=24)
    d.text((145, 1090), "供电基础设施", font=font(34, True), fill=INK)
    d.multiline_text(
        (145, 1145),
        "2S 7.4 V电池 → 保护与总开关 → 5 V稳压 → 星形分支供电\nPCA9685 VCC为逻辑电源，V+为舵机大电流电源；全部模块在电源分配点共地。",
        font=font(31), fill=MUTED, spacing=13,
    )
    img.save(path, quality=95, dpi=(300, 300))


def power_box(draw, xy, title, lines, fill, accent):
    rounded_box(draw, xy, fill, outline=accent, width=4, radius=25)
    x1, y1, x2, y2 = xy
    draw.text((x1 + 30, y1 + 23), title, font=font(38, True), fill=INK)
    draw.multiline_text((x1 + 30, y1 + 83), lines, font=font(29), fill=MUTED, spacing=10)


def draw_power(path: Path):
    img = Image.new("RGB", (2400, 1242), WHITE)
    d = ImageDraw.Draw(img)
    power_box(d, (70, 420, 420, 650), "2S 7.4 V电池", "满电约8.4 V\n电池规格待最终匹配", ORANGE, ORANGE_DARK)
    power_box(d, (520, 420, 870, 650), "保护与总开关", "BMS / 保险丝\n切断整机输入电源", PURPLE, PURPLE_DARK)
    power_box(d, (970, 420, 1360, 650), "5 V稳压模块", "建议额定6～8 A\n按实测峰值校核", GREEN, GREEN_DARK)

    arrow(d, [(420, 535), (520, 535)], color=ORANGE_DARK)
    label(d, (470, 365), "7.4～8.4 V", size=25)
    arrow(d, [(870, 535), (970, 535)], color=ORANGE_DARK)
    label(d, (920, 365), "受保护输入", size=25)

    # 5 V distribution bus and three strictly orthogonal branches.
    d.line([(1360, 535), (1515, 535)], fill=ORANGE_DARK, width=9)
    d.ellipse((1497, 517, 1533, 553), fill=ORANGE_DARK)
    d.line([(1515, 190), (1515, 880)], fill=ORANGE_DARK, width=9)

    branches = [
        ((1740, 90, 2320, 310), "舵机大电流支路", "PCA9685 V+ → 五只舵机\n电源入口附近并联大电容", ORANGE, ORANGE_DARK, 200),
        ((1740, 420, 2320, 650), "主控与逻辑支路", "ESP32 5V/VIN\n板载3.3 V → INMP441、PCA9685 VCC", BLUE, BLUE_DARK, 535),
        ((1740, 760, 2320, 980), "音频功放支路", "MAX98357A VIN\n按模块额定电压连接", BLUE, BLUE_DARK, 870),
    ]
    for xy, title, lines, fill, accent, cy in branches:
        d.line([(1515, cy), (1740, cy)], fill=ORANGE_DARK, width=9)
        arrow(d, [(1685, cy), (1740, cy)], color=ORANGE_DARK, width=9, head=22)
        power_box(d, xy, title, lines, fill, accent)
    label(d, (1515, 110), "5 V星形分支", size=28)

    # Ground bus is intentionally separate from the power arrows.
    d.line([(165, 1080), (2210, 1080)], fill=LINE, width=7)
    for x in (245, 695, 1165, 1890):
        d.line([(x, 1040), (x, 1080)], fill=LINE, width=6)
        d.ellipse((x - 9, 1071, x + 9, 1089), fill=LINE)
    centered_text(d, (200, 1090, 2200, 1185), "所有支路在电源分配点共地；舵机电流不得经过ESP32开发板或普通杜邦线。", font(31, True), INK)
    d.text((75, 1165), "说明：USB仅用于烧录和调试；外部5 V与USB同时连接前应确认隔离，避免倒灌。整机供电方案待五舵机联调验证。", font=font(27), fill=RED)
    img.save(path, quality=95, dpi=(300, 300))


def flow_box(draw, xy, number, title, lines, fill, accent):
    rounded_box(draw, xy, fill, outline=accent, width=4, radius=25)
    x1, y1, x2, y2 = xy
    draw.ellipse((x1 + 24, y1 + 24, x1 + 82, y1 + 82), fill=accent)
    centered_text(draw, (x1 + 24, y1 + 24, x1 + 82, y1 + 82), str(number), font(28, True), WHITE)
    draw.text((x1 + 103, y1 + 24), title, font=font(36, True), fill=INK)
    draw.multiline_text((x1 + 30, y1 + 93), lines, font=font(28), fill=MUTED, spacing=10)


def draw_data_flow(path: Path):
    img = Image.new("RGB", (2400, 1582), WHITE)
    d = ImageDraw.Draw(img)
    xs = [(70, 525), (645, 1100), (1220, 1675), (1795, 2250)]
    top_y = (95, 390)
    bottom_y = (790, 1085)
    top = [
        (1, "用户语音", "说出唤醒词\n并提出问题", ORANGE, ORANGE_DARK),
        (2, "ESP32本地处理", "INMP441采集\n唤醒检测、pre-roll\n端点检测与PCM录音", BLUE, BLUE_DARK),
        (3, "AI bridge接收", "Wi-Fi / HTTP上传\n16 kHz单声道PCM\n转换WAV并调度服务", GREEN, GREEN_DARK),
        (4, "ASR语音识别", "faster-whisper small\n输出识别文字\n解码参数可配置", PURPLE, PURPLE_DARK),
    ]
    for xy, item in zip(xs, top):
        flow_box(d, (xy[0], top_y[0], xy[1], top_y[1]), *item)

    bottom = [
        (8, "ESP32播放与执行", "下载WAV并由MAX98357A播放\nmotion进入FreeRTOS动作队列\nPCA9685输出五路PWM", BLUE, BLUE_DARK),
        (7, "返回汇总结果", "JSON：reply_text、emotion、motion\nlatency与audio_url", GREEN, GREEN_DARK),
        (6, "生成语音", "Windows SAPI\n或GPT-SoVITS\n输出可下载WAV", PURPLE, PURPLE_DARK),
        (5, "生成回复与意图", "Ollama结合糯糯人设\n和短期上下文\n输出回复、情绪与动作意图", ORANGE, ORANGE_DARK),
    ]
    for xy, item in zip(xs, bottom):
        flow_box(d, (xy[0], bottom_y[0], xy[1], bottom_y[1]), *item)

    # Top row, left to right.
    labels_top = ["声音", "PCM / HTTP", "识别请求"]
    for i, txt in enumerate(labels_top):
        x1, x2 = xs[i][1], xs[i + 1][0]
        arrow(d, [(x1, 243), (x2, 243)], width=8)
        label(d, ((x1 + x2) / 2, 38), txt, size=23)

    # Downward transition, then bottom row right to left.
    arrow(d, [(2023, 390), (2023, 790)], width=8)
    label(d, (2170, 590), "识别文字", size=25)
    labels_bottom = ["回复文字", "WAV / audio_url", "JSON结果"]
    for i, txt in enumerate(labels_bottom):
        # bottom boxes are visually ordered 8,7,6,5, so flow travels from right to left.
        right_box = xs[3 - i]
        left_box = xs[2 - i]
        arrow(d, [(right_box[0], 938), (left_box[1], 938)], width=8)
        label(d, ((right_box[0] + left_box[1]) / 2, 720), txt, size=23)

    rounded_box(d, (155, 1220, 2245, 1480), GRAY, outline=GRAY_DARK, width=3, radius=24)
    centered_text(
        d,
        (205, 1245, 2195, 1345),
        "播放结束 → 继续监听下一轮语音 → 超时或达到轮数限制后返回等待唤醒",
        font(34, True), INK,
    )
    centered_text(
        d,
        (205, 1350, 2195, 1448),
        "端点检测、服务端管线与WAV下载播放已有代码；新版连续对话配置已编译，尚待烧录实测。\n五舵机动作架构已写入代码，目前仅PCA9685通道0完成实际运动验证。",
        font(27), RED, 12,
    )
    img.save(path, quality=95, dpi=(300, 300))


def patch_docx(docx_path: Path, replacements: dict[str, Path]) -> Path:
    with tempfile.TemporaryDirectory(prefix="paper_figures_") as temp_dir:
        temp_dir = Path(temp_dir)
        backup = temp_dir / docx_path.name
        shutil.copy2(docx_path, backup)
        patched = temp_dir / f"{docx_path.stem}_patched.docx"
        with zipfile.ZipFile(backup, "r") as zin, zipfile.ZipFile(patched, "w") as zout:
            for item in zin.infolist():
                data = replacements[item.filename].read_bytes() if item.filename in replacements else zin.read(item.filename)
                zout.writestr(item, data)
        try:
            shutil.copy2(patched, docx_path)
            return docx_path
        except PermissionError:
            # Word locks an open DOCX on Windows. Preserve the user's live file and
            # provide a complete optimized copy instead of forcing the application closed.
            fallback = docx_path.with_name(f"{docx_path.stem}_图示优化版{docx_path.suffix}")
            shutil.copy2(patched, fallback)
            return fallback


def main():
    parser = argparse.ArgumentParser(description="重绘论文示意图并替换正式版DOCX内嵌图片。")
    parser.add_argument("--images-only", action="store_true", help="仅生成PNG，不修改DOCX")
    args = parser.parse_args()

    outputs = {
        "word/media/image3.png": PAPER_DIR / "图2-1_四层总体架构.png",
        "word/media/image4.png": PAPER_DIR / "图3-1_成品供电结构.png",
        "word/media/image5.png": PAPER_DIR / "图4-1_语音交互数据流.png",
    }
    draw_architecture(outputs["word/media/image3.png"])
    draw_power(outputs["word/media/image4.png"])
    draw_data_flow(outputs["word/media/image5.png"])
    updated_docx = None
    if not args.images_only:
        updated_docx = patch_docx(DOCX_PATH, outputs)
    for path in outputs.values():
        print(path)
    if updated_docx is not None:
        print(updated_docx)


if __name__ == "__main__":
    main()
