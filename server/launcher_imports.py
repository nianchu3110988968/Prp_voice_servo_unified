"""Tk import forms; model hashing runs through the launcher's worker queue."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from services.profile_config import import_persona, import_voice, VERSIONS, LANGUAGES


def show_import(app, kind):
    dialog = tk.Toplevel(app.window)
    dialog.title("新建/导入人格" if kind == "persona" else "导入音色（不复制模型）")
    dialog.geometry("760x650")
    form = ttk.Frame(dialog, padding=12)
    form.pack(fill="both", expand=True)
    fields = {}
    names = [("id", "唯一ID（字母开头）"), ("display_name", "显示名称")]
    if kind == "persona":
        names += [("character_name", "角色名称")]
    else:
        names += [("gpt_weights", "GPT .ckpt"), ("sovits_weights", "SoVITS .pth"),
                  ("reference_wav", "参考 .wav"), ("gpt_sovits_version", "模型版本"),
                  ("prompt_language", "参考语言"), ("text_language", "合成语言"),
                  ("voice_revision", "音色版本（例如 v1）")]
    defaults = {"gpt_sovits_version": "v2ProPlus", "prompt_language": "zh", "text_language": "zh", "voice_revision": "v1"}
    def browse(variable, extension):
        path = filedialog.askopenfilename(parent=dialog, filetypes=[(extension, "*" + extension)])
        if path:
            variable.set(path)
    for key, label in names:
        row = ttk.Frame(form)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=24).pack(side="left")
        value = fields[key] = tk.StringVar(value=defaults.get(key, ""))
        options = sorted(VERSIONS if key == "gpt_sovits_version" else LANGUAGES)
        widget = (ttk.Combobox(row, textvariable=value, values=options, state="readonly")
                  if key in {"gpt_sovits_version", "prompt_language", "text_language"}
                  else ttk.Entry(row, textvariable=value))
        widget.pack(side="left", fill="x", expand=True)
        suffix = {"gpt_weights": ".ckpt", "sovits_weights": ".pth", "reference_wav": ".wav"}.get(key)
        if suffix:
            ttk.Button(row, text="选择", command=lambda v=value, s=suffix: browse(v, s)).pack(side="left")
    ttk.Label(form, text="人格正文（UTF-8）" if kind == "persona" else "参考音频逐字原文（必须与WAV一致）").pack(anchor="w")
    body = tk.Text(form, height=10, wrap="word")
    body.pack(fill="both", expand=True)
    if kind == "persona":
        def read_text():
            path = filedialog.askopenfilename(parent=dialog, filetypes=[("UTF-8 TXT", "*.txt")])
            if path:
                try:
                    text = Path(path).read_text(encoding="utf-8-sig")
                    body.delete("1.0", "end")
                    body.insert("1.0", text)
                except Exception as exc:
                    app.error(str(exc))
        ttk.Button(form, text="从UTF-8 TXT读取", command=read_text).pack(anchor="w")
    ttk.Label(form, text="保存为新的本地档案；已有ID不会覆盖。音色将自动计算并验证SHA256。", wraplength=700).pack(anchor="w", pady=6)
    def save():
        data = {key: value.get().strip() for key, value in fields.items()}
        text = body.get("1.0", "end").strip()
        if app.busy:
            return
        if kind == "persona":
            action = lambda: import_persona(data["id"], data["display_name"], data["character_name"], text, app.root).public()
        else:
            data.update(reference_text=text, weight_pair={})
            action = lambda: import_voice(data, app.root).public()
        # Keep the entered form available on validation failure.
        def completed(result):
            app.refresh_profiles()
            (app.persona if kind == "persona" else app.voice).set(data["id"])
            app.show_result({"已保存并验证": result})
            dialog.destroy()
        app.run(action, completed)
    ttk.Button(form, text="验证并保存本地配置", command=save).pack(pady=8)
