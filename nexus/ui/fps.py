"""Contador de FPS (overlay sempre no topo) usando o PresentMon."""
import csv
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path

from ..core import NO_WINDOW, recurso


class FpsOverlay:
    def __init__(self, master):
        self.proc = None
        self.quadros = {}
        self.lock = threading.Lock()
        self.rodando = True
        self.fps_atual = 0
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.85)
        self.win.configure(bg="black")
        self.win.geometry("+20+20")
        self.lbl = tk.Label(self.win, text="FPS --", font=("Consolas", 22, "bold"), fg="#00ff66", bg="black", padx=12, pady=4)
        self.lbl.pack()
        self.sub = tk.Label(self.win, text="", font=("Consolas", 9), fg="#aaaaaa", bg="black")
        self.sub.pack()
        for w in (self.lbl, self.sub):
            w.bind("<ButtonPress-1>", lambda e: setattr(self, "_d", (e.x, e.y)))
            w.bind("<B1-Motion>", self._mover)
            w.bind("<Double-Button-1>", lambda e: self.fechar())
        self._iniciar()
        self._atualizar()

    def _mover(self, e):
        dx, dy = self._d
        self.win.geometry(f"+{self.win.winfo_x() + e.x - dx}+{self.win.winfo_y() + e.y - dy}")

    def _iniciar(self):
        exe = recurso("PresentMon.exe")
        if not exe.exists():
            exe = Path("PresentMon.exe")
        if not exe.exists():
            self.sub.config(text="PresentMon.exe não encontrado")
            return
        cmd = [str(exe), "--output_stdout", "--stop_existing_session", "--session_name", "NexusPC_FPS",
               "--no_console_stats"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True, creationflags=NO_WINDOW)
        except OSError as e:
            self.sub.config(text=f"erro: {e}")
            return
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        cab = None
        for linha in csv.reader(self.proc.stdout):
            if not self.rodando:
                break
            if cab is None:
                cab = linha
                continue
            try:
                d = dict(zip(cab, linha))
                app = d.get("Application") or d.get("ApplicationName") or "?"
                ft = float(d.get("MsBetweenPresents") or d.get("FrameTime") or 0)
                if ft <= 0 or app.lower() in ("dwm.exe", "explorer.exe", "?"):
                    continue
                with self.lock:
                    self.quadros.setdefault(app, []).append((time.time(), ft))
            except (ValueError, KeyError):
                continue

    def _atualizar(self):
        if not self.rodando:
            return
        agora, melhor, n = time.time(), None, 0
        with self.lock:
            for app, lst in list(self.quadros.items()):
                lst[:] = [(t, f) for t, f in lst if agora - t <= 1.0]
                if len(lst) > n:
                    melhor, n = app, len(lst)
        self.fps_atual = n if melhor else 0
        if melhor and n:
            self.lbl.config(text=f"FPS {n}", fg="#00ff66" if n >= 55 else "#ffcc00" if n >= 30 else "#ff4444")
            self.sub.config(text=melhor)
        else:
            self.lbl.config(text="FPS --", fg="#888888")
            if self.proc:
                self.sub.config(text="abra um jogo • duplo clique fecha")
        self.win.after(500, self._atualizar)

    def fechar(self):
        self.rodando = False
        if self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.win.destroy()
