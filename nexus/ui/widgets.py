"""Componentes visuais: botões, cartões, medidor circular e gráfico em tempo real."""
import tkinter as tk
from collections import deque

from . import theme as T


class Botao(tk.Label):
    """Botão plano com efeito hover. kind: 'primario' (ciano), 'sec' (grafite), 'perigo'."""

    def __init__(self, master, texto, comando, kind="sec", **kw):
        cores = {"primario": (T.CIANO, "#06222a", "#67e8f9"), "sec": (T.PANEL2, T.TEXTO, "#1c2434"),
                 "perigo": ("#3a1518", T.VERMELHO, "#4d1b20")}[kind]
        self._bg, self._fg, self._hover = cores
        super().__init__(master, text=texto, bg=self._bg, fg=self._fg, font=T.fonte(10, True),
                         padx=kw.pop("padx", 14), pady=kw.pop("pady", 7), cursor="hand2",
                         highlightthickness=1, highlightbackground=T.BORDA if kind != "primario" else T.CIANO, **kw)
        self._cmd, self._ativo = comando, True
        self.bind("<Enter>", lambda e: self._ativo and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._ativo and self._cmd and self._cmd())

    def marcar(self, ativo):
        """Destaca o botão (usado em abas)."""
        self._bg, self._fg, self._hover = ((T.CIANO, "#06222a", "#67e8f9") if ativo else (T.PANEL2, T.TEXTO, "#1c2434"))
        self.config(bg=self._bg, fg=self._fg)

    def ativar(self, sim):
        self._ativo = sim
        self.config(fg=self._fg if sim else T.MUDO, cursor="hand2" if sim else "arrow")


class Cartao(tk.Frame):
    def __init__(self, master, titulo="", cor=T.CIANO, **kw):
        super().__init__(master, bg=T.PANEL, highlightthickness=1, highlightbackground=T.BORDA, **kw)
        if titulo:
            tk.Label(self, text=titulo.upper(), bg=T.PANEL, fg=cor, font=T.fonte(8, True)).pack(
                anchor="w", padx=12, pady=(10, 0))
        self.corpo = tk.Frame(self, bg=T.PANEL)
        self.corpo.pack(fill="both", expand=True, padx=12, pady=(4, 10))


class Medidor(tk.Canvas):
    """Medidor em arco com animação suave. set(valor 0-100, texto, cor)."""

    def __init__(self, master, tamanho=130, espessura=11, **kw):
        super().__init__(master, width=tamanho, height=tamanho, bg=T.PANEL, highlightthickness=0, **kw)
        self.t, self.esp = tamanho, espessura
        self.atual = self.alvo = 0.0
        self.texto, self.sub, self.cor = "--", "", T.CIANO
        self._anim = False
        self._desenhar()

    def set(self, valor, texto=None, sub="", cor=None):
        self.alvo = max(0.0, min(100.0, float(valor or 0)))
        self.texto = texto if texto is not None else f"{self.alvo:.0f}"
        self.sub = sub
        self.cor = cor or self.cor
        if not self._anim:
            self._anim = True
            self._passo()

    def _passo(self):
        dif = self.alvo - self.atual
        if abs(dif) < 0.4:
            self.atual, self._anim = self.alvo, False
        else:
            self.atual += dif * 0.18
            self.after(16, self._passo)
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        p, t = self.esp / 2 + 4, self.t
        self.create_arc(p, p, t - p, t - p, start=225, extent=-270, style="arc", width=self.esp, outline=T.PANEL2)
        if self.atual > 0.3:
            self.create_arc(p, p, t - p, t - p, start=225, extent=-270 * self.atual / 100, style="arc",
                            width=self.esp, outline=self.cor)
        self.create_text(t / 2, t / 2 - (6 if self.sub else 0), text=self.texto, fill=T.TEXTO,
                         font=T.fonte(max(12, int(t / 5)), True))
        if self.sub:
            self.create_text(t / 2, t / 2 + t / 6, text=self.sub, fill=T.MUDO, font=(T.F, 8))


class Grafico(tk.Canvas):
    """Gráfico de linha em tempo real com preenchimento."""

    def __init__(self, master, cor=T.CIANO, maximo=100, unidade="%", pontos=60, altura=70, **kw):
        super().__init__(master, height=altura, bg=T.PANEL, highlightthickness=0, **kw)
        self.cor, self.maximo, self.unidade = cor, maximo, unidade
        self.dados = deque([None] * pontos, maxlen=pontos)
        self.bind("<Configure>", lambda e: self._desenhar())

    def push(self, v):
        self.dados.append(v)
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20:
            return
        for i in (0.25, 0.5, 0.75):
            self.create_line(0, h * i, w, h * i, fill=T.BORDA)
        n = len(self.dados)
        pts = []
        validos = [d for d in self.dados if d is not None]
        if self.maximo is None:
            teto = max(1.0, max(validos, default=1) * 1.2)
        else:
            teto = self.maximo
        for i, v in enumerate(self.dados):
            if v is None:
                continue
            pts.append((i * w / (n - 1), h - 3 - (h - 8) * min(v, teto) / teto))
        if len(pts) >= 2:
            flat = [c for p in pts for c in p]
            self.create_polygon(pts[0][0], h, *flat, pts[-1][0], h, fill=T.misturar(T.PANEL, self.cor, 0.22), outline="")
            self.create_line(*flat, fill=self.cor, width=2, smooth=True)


def titulo_pagina(master, titulo, sub=""):
    f = tk.Frame(master, bg=T.BG)
    f.pack(fill="x", padx=26, pady=(22, 8))
    tk.Label(f, text=titulo, bg=T.BG, fg=T.TEXTO, font=T.fonte(20, True)).pack(anchor="w")
    if sub:
        tk.Label(f, text=sub, bg=T.BG, fg=T.MUDO, font=T.fonte(10), wraplength=860, justify="left").pack(anchor="w")
    return f


def texto_rolavel(master, altura=10, mono=True):
    f = tk.Frame(master, bg=T.PANEL, highlightthickness=1, highlightbackground=T.BORDA)
    t = tk.Text(f, height=altura, bg=T.PANEL, fg=T.TEXTO, insertbackground=T.CIANO, relief="flat",
                font=T.fonte(9, mono=True) if mono else T.fonte(10), wrap="word", padx=10, pady=8,
                selectbackground="#1d3557", highlightthickness=0, bd=0)
    sb = tk.Scrollbar(f, command=t.yview, bg=T.PANEL2, troughcolor=T.BG, bd=0)
    t.config(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    t.pack(side="left", fill="both", expand=True)
    return f, t
