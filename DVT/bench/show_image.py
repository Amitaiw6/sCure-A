"""Open an image in a plain always-on-top window (used for bench screenshots).
Usage: python show_image.py image.png [title]"""
import sys, tkinter as tk
from PIL import Image, ImageTk

try:                                   # real pixels, not DPI-virtualised ones
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # noqa: BLE001
    pass

path = sys.argv[1]
title = sys.argv[2] if len(sys.argv) > 2 else path
root = tk.Tk()
root.title(title)
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
im = Image.open(path)
scale = min(sw / im.width, sh / im.height)      # fit the whole screen, Tk units
im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
ph = ImageTk.PhotoImage(im)
root.configure(bg="white")
tk.Label(root, image=ph, bg="white").place(relx=0.5, rely=0.5, anchor="center")
root.attributes("-fullscreen", True)           # same units as winfo_screen*, no DPI surprises
root.bind("<Escape>", lambda e: root.destroy())
root.attributes("-topmost", True)
root.lift()
root.focus_force()
root.mainloop()
