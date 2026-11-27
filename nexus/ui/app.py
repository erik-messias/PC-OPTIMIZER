"""Janela principal do NEXUS PC: menu lateral, dashboard e páginas."""
import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from .. import cleaning, diagnostics as dg, drivers as drv, hardware as hw, optimize as opt
from .. import repair as rp, startup as st, bottleneck as bn, relatorio as rel, update as up, lhm
from ..core import (APP, HIST, IS_WIN, PASTA, PASTA_REL, VERSAO, carregar_config, fmt_bytes, is_admin, log,
                    plano_ativo, salvar_config)
from . import theme as T
from .widgets import Botao, Cartao, Grafico, Medidor, texto_rolavel, titulo_pagina

MENU = [("dashboard", "Dashboard", "◈"), ("analise", "Análise completa", "⚡"), ("diagnostico", "Diagnóstico", "✚"),
        ("drivers", "Drivers", "⛭"), ("game", "Game Boost", "▶"), ("work", "Work Boost", "▣"),
        ("monitor", "Monitoramento", "∿"), ("reparo", "Reparação do Windows", "⚙"), ("limpeza", "Limpeza", "✦"),
        ("startup", "Inicialização", "⏻"), ("historico", "Histórico", "☰"), ("config", "Configurações", "⚑")]


# =============================================================================== base
class Pagina(tk.Frame):
    def __init__(self, app):
        super().__init__(app.conteudo, bg=T.BG)
        self.app = app

    def on_show(self):
        pass

    def on_sample(self, s):
        pass


def arvore(master, colunas, larguras, altura=10, multi=False):
    """Treeview escuro com barra de rolagem. colunas = [(id, titulo)]"""
    f = tk.Frame(master, bg=T.PANEL, highlightthickness=1, highlightbackground=T.BORDA)
    tv = ttk.Treeview(f, columns=[c[0] for c in colunas], show="headings", height=altura,
                      selectmode="extended" if multi else "browse")
    for (cid, titulo), w in zip(colunas, larguras):
        tv.heading(cid, text=titulo, anchor="w")
        tv.column(cid, width=w, anchor="w", stretch=(w > 150))
    sb = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tv.pack(side="left", fill="both", expand=True)
    for nome, cor in (("crítico", T.VERMELHO), ("alto", T.LARANJA), ("médio", T.AMARELO), ("baixo", T.AZUL),
                      ("info", T.MUDO), ("ok", T.VERDE), ("sus", T.AMARELO)):
        tv.tag_configure(nome, foreground=cor)
    return f, tv


def linha_botoes(master):
    f = tk.Frame(master, bg=T.BG)
    f.pack(fill="x", padx=26, pady=6)
    return f


def barra_progresso(master):
    c = tk.Canvas(master, height=14, bg=T.PANEL2, highlightthickness=0)
    c.valor = 0.0

    def desenhar(v):
        c.valor = v
        c.delete("all")
        w = c.winfo_width()
        c.create_rectangle(0, 0, w * v / 100, 14, fill=T.CIANO, outline="")
        c.create_rectangle(max(0, w * v / 100 - 40), 0, w * v / 100, 14, fill="#67e8f9", outline="", stipple="gray50")
    c.set = desenhar
    return c


# ============================================================================ dashboard
class Dashboard(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Dashboard", "Visão geral do seu computador em tempo real.")
        topo = tk.Frame(self, bg=T.BG)
        topo.pack(fill="x", padx=26, pady=6)
        c1 = Cartao(topo, "Saúde do sistema")
        c1.pack(side="left", fill="y")
        self.saude = Medidor(c1.corpo, 190, 14)
        self.saude.pack()
        self.estado = tk.Label(c1.corpo, text="Execute a análise completa", bg=T.PANEL, fg=T.MUDO, font=T.fonte(10))
        self.estado.pack(pady=(2, 8))
        Botao(c1.corpo, "ANÁLISE COMPLETA DO SISTEMA", lambda: app.ir("analise", iniciar=True), "primario").pack(fill="x")

        c2 = Cartao(topo, "Pontuação por categoria", T.ROXO)
        c2.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.barras = {}
        for cat in dg.CATEGORIAS:
            linha = tk.Frame(c2.corpo, bg=T.PANEL)
            linha.pack(fill="x", pady=5)
            tk.Label(linha, text=cat, width=14, anchor="w", bg=T.PANEL, fg=T.TEXTO, font=T.fonte(10)).pack(side="left")
            cv = tk.Canvas(linha, height=10, bg=T.PANEL2, highlightthickness=0)
            cv.pack(side="left", fill="x", expand=True, padx=8)
            val = tk.Label(linha, text="--", width=4, bg=T.PANEL, fg=T.MUDO, font=T.fonte(10, True))
            val.pack(side="left")
            self.barras[cat] = (cv, val)

        grade = tk.Frame(self, bg=T.BG)
        grade.pack(fill="both", expand=True, padx=26, pady=(6, 10))
        self.g = {}
        defs = [("cpu_temp", "Temp. CPU", T.CIANO), ("gpu_temp", "Temp. GPU", T.ROXO), ("ram", "Memória RAM", T.AZUL),
                ("cpu", "Processador", T.CIANO), ("gpu", "Placa de vídeo", T.ROXO), ("disco", "Disco livre", T.VERDE)]
        for i, (k, nome, cor) in enumerate(defs):
            c = Cartao(grade, nome, cor)
            c.grid(row=i // 4, column=i % 4, sticky="nsew", padx=5, pady=5)
            m = Medidor(c.corpo, 104, 9)
            m.pack()
            m.cor = cor
            self.g[k] = m
        for k, nome, cor in (("problemas", "Problemas", T.AMARELO), ("drivers", "Drivers", T.VERDE)):
            idx = len(self.g)
            c = Cartao(grade, nome, cor)
            c.grid(row=idx // 4, column=idx % 4, sticky="nsew", padx=5, pady=5)
            lbl = tk.Label(c.corpo, text="--", bg=T.PANEL, fg=T.MUDO, font=T.fonte(30, True))
            lbl.pack(pady=(14, 0))
            sub = tk.Label(c.corpo, text="sem análise", bg=T.PANEL, fg=T.MUDO, font=T.fonte(9))
            sub.pack(pady=(0, 16))
            self.g[k] = (lbl, sub)
        for c in range(4):
            grade.columnconfigure(c, weight=1)
        self._n = 0
        self._disco = None

    def on_show(self):
        self.atualizar_analise()

    def atualizar_analise(self):
        a = self.app
        if a.geral is not None:
            self.saude.set(a.geral, str(a.geral), "de 100", T.cor_nota(a.geral))
            self.estado.config(text=T.rotulo_nota(a.geral), fg=T.cor_nota(a.geral))
            for cat, (cv, val) in self.barras.items():
                n = a.notas[cat][0]
                cv.delete("all")
                cv.update_idletasks()
                cv.create_rectangle(0, 0, cv.winfo_width() * n / 100, 10, fill=T.cor_nota(n), outline="")
                val.config(text=str(n), fg=T.cor_nota(n))
            lbl, sub = self.g["problemas"]
            graves = sum(1 for p in a.problemas if p.gravidade in ("crítico", "alto"))
            lbl.config(text=str(len(a.problemas)), fg=T.VERMELHO if graves else T.AMARELO if a.problemas else T.VERDE)
            sub.config(text=f"{graves} graves" if a.problemas else "nenhum problema")
            lbl, sub = self.g["drivers"]
            aten = [p for p in a.problemas if p.categoria == "Drivers" and p.gravidade != "info"]
            lbl.config(text=str(len(aten)) if aten else "OK", fg=T.AMARELO if aten else T.VERDE)
            sub.config(text="precisam de atenção" if aten else "tudo em ordem")

    def on_sample(self, s):
        g = self.g
        ct = s.get("cpu_temp")
        g["cpu_temp"].set(ct or 0, f"{ct:.0f}°" if ct else "N/D", "", T.VERMELHO if (ct or 0) >= 85 else T.CIANO)
        gt = s.get("gpu_temp")
        g["gpu_temp"].set(gt or 0, f"{gt:.0f}°" if gt else "N/D", "", T.VERMELHO if (gt or 0) >= 85 else T.ROXO)
        g["ram"].set(s["ram_pct"], f"{s['ram_pct']:.0f}%", fmt_bytes(s["ram_usada"]),
                     T.VERMELHO if s["ram_pct"] >= 90 else T.AZUL)
        g["cpu"].set(s["cpu"], f"{s['cpu']:.0f}%", f"{s['cpu_freq']:.0f} MHz" if s["cpu_freq"] else "")
        gu = s.get("gpu_util")
        g["gpu"].set(gu or 0, f"{gu:.0f}%" if gu is not None else "N/D")
        self._n += 1
        if self._n % 10 == 1:
            try:
                usos = hw.discos_uso()
                if usos:
                    pior = min(usos, key=lambda u: u[3] / u[1])
                    self._disco = (pior[0], pior[3] / pior[1] * 100, pior[3])
            except Exception:  # noqa: BLE001
                pass
        if self._disco:
            letra, pct, livre = self._disco
            g["disco"].set(pct, f"{pct:.0f}%", f"{letra} {fmt_bytes(livre)}", T.VERMELHO if pct < 10 else T.VERDE)


# ======================================================================= análise completa
class Analise(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Análise completa", "Lê o hardware, o Windows, os drivers e as temperaturas, "
                      "interpreta os resultados e calcula a pontuação de saúde.")
        r = linha_botoes(self)
        self.btn = Botao(r, "⚡ INICIAR ANÁLISE", self.iniciar, "primario")
        self.btn.pack(side="left")
        self.btn_diag = Botao(r, "Ver diagnóstico", lambda: app.ir("diagnostico"))
        self.btn_diag.pack(side="left", padx=8)
        self.btn_rel = Botao(r, "Abrir relatórios", lambda: os.startfile(PASTA_REL) if IS_WIN else None)
        self.btn_rel.pack(side="left")
        Botao(r, "Relatório HTML", app.exportar_html).pack(side="left", padx=8)
        self.pct = tk.Label(self, text="0%", bg=T.BG, fg=T.CIANO, font=T.fonte(26, True))
        self.pct.pack(anchor="w", padx=26)
        self.barra = barra_progresso(self)
        self.barra.pack(fill="x", padx=26, pady=4)
        self.etapa = tk.Label(self, text="Pronto para analisar.", bg=T.BG, fg=T.MUDO, font=T.fonte(10))
        self.etapa.pack(anchor="w", padx=26)
        f, self.txt = texto_rolavel(self, 16)
        f.pack(fill="both", expand=True, padx=26, pady=10)
        self.ocupado = False

    def escrever(self, m):
        self.txt.insert("end", m + "\n")
        self.txt.see("end")

    def iniciar(self):
        if self.ocupado:
            return
        self.ocupado = True
        self.txt.delete("1.0", "end")
        self.btn.ativar(False)
        t0 = time.time()

        def prog(pct, msg):
            self.app.post(lambda: (self.barra.set(pct), self.pct.config(text=f"{pct}%"),
                                   self.etapa.config(text=msg), self.escrever(f"[{pct:>3}%] {msg}")))

        def trabalho():
            ctx = dg.coletar_contexto(prog)
            probs = dg.diagnosticar(ctx)
            geral, notas = dg.pontuar(probs)
            texto = dg.texto_relatorio(ctx, probs, geral, notas)
            arq = PASTA_REL / f"analise_{datetime.now():%Y%m%d_%H%M%S}.txt"
            try:
                arq.write_text(texto, encoding="utf-8")
            except OSError:
                arq = None
            return ctx, probs, geral, notas, arq

        def fim(res):
            ctx, probs, geral, notas, arq = res
            a = self.app
            a.ctx, a.problemas, a.geral, a.notas = ctx, probs, geral, notas
            self.barra.set(100)
            self.pct.config(text="100%")
            self.etapa.config(text=f"Concluída em {time.time() - t0:.0f}s.", fg=T.VERDE)
            self.escrever(f"\nPONTUAÇÃO GERAL: {geral}/100 ({T.rotulo_nota(geral)})")
            for c in dg.CATEGORIAS:
                self.escrever(f"  {c:<15}{notas[c][0]:>4}")
            self.escrever(f"\n{len(probs)} problema(s) encontrado(s)."
                          + (f"\nRelatório salvo em: {arq}" if arq else ""))
            HIST.registrar("Análise completa", "Solicitada pelo usuário", f"Nota {geral}/100, {len(probs)} problemas")
            HIST.registrar_desempenho(geral, {c: notas[c][0] for c in dg.CATEGORIAS}, len(probs))
            self.btn.ativar(True)
            self.ocupado = False

        def erro(e):
            self.escrever(f"ERRO: {e}")
            self.btn.ativar(True)
            self.ocupado = False
        self.app.bg(trabalho, fim, erro)


# ========================================================================== diagnóstico
class Diagnostico(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Diagnóstico inteligente",
                      "Cada problema mostra se é CONFIRMADO (há evidência) ou SUSPEITA (indício), com causas e correção.")
        Botao(linha_botoes(self), "Exportar relatório HTML", app.exportar_html).pack(side="left")
        corpo = tk.Frame(self, bg=T.BG)
        corpo.pack(fill="both", expand=True, padx=26, pady=6)
        esq = tk.Frame(corpo, bg=T.BG)
        esq.pack(side="left", fill="both", expand=True)
        f, self.tv = arvore(esq, [("g", "Gravidade"), ("s", "Situação"), ("c", "Categoria"), ("t", "Problema")],
                            [85, 90, 125, 320], altura=14)
        f.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", self.selecionar)
        dir_ = tk.Frame(corpo, bg=T.BG, width=380)
        dir_.pack(side="left", fill="both", padx=(12, 0))
        f2, self.det = texto_rolavel(dir_, 14, mono=False)
        f2.pack(fill="both", expand=True)
        for k, c in T.GRAVIDADE_COR.items():
            self.det.tag_configure(k, foreground=c, font=T.fonte(12, True))
        self.det.tag_configure("h", foreground=T.CIANO, font=T.fonte(10, True))
        self.det.tag_configure("conf", foreground=T.VERDE)
        self.det.tag_configure("susp", foreground=T.AMARELO)
        c = Cartao(self, "Como a nota foi calculada", T.ROXO)
        c.pack(fill="x", padx=26, pady=(6, 14))
        self.calc = tk.Label(c.corpo, text="Execute a análise completa.", bg=T.PANEL, fg=T.MUDO, font=T.fonte(9),
                             justify="left", anchor="w", wraplength=900)
        self.calc.pack(anchor="w")
        self.lista = []

    def on_show(self):
        a = self.app
        self.tv.delete(*self.tv.get_children())
        self.lista = a.problemas
        for i, p in enumerate(self.lista):
            self.tv.insert("", "end", iid=str(i), values=(p.gravidade, p.status, p.categoria, p.titulo), tags=(p.gravidade,))
        self.det.delete("1.0", "end")
        if a.geral is None:
            self.det.insert("end", "Nenhuma análise feita ainda. Vá em 'Análise completa'.")
            return
        if not self.lista:
            self.det.insert("end", "Nenhum problema encontrado. Excelente!")
        pesos = ", ".join(f"{c} {dg.PESOS[c]}%" for c in dg.CATEGORIAS)
        self.calc.config(text=(
            "Cada categoria começa em 100. Problemas confirmados descontam: crítico -35, alto -20, médio -10, baixo -4; "
            "suspeitas descontam metade. Idade ou modelo do hardware NÃO desconta pontos. "
            f"Pesos da nota geral: {pesos}. Nota geral: {a.geral}/100."))

    def selecionar(self, _):
        sel = self.tv.selection()
        if not sel:
            return
        p = self.lista[int(sel[0])]
        d = self.det
        d.delete("1.0", "end")
        d.insert("end", f"{p.gravidade.upper()}\n", p.gravidade)
        d.insert("end", f"{p.titulo}\n", "h")
        d.insert("end", ("● CONFIRMADO" if p.status == "confirmado" else "○ SUSPEITA") + f"  •  {p.categoria}\n\n",
                 "conf" if p.status == "confirmado" else "susp")
        d.insert("end", "O que está acontecendo\n", "h")
        d.insert("end", p.explicacao + "\n\n")
        if p.causas:
            d.insert("end", "Possíveis causas\n", "h")
            d.insert("end", "\n".join("• " + c for c in p.causas) + "\n\n")
        if p.recomendacao:
            d.insert("end", "Recomendação\n", "h")
            d.insert("end", p.recomendacao + "\n")
        if p.evidencia:
            d.insert("end", "\nEvidência: ", "h")
            d.insert("end", p.evidencia)


# ============================================================================== drivers
class Drivers(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Central inteligente de drivers",
                      "Identifica drivers ausentes, genéricos e antigos. Nada é instalado sem a sua aprovação.")
        r = linha_botoes(self)
        Botao(r, "1  Ler drivers", self.ler, "primario").pack(side="left")
        Botao(r, "2  Windows Update", self.buscar).pack(side="left", padx=6)
        Botao(r, "3  Instalar selecionados", self.instalar).pack(side="left")
        Botao(r, "Gerenc. de Dispositivos", lambda: os.startfile("devmgmt.msc") if IS_WIN else None).pack(side="left", padx=6)
        self.btn_gpu = Botao(r, "Site da placa de vídeo", self.site_gpu)
        self.btn_gpu.pack(side="left")
        self.so_aten = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Mostrar só os que precisam de atenção", variable=self.so_aten, command=self.popular,
                       bg=T.BG, fg=T.TEXTO, selectcolor=T.PANEL2, activebackground=T.BG, activeforeground=T.TEXTO,
                       font=T.fonte(10)).pack(anchor="w", padx=26)
        f, self.tv = arvore(self, [("s", "Situação"), ("n", "Dispositivo"), ("c", "Classe"), ("f", "Fabricante"),
                                   ("v", "Versão"), ("d", "Data")], [90, 280, 80, 220, 130, 90], altura=9)
        f.pack(fill="both", expand=True, padx=26, pady=4)
        tk.Label(self, text="Atualizações disponíveis (Windows Update) — selecione e clique em 'Instalar selecionados'",
                 bg=T.BG, fg=T.CIANO, font=T.fonte(10, True)).pack(anchor="w", padx=26, pady=(6, 0))
        f2, self.tv_wu = arvore(self, [("n", "Driver"), ("f", "Fabricante"), ("c", "Classe"), ("d", "Data"), ("t", "Tamanho")],
                                [360, 170, 100, 90, 90], altura=5, multi=True)
        f2.pack(fill="x", padx=26, pady=4)
        self.status = tk.Label(self, text="", bg=T.BG, fg=T.MUDO, font=T.fonte(9), anchor="w", justify="left", wraplength=1000)
        self.status.pack(fill="x", padx=26, pady=(2, 10))
        self.drivers, self.erros, self.wu = [], [], []

    def msg(self, t, cor=T.MUDO):
        self.status.config(text=t, fg=cor)

    def ler(self):
        self.msg("Lendo drivers (pode levar até 1 minuto)...", T.CIANO)

        def fim(res):
            self.drivers, erros = res
            self.erros = drv.classificar_erros(erros)
            self.app.drivers, self.app.erros_pnp = self.drivers, self.erros
            self.popular()
            aten = sum(1 for d in self.drivers if d["status"] != "ok") + len(self.erros)
            self.msg(f"{len(self.drivers)} drivers lidos; {aten} precisam de atenção.", T.VERDE if not aten else T.AMARELO)
        self.app.bg(drv.ler_drivers, fim, lambda e: self.msg(f"Erro: {e}", T.VERMELHO))

    def popular(self):
        self.tv.delete(*self.tv.get_children())
        for e in self.erros:
            self.tv.insert("", "end", values=("ERRO", e["nome"], e["classe"], e["causa"][:38], f"código {e['codigo']}", ""),
                           tags=("crítico",))
        nomes = {"ok": ("OK", "ok"), "generico": ("GENÉRICO", "médio"), "antigo": ("ANTIGO", "baixo")}
        for d in sorted(self.drivers, key=lambda x: (x["status"] == "ok", x.get("DeviceClass") or "")):
            if self.so_aten.get() and d["status"] == "ok":
                continue
            rot, tag = nomes[d["status"]]
            self.tv.insert("", "end", values=(rot, d.get("DeviceName"), d.get("DeviceClass"),
                                              d.get("DriverProviderName") or d.get("Manufacturer") or "", d.get("DriverVersion"),
                                              d.get("data")), tags=(tag,))

    def buscar(self):
        self.msg("Procurando drivers no Windows Update (pode levar alguns minutos)...", T.CIANO)

        def fim(res):
            if res is None:
                self.msg("Não foi possível consultar o Windows Update. Verifique a internet.", T.VERMELHO)
                return
            self.wu = res
            self.tv_wu.delete(*self.tv_wu.get_children())
            for i, w in enumerate(res):
                self.tv_wu.insert("", "end", iid=str(i), values=(w.get("titulo"), w.get("fab"), w.get("classe"),
                                                                 w.get("data"), fmt_bytes(w.get("tamanho"))))
            self.msg(f"{len(res)} driver(s) disponível(is)." if res else "Nenhum driver pendente. Tudo atualizado pelo Windows Update.",
                     T.AMARELO if res else T.VERDE)
        self.app.bg(drv.buscar_atualizacoes, fim, lambda e: self.msg(f"Erro: {e}", T.VERMELHO))

    def instalar(self):
        sel = [self.wu[int(i)] for i in self.tv_wu.selection()]
        if not sel:
            messagebox.showinfo(APP, "Selecione na lista de baixo os drivers que deseja instalar.")
            return
        lista = "\n".join("• " + (s.get("titulo") or "")[:90] for s in sel[:12])
        if not messagebox.askyesno(APP, f"Instalar {len(sel)} driver(s)?\n\n{lista}\n\n"
                                        "Antes será criado um ponto de restauração e os drivers atuais serão salvos.\n"
                                        "Riscos: um driver novo pode, raramente, causar instabilidade. "
                                        "Você aprova a instalação?"):
            return
        self.msg("Instalando...", T.CIANO)

        def prog(m):
            self.app.post(lambda: self.msg(m, T.CIANO))

        def fim(res):
            ok, texto, reiniciar = res
            self.msg(texto, T.VERDE if ok else T.VERMELHO)
            if reiniciar:
                messagebox.showinfo(APP, "É preciso REINICIAR o PC para concluir a instalação dos drivers.")
        self.app.bg(lambda: drv.instalar_atualizacoes(sel, self.drivers, prog), fim,
                    lambda e: self.msg(f"Erro: {e}", T.VERMELHO))

    def site_gpu(self):
        nomes = [d.get("DeviceName") for d in self.drivers if (d.get("DeviceClass") or "").upper() == "DISPLAY"]
        if not nomes and self.app.ctx:
            nomes = [g.get("Name") for g in self.app.ctx["inv"].get("gpu", [])]
        for n in nomes:
            m = drv.marca_gpu(n)
            if m:
                webbrowser.open(m[1])
                self.msg(f"Aberto o site oficial {m[0]}. Baixe SOMENTE do site do fabricante.", T.VERDE)
                return
        self.msg("Leia os drivers primeiro (botão 1) para detectar a placa de vídeo.", T.AMARELO)


# =============================================================================== boost
class PainelProcessos(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        f, self.tv = arvore(self, [("n", "Processo"), ("p", "PID"), ("m", "Memória")], [260, 80, 110], altura=7)
        f.pack(fill="both", expand=True)
        r = tk.Frame(self, bg=T.BG)
        r.pack(fill="x", pady=4)
        Botao(r, "↻ Atualizar", self.atualizar).pack(side="left")
        Botao(r, "Encerrar selecionado", self.encerrar, "perigo").pack(side="left", padx=6)

    def atualizar(self):
        self.tv.delete(*self.tv.get_children())
        for n, pid, ram, _ in hw.top_processos(12):
            self.tv.insert("", "end", values=(n, pid, fmt_bytes(ram)))

    def encerrar(self):
        sel = self.tv.selection()
        if not sel:
            return
        n, pid, _ = self.tv.item(sel[0], "values")
        if messagebox.askyesno(APP, f"Encerrar '{n}'?\nTrabalho não salvo nele será perdido."):
            ok, m = opt.encerrar_processo(int(pid), n)
            messagebox.showinfo(APP, m)
            self.atualizar()


class GameBoost(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Game Boost", "Perfis de desempenho para jogos. Toda mudança é registrada e pode ser desfeita no Histórico.")
        r = linha_botoes(self)
        for chave, p in opt.PERFIS.items():
            Botao(r, p["nome"], lambda c=chave: self.perfil(c), "primario" if chave == "maximo" else "sec").pack(side="left", padx=(0, 6))
        self.plano = tk.Label(self, text="", bg=T.BG, fg=T.CIANO, font=T.fonte(10, True))
        self.plano.pack(anchor="w", padx=26)
        self.desc = tk.Label(self, text="Escolha um perfil acima.", bg=T.BG, fg=T.MUDO, font=T.fonte(10))
        self.desc.pack(anchor="w", padx=26)
        corpo = tk.Frame(self, bg=T.BG)
        corpo.pack(fill="both", expand=True, padx=26, pady=8)
        esq = Cartao(corpo, "Processos que mais usam memória")
        esq.pack(side="left", fill="both", expand=True)
        self.proc = PainelProcessos(esq.corpo, app)
        self.proc.pack(fill="both", expand=True)
        dir_ = Cartao(corpo, "Recomendações para o seu hardware", T.ROXO)
        dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
        f, self.dicas = texto_rolavel(dir_.corpo, 9, mono=False)
        f.pack(fill="both", expand=True)
        r2 = linha_botoes(self)
        Botao(r2, "🎮 Contador de FPS", self.fps).pack(side="left")
        Botao(r2, "Usar GPU potente em um jogo…", self.gpu).pack(side="left", padx=6)
        Botao(r2, "★ Meus perfis…", lambda: DialogoPerfis(app)).pack(side="left")
        self.overlay = None
        self.perfil_atual = "equilibrado"

    def on_show(self):
        self.plano.config(text=f"Plano de energia atual: {plano_ativo()[1] or 'desconhecido'}")
        self.proc.atualizar()
        self.mostrar_dicas()

    def mostrar_dicas(self):
        self.dicas.delete("1.0", "end")
        if not self.app.ctx:
            self.dicas.insert("end", "Execute a Análise completa para receber recomendações específicas do seu hardware.")
            return
        for d in opt.dicas_graficas(self.app.ctx["inv"], self.perfil_atual):
            self.dicas.insert("end", "• " + d + "\n\n")

    def perfil(self, chave):
        p = opt.PERFIS[chave]
        self.perfil_atual = chave
        self.desc.config(text=p["desc"])
        ok, m = opt.aplicar_perfil(chave)
        self.plano.config(text=f"Plano de energia atual: {plano_ativo()[1]}" if ok else m, fg=T.CIANO if ok else T.VERMELHO)
        self.mostrar_dicas()

    def fps(self):
        from .fps import FpsOverlay
        if self.overlay and self.overlay.rodando:
            return
        self.overlay = FpsOverlay(self.app)

    def gpu(self):
        exe = filedialog.askopenfilename(title="Escolha o .exe do jogo", filetypes=[("Programa", "*.exe")])
        if exe:
            ok, m = opt.definir_gpu_alta(exe)
            messagebox.showinfo(APP, m + ("\nPode desfazer no Histórico." if ok else ""))


class WorkBoost(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Work Boost", "Perfis para trabalho. O plano de energia é trocado (reversível no Histórico) "
                      "e você recebe recomendações para o seu hardware e para o que está aberto agora.")
        r = linha_botoes(self)
        for chave, p in opt.WORK_PERFIS.items():
            Botao(r, p["curto"], lambda c=chave: self.perfil(c), "primario" if chave == "escritorio" else "sec").pack(side="left", padx=(0, 6))
        self.estado = tk.Label(self, text="Escolha o tipo de trabalho.", bg=T.BG, fg=T.CIANO, font=T.fonte(10, True))
        self.estado.pack(anchor="w", padx=26)
        corpo = tk.Frame(self, bg=T.BG)
        corpo.pack(fill="both", expand=True, padx=26, pady=8)
        esq = Cartao(corpo, "Maiores consumidores de memória")
        esq.pack(side="left", fill="both", expand=True)
        self.proc = PainelProcessos(esq.corpo, app)
        self.proc.pack(fill="both", expand=True)
        dir_ = Cartao(corpo, "Recomendações", T.ROXO)
        dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
        f, self.dicas = texto_rolavel(dir_.corpo, 10, mono=False)
        f.pack(fill="both", expand=True)
        self.chave = None

    def on_show(self):
        self.proc.atualizar()
        self.mostrar()

    def mostrar(self):
        self.dicas.delete("1.0", "end")
        if not self.chave:
            self.dicas.insert("end", "Selecione um perfil acima.")
            return
        inv = self.app.ctx["inv"] if self.app.ctx else {}
        for d in opt.dicas_trabalho(self.chave, inv, hw.top_processos(6)):
            self.dicas.insert("end", "• " + d + "\n\n")
        if not self.app.ctx:
            self.dicas.insert("end", "(Faça a Análise completa para recomendações mais precisas.)")

    def perfil(self, chave):
        self.chave = chave
        ok, m = opt.aplicar_work(chave)
        self.estado.config(text=f"{opt.WORK_PERFIS[chave]['nome']}: {m}", fg=T.CIANO if ok else T.VERMELHO)
        self.mostrar()


# ========================================================================== monitoramento
class Monitor(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Monitoramento em tempo real", "Atualiza a cada segundo. Temperatura de CPU: abra o LibreHardwareMonitor para leitura precisa.")
        g = tk.Frame(self, bg=T.BG)
        g.pack(fill="both", expand=True, padx=26, pady=6)
        defs = [("cpu", "CPU uso", T.CIANO, 100, "%"), ("cpu_temp", "CPU temperatura", T.LARANJA, 110, "°C"),
                ("cpu_freq", "CPU frequência", T.AZUL, None, " MHz"), ("ram_pct", "Memória RAM", T.ROXO, 100, "%"),
                ("gpu_util", "GPU uso", T.VERDE, 100, "%"), ("gpu_temp", "GPU temperatura", T.LARANJA, 110, "°C"),
                ("vram", "GPU VRAM", T.ROXO, 100, "%"), ("disco_leitura", "Disco leitura", T.AZUL, None, " MB/s"),
                ("disco_escrita", "Disco escrita", T.CIANO, None, " MB/s")]
        self.graf, self.val = {}, {}
        for i, (k, nome, cor, mx, un) in enumerate(defs):
            c = Cartao(g, nome, cor)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=5, pady=5)
            v = tk.Label(c.corpo, text="--", bg=T.PANEL, fg=T.TEXTO, font=T.fonte(18, True))
            v.pack(anchor="w")
            gr = Grafico(c.corpo, cor, mx, un)
            gr.pack(fill="x")
            self.graf[k], self.val[k] = gr, (v, un)
        for c in range(3):
            g.columnconfigure(c, weight=1)
        self.info = tk.Label(self, text="", bg=T.BG, fg=T.MUDO, font=T.fonte(9), justify="left", anchor="w", wraplength=1000)
        self.info.pack(fill="x", padx=26, pady=(0, 4))
        r = linha_botoes(self)
        self.btn_rec = Botao(r, "● Gravar sessão", self.alternar_gravacao, "primario")
        self.btn_rec.pack(side="left")
        self.rec_lbl = tk.Label(r, text="Grave enquanto joga ou trabalha para descobrir o que limita o desempenho.",
                                bg=T.BG, fg=T.MUDO, font=T.fonte(9))
        self.rec_lbl.pack(side="left", padx=10)

    def alternar_gravacao(self):
        g = self.app.gravador
        if not g.ativo:
            g.iniciar()
            self.btn_rec.config(text="■ Parar e analisar")
            self.rec_lbl.config(text="Gravando... pode minimizar o NEXUS PC e jogar.", fg=T.VERMELHO)
            return
        dur = g.parar()
        self.btn_rec.config(text="● Gravar sessão")
        r, achados = bn.analisar(g.amostras)
        texto = bn.texto(r, achados, dur)
        HIST.registrar_sessao("Sessão gravada", dur, {"resumo": r, "achados": [list(a) for a in achados]})
        HIST.registrar("Sessão analisada", f"{dur / 60:.1f} min", f"{len(achados)} achado(s)")
        self.rec_lbl.config(text="Sessão salva no Histórico > Desempenho.", fg=T.VERDE)
        self.app.janela_texto("Análise de gargalos da sessão", texto)

    def on_sample(self, s):
        g = self.app.gravador
        if g.ativo:
            self.rec_lbl.config(text=f"● Gravando {g.duracao:.0f}s ({len(g.amostras)} amostras)", fg=T.VERMELHO)
        vram = None
        if s.get("gpu_vram") and s["gpu_vram"][1]:
            vram = s["gpu_vram"][0] / s["gpu_vram"][1] * 100
        vals = {k: s.get(k) for k in self.graf}
        vals["vram"] = vram
        for k, v in vals.items():
            self.graf[k].push(v)
            lbl, un = self.val[k]
            lbl.config(text=f"{v:.0f}{un}" if v is not None else "N/D")
        n = os.cpu_count() or 0
        extra = []
        if s.get("cpu_consumo") is not None:
            extra.append(f"CPU consumo {s['cpu_consumo']:.0f} W")
        if s.get("disco_temp") is not None:
            extra.append(f"disco {s['disco_temp']:.0f} °C")
        if s.get("ventoinhas"):
            extra.append("ventoinhas " + ", ".join(f"{n} {v:.0f} RPM" for n, v in s["ventoinhas"][:3]))
        if s.get("gpu_consumo") is not None:
            extra.append(f"GPU consumo {s['gpu_consumo']:.0f} W")
        if s.get("gpu_freq"):
            extra.append(f"GPU {s['gpu_freq']:.0f} MHz")
        if s.get("gpu_fan") is not None:
            extra.append(f"ventoinha GPU {s['gpu_fan']:.0f}%")
        fontes = ", ".join(s.get("fontes") or []) or "nenhuma (instale o driver em Configurações > Sensores)"
        partes = [f"Threads lógicas: {n}", f"RAM {fmt_bytes(s['ram_usada'])} / {fmt_bytes(s['ram_total'])}"] + extra
        self.info.config(text=" • ".join(partes) + f"\nFonte de temperatura da CPU: {fontes}")


# ============================================================================= reparação
class Reparo(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Reparação do Windows", "Ferramentas oficiais do próprio Windows. Cada uma é explicada antes de rodar. "
                      "Itens com ⚠ alteram o sistema e pedem confirmação. Exigem Administrador.")
        corpo = tk.Frame(self, bg=T.BG)
        corpo.pack(fill="both", expand=True, padx=26, pady=6)
        esq = tk.Frame(corpo, bg=T.BG, width=330)
        esq.pack(side="left", fill="y")
        self.sel = tk.StringVar(value="sfc_verificar")
        for chave, f in rp.FERRAMENTAS.items():
            tk.Radiobutton(esq, text=f["nome"] + (" ⚠" if f["altera"] else ""), variable=self.sel, value=chave,
                           command=self.descrever, bg=T.BG, fg=T.TEXTO, selectcolor=T.PANEL2, activebackground=T.BG,
                           activeforeground=T.CIANO, font=T.fonte(10), anchor="w", justify="left", wraplength=320,
                           highlightthickness=0, bd=0).pack(fill="x", pady=3)
        self.desc = tk.Label(esq, text="", bg=T.PANEL, fg=T.MUDO, font=T.fonte(9), wraplength=310, justify="left",
                             anchor="nw", padx=10, pady=8, highlightthickness=1, highlightbackground=T.BORDA)
        self.desc.pack(fill="x", pady=8)
        self.btn = Botao(esq, "▶ EXECUTAR", self.executar, "primario")
        self.btn.pack(fill="x")
        self.cancelar = False
        Botao(esq, "Cancelar", lambda: setattr(self, "cancelar", True)).pack(fill="x", pady=(6, 14))
        tk.Label(esq, text="Outras ferramentas", bg=T.BG, fg=T.CIANO, font=T.fonte(10, True)).pack(anchor="w")
        for nome, cmd in (("Visualizador de Eventos", "eventvwr.msc"), ("Diagnóstico de Memória", "mdsched.exe"),
                          ("Windows Update", "ms-settings:windowsupdate"), ("Gerenciador de Dispositivos", "devmgmt.msc")):
            Botao(esq, nome, lambda c=cmd: os.startfile(c) if IS_WIN else None).pack(fill="x", pady=2)
        dir_ = tk.Frame(corpo, bg=T.BG)
        dir_.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.resultado = tk.Label(dir_, text="Escolha uma ferramenta e clique em Executar.", bg=T.BG, fg=T.MUDO,
                                  font=T.fonte(11, True), anchor="w", justify="left", wraplength=620)
        self.resultado.pack(fill="x")
        f, self.txt = texto_rolavel(dir_, 18)
        f.pack(fill="both", expand=True, pady=6)
        self.ocupado = False
        self.descrever()

    def descrever(self):
        f = rp.FERRAMENTAS[self.sel.get()]
        self.desc.config(text=f"{f['desc']}\n\nTempo estimado: {f['tempo']}.")

    def executar(self):
        if self.ocupado:
            return
        chave = self.sel.get()
        f = rp.FERRAMENTAS[chave]
        if not IS_WIN:
            messagebox.showinfo(APP, "Disponível somente no Windows.")
            return
        if not is_admin():
            messagebox.showwarning(APP, "Execute o NEXUS PC como Administrador para usar esta ferramenta.")
            return
        if f["altera"] and not messagebox.askyesno(APP, f"{f['nome']}\n\n{f['desc']}\n\nDemora {f['tempo']}. Deseja continuar?"):
            return
        self.ocupado, self.cancelar = True, False
        self.txt.delete("1.0", "end")
        self.resultado.config(text="Executando... não feche o programa.", fg=T.CIANO)

        def linha(t):
            self.app.post(lambda: (self.txt.insert("end", t + "\n"), self.txt.see("end")))

        def trabalho():
            return rp.executar(chave, linha, lambda: self.cancelar)

        def fim(res):
            cod, texto = res
            estado, msg = rp.interpretar(chave, cod, texto)
            cor = {"ok": T.VERDE, "reparado": T.VERDE, "problema": T.AMARELO, "erro": T.VERMELHO}[estado]
            self.resultado.config(text=msg, fg=cor)
            self.ocupado = False

        def erro(e):
            self.resultado.config(text=f"Erro: {e}", fg=T.VERMELHO)
            self.ocupado = False
        self.app.bg(trabalho, fim, erro)


# ================================================================================ limpeza
class Limpeza(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Limpeza inteligente", "Veja o que será removido, onde está e quais as consequências. "
                      "Documentos pessoais e arquivos de jogos nunca são tocados.")
        r = linha_botoes(self)
        Botao(r, "🔍 Analisar", self.analisar, "primario").pack(side="left")
        Botao(r, "Limpar selecionados", self.limpar).pack(side="left", padx=6)
        self.total = tk.Label(r, text="", bg=T.BG, fg=T.VERDE, font=T.fonte(11, True))
        self.total.pack(side="left", padx=12)
        self.lista = tk.Frame(self, bg=T.BG)
        self.lista.pack(fill="both", expand=True, padx=26, pady=6)
        self.vars, self.cats = {}, []

    def analisar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        tk.Label(self.lista, text="Analisando...", bg=T.BG, fg=T.CIANO).pack(anchor="w")

        def fim(cats):
            self.cats = cats
            for w in self.lista.winfo_children():
                w.destroy()
            self.vars = {}
            total = 0
            for c in cats:
                v = tk.BooleanVar(value=c["padrao"])
                self.vars[c["chave"]] = v
                caixa = Cartao(self.lista)
                caixa.pack(fill="x", pady=3)
                topo = tk.Frame(caixa.corpo, bg=T.PANEL)
                topo.pack(fill="x")
                tk.Checkbutton(topo, text=c["nome"], variable=v, bg=T.PANEL, fg=T.TEXTO, selectcolor=T.PANEL2,
                               activebackground=T.PANEL, activeforeground=T.TEXTO, font=T.fonte(10, True),
                               command=self.somar).pack(side="left")
                tk.Label(topo, text=f"{fmt_bytes(c['bytes'])} • {c['arquivos']} itens", bg=T.PANEL,
                         fg=T.CIANO, font=T.fonte(10, True)).pack(side="right")
                tk.Label(caixa.corpo, text=f"Onde: {c['locais'][:110]}", bg=T.PANEL, fg=T.MUDO, font=T.fonte(8),
                         anchor="w").pack(fill="x")
                tk.Label(caixa.corpo, text=f"Consequência: {c['consequencia']}", bg=T.PANEL, fg=T.ROXO, font=T.fonte(9),
                         anchor="w", wraplength=900, justify="left").pack(fill="x")
            self.somar()
        self.app.bg(cleaning.analisar, fim)

    def somar(self):
        t = sum(c["bytes"] for c in self.cats if self.vars.get(c["chave"]) and self.vars[c["chave"]].get())
        self.total.config(text=f"Poderá liberar: {fmt_bytes(t)}")

    def limpar(self):
        escolhidas = [k for k, v in self.vars.items() if v.get()]
        if not escolhidas:
            messagebox.showinfo(APP, "Analise e marque o que deseja limpar.")
            return
        cfg = carregar_config()
        if "navegadores" in escolhidas and not cfg.get("limpar_navegadores"):
            if not messagebox.askyesno(APP, "Limpar o cache dos navegadores?\nFeche-os antes. Senhas e histórico não são apagados."):
                escolhidas.remove("navegadores")
            else:
                cfg["limpar_navegadores"] = True
                salvar_config(cfg)
        if not escolhidas or not messagebox.askyesno(APP, f"Remover {len(escolhidas)} categoria(s) selecionada(s)?"):
            return

        def fim(b):
            self.total.config(text=f"Liberado: {fmt_bytes(b)}")
            messagebox.showinfo(APP, f"{fmt_bytes(b)} liberados.")
        self.app.bg(lambda: cleaning.limpar(escolhidas), fim)


# ============================================================================ inicialização
class Inicializacao(Pagina):
    REC = {"suspeito": ("SUSPEITO", "crítico"), "desativar": ("pode desativar", "médio"), "avaliar": ("avaliar", "baixo"),
           "manter": ("manter", "ok"), "proteger": ("essencial", "ok")}

    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Gerenciador de inicialização",
                      "Programas que abrem junto com o Windows. Desativar é reversível e não apaga nada "
                      "(é o mesmo mecanismo do Gerenciador de Tarefas).")
        r = linha_botoes(self)
        Botao(r, "Desativar selecionado", lambda: self.alternar(False), "primario").pack(side="left")
        Botao(r, "Reativar selecionado", lambda: self.alternar(True)).pack(side="left", padx=6)
        Botao(r, "↻ Atualizar", self.on_show).pack(side="left")
        self.msg = tk.Label(r, text="", bg=T.BG, fg=T.MUDO, font=T.fonte(9))
        self.msg.pack(side="left", padx=10)
        f, self.tv = arvore(self, [("e", "Estado"), ("n", "Nome"), ("f", "Fabricante"), ("r", "RAM agora"),
                                   ("o", "Origem"), ("a", "Recomendação")], [100, 190, 170, 90, 130, 130], altura=13)
        f.pack(fill="both", expand=True, padx=26, pady=6)
        self.tv.bind("<<TreeviewSelect>>", self.detalhe)
        self.det = tk.Label(self, text="", bg=T.PANEL, fg=T.MUDO, font=T.fonte(9), anchor="w", justify="left", wraplength=1000,
                            padx=12, pady=8, highlightthickness=1, highlightbackground=T.BORDA)
        self.det.pack(fill="x", padx=26, pady=(0, 14))
        self.itens = []

    def on_show(self):
        self.msg.config(text="Lendo...", fg=T.CIANO)

        def fim(itens):
            self.itens = itens
            self.tv.delete(*self.tv.get_children())
            for i, it in enumerate(itens):
                rot, tag = self.REC[it["rec"]]
                self.tv.insert("", "end", iid=str(i), tags=(tag,) if it["habilitado"] else ("info",),
                               values=("ATIVO" if it["habilitado"] else "desativado", it["nome"], it["fab"] or "—",
                                       fmt_bytes(it["ram"]) if it["ram"] else "—", it["origem"], rot))
            ativos = sum(1 for x in itens if x["habilitado"])
            self.msg.config(text=f"{ativos} ativo(s) de {len(itens)}", fg=T.MUDO)
        self.app.bg(st.listar, fim, lambda e: self.msg.config(text=f"Erro: {e}", fg=T.VERMELHO))

    def detalhe(self, _):
        sel = self.tv.selection()
        if sel:
            it = self.itens[int(sel[0])]
            self.det.config(text=f"{it['motivo']}\nComando: {it['cmd']}")

    def alternar(self, habilitar):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo(APP, "Selecione um programa na lista.")
            return
        it = self.itens[int(sel[0])]
        if not habilitar and not messagebox.askyesno(APP, f"Desativar '{it['nome']}' na inicialização?\n\n{it['motivo']}\n\n"
                                                         "Você pode reativar a qualquer momento."):
            return
        ok, m = st.alternar(it, habilitar)
        self.msg.config(text=m, fg=T.VERDE if ok else T.VERMELHO)
        if ok:
            self.on_show()


# ============================================================================== histórico
class Historico(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Histórico", "Alterações feitas pelo NEXUS PC (reversíveis) e a evolução do desempenho do seu computador.")
        r = linha_botoes(self)
        self.b1 = Botao(r, "Alterações", lambda: self.modo("alt"), "primario")
        self.b1.pack(side="left")
        self.b2 = Botao(r, "Desempenho", lambda: self.modo("des"))
        self.b2.pack(side="left", padx=6)
        # --- alterações
        self.f_alt = tk.Frame(self, bg=T.BG)
        f, self.tv = arvore(self.f_alt, [("i", "#"), ("d", "Data"), ("a", "Alteração"), ("m", "Motivo"), ("r", "Resultado"), ("v", "Reversível")],
                            [40, 140, 170, 260, 260, 90], altura=15)
        f.pack(fill="both", expand=True, padx=26, pady=8)
        r2 = tk.Frame(self.f_alt, bg=T.BG)
        r2.pack(fill="x", padx=26)
        Botao(r2, "↶ Reverter selecionado", self.reverter, "primario").pack(side="left")
        Botao(r2, "Abrir pasta de logs", lambda: os.startfile(PASTA) if IS_WIN else None).pack(side="left", padx=6)
        # --- desempenho
        self.f_des = tk.Frame(self, bg=T.BG)
        c = Cartao(self.f_des, "Evolução da nota de saúde (0-100)")
        c.pack(fill="x", padx=26, pady=8)
        self.graf = Grafico(c.corpo, T.CIANO, 100, "", pontos=30, altura=110)
        self.graf.pack(fill="x")
        self.resumo = tk.Label(c.corpo, text="", bg=T.PANEL, fg=T.MUDO, font=T.fonte(9), anchor="w")
        self.resumo.pack(fill="x")
        f2, self.tv2 = arvore(self.f_des, [("d", "Data"), ("t", "Tipo"), ("n", "Resultado")], [165, 150, 600], altura=9)
        f2.pack(fill="both", expand=True, padx=26, pady=4)
        self.modo("alt")

    def modo(self, m):
        self.f_alt.pack_forget()
        self.f_des.pack_forget()
        (self.f_alt if m == "alt" else self.f_des).pack(fill="both", expand=True)
        self.b1.marcar(m == "alt")
        self.b2.marcar(m == "des")

    def on_show(self):
        self.tv.delete(*self.tv.get_children())
        for id_, data, acao, motivo, res, rev, revertido, _ in HIST.listar():
            estado = "revertido" if revertido else ("sim" if rev else "não")
            self.tv.insert("", "end", iid=str(id_), values=(id_, data.replace("T", " "), acao, motivo, res, estado))
        self.tv2.delete(*self.tv2.get_children())
        analises = HIST.listar_desempenho(30)
        self.graf.dados.clear()
        self.graf.dados.extend([None] * (30 - len(analises)) + [a[1] for a in analises])
        self.graf._desenhar()
        if len(analises) >= 2:
            dif = analises[-1][1] - analises[0][1]
            self.resumo.config(text=f"{len(analises)} análises • primeira {analises[0][1]} → última {analises[-1][1]} ({dif:+d})")
        else:
            self.resumo.config(text="Faça análises completas ao longo do tempo para ver a evolução.")
        linhas = [(d, "Análise completa", f"Nota {g}/100 • {p} problema(s) • " + ", ".join(f"{k} {v}" for k, v in n.items()))
                  for d, g, n, p in analises]
        for d, nome, dur, res in HIST.listar_sessoes(15):
            r = res.get("resumo", {})
            fmtv = lambda v: "N/D" if v is None else f"{v:.0f}%"  # noqa: E731
            linhas.append((d, "Sessão gravada", f"{dur / 60:.1f} min • CPU {fmtv(r.get('cpu_med'))} • GPU {fmtv(r.get('gpu_med'))} • "
                           + "; ".join(a[0] for a in res.get("achados", [])[:2])))
        for d, t, n in sorted(linhas, reverse=True):
            self.tv2.insert("", "end", values=(d.replace("T", " "), t, n))

    def reverter(self):
        sel = self.tv.selection()
        if not sel:
            return
        ok, m = HIST.reverter(int(sel[0]))
        messagebox.showinfo(APP, m)
        self.on_show()


class DialogoPerfis(tk.Toplevel):
    """Perfis personalizados: plano de energia + lista de programas que você costuma fechar."""
    PLANOS = {"Máximo desempenho": "maximo", "Equilibrado": "equilibrado", "Economia de energia": "economia"}

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Meus perfis")
        self.configure(bg=T.BG)
        self.geometry("620x470")
        self.cfg = carregar_config()
        tk.Label(self, text="Meus perfis", bg=T.BG, fg=T.TEXTO, font=T.fonte(16, True)).pack(anchor="w", padx=18, pady=(14, 0))
        tk.Label(self, text="Ao aplicar, troca o plano de energia (reversível) e oferece fechar os programas listados.",
                 bg=T.BG, fg=T.MUDO, font=T.fonte(9)).pack(anchor="w", padx=18)
        corpo = tk.Frame(self, bg=T.BG)
        corpo.pack(fill="both", expand=True, padx=18, pady=10)
        self.lista = tk.Listbox(corpo, bg=T.PANEL, fg=T.TEXTO, selectbackground="#1d3557", relief="flat", highlightthickness=1,
                                highlightbackground=T.BORDA, width=20, font=T.fonte(10), exportselection=False)
        self.lista.pack(side="left", fill="y")
        self.lista.bind("<<ListboxSelect>>", self.carregar)
        dir_ = tk.Frame(corpo, bg=T.BG)
        dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
        tk.Label(dir_, text="Nome", bg=T.BG, fg=T.CIANO, font=T.fonte(9, True)).pack(anchor="w")
        self.nome = tk.Entry(dir_, bg=T.PANEL2, fg=T.TEXTO, insertbackground=T.CIANO, relief="flat", font=T.fonte(10))
        self.nome.pack(fill="x", ipady=4)
        tk.Label(dir_, text="Plano de energia", bg=T.BG, fg=T.CIANO, font=T.fonte(9, True)).pack(anchor="w", pady=(8, 0))
        self.plano = ttk.Combobox(dir_, values=list(self.PLANOS), state="readonly")
        self.plano.set("Equilibrado")
        self.plano.pack(fill="x")
        tk.Label(dir_, text="Programas para fechar (um por linha, ex.: chrome.exe)", bg=T.BG, fg=T.CIANO,
                 font=T.fonte(9, True)).pack(anchor="w", pady=(8, 0))
        self.procs = tk.Text(dir_, height=8, bg=T.PANEL2, fg=T.TEXTO, insertbackground=T.CIANO, relief="flat", font=T.fonte(10, mono=True))
        self.procs.pack(fill="both", expand=True)
        r = tk.Frame(self, bg=T.BG)
        r.pack(fill="x", padx=18, pady=(0, 14))
        Botao(r, "Novo", self.novo).pack(side="left")
        Botao(r, "Salvar", self.salvar, "primario").pack(side="left", padx=6)
        Botao(r, "Aplicar", self.aplicar).pack(side="left")
        Botao(r, "Excluir", self.excluir, "perigo").pack(side="left", padx=6)
        self.atualizar()

    def atualizar(self):
        self.lista.delete(0, "end")
        for p in self.cfg["perfis_custom"]:
            self.lista.insert("end", p["nome"])

    def carregar(self, _=None):
        sel = self.lista.curselection()
        if not sel:
            return
        p = self.cfg["perfis_custom"][sel[0]]
        self.nome.delete(0, "end")
        self.nome.insert(0, p["nome"])
        self.plano.set(next((k for k, v in self.PLANOS.items() if v == p["plano"]), "Equilibrado"))
        self.procs.delete("1.0", "end")
        self.procs.insert("end", "\n".join(p["fechar"]))

    def novo(self):
        self.lista.selection_clear(0, "end")
        self.nome.delete(0, "end")
        self.procs.delete("1.0", "end")

    def _dados(self):
        nome = self.nome.get().strip()
        fechar = [x.strip() for x in self.procs.get("1.0", "end").splitlines() if x.strip()]
        return {"nome": nome, "plano": self.PLANOS[self.plano.get()], "fechar": fechar}

    def salvar(self):
        d = self._dados()
        if not d["nome"]:
            messagebox.showinfo(APP, "Dê um nome ao perfil.", parent=self)
            return
        lst = self.cfg["perfis_custom"]
        for i, p in enumerate(lst):
            if p["nome"].lower() == d["nome"].lower():
                lst[i] = d
                break
        else:
            lst.append(d)
        salvar_config(self.cfg)
        self.atualizar()

    def excluir(self):
        sel = self.lista.curselection()
        if sel:
            del self.cfg["perfis_custom"][sel[0]]
            salvar_config(self.cfg)
            self.atualizar()
            self.novo()

    def aplicar(self):
        d = self._dados()
        ok, m = opt.aplicar_plano(d["plano"], f"Perfil personalizado '{d['nome'] or 'sem nome'}'")
        achados = []
        if hw.psutil and d["fechar"]:
            alvo = {x.lower() for x in d["fechar"]}
            for p in hw.psutil.process_iter(["name", "pid"]):
                try:
                    if (p.info["name"] or "").lower() in alvo:
                        achados.append((p.info["name"], p.info["pid"]))
                except hw.psutil.Error:
                    continue
        if achados and messagebox.askyesno(APP, "Encerrar estes programas?\n\n" + "\n".join(sorted({n for n, _ in achados})) +
                                           "\n\nTrabalho não salvo neles será perdido.", parent=self):
            for n, pid in achados:
                opt.encerrar_processo(pid, n)
        messagebox.showinfo(APP, m, parent=self)


# ============================================================================= configurações
class Config(Pagina):
    def __init__(self, app):
        super().__init__(app)
        titulo_pagina(self, "Configurações")
        c = Cartao(self, "Segurança", T.ROXO)
        c.pack(fill="x", padx=26, pady=8)
        self.cfg = carregar_config()
        self.v1 = tk.BooleanVar(value=self.cfg["restauracao_auto"])
        self.v2 = tk.BooleanVar(value=self.cfg["limpar_navegadores"])
        for v, t in ((self.v1, "Criar ponto de restauração antes de instalar drivers (recomendado)"),
                     (self.v2, "Já autorizei a limpeza de cache de navegadores")):
            tk.Checkbutton(c.corpo, text=t, variable=v, command=self.salvar, bg=T.PANEL, fg=T.TEXTO, selectcolor=T.PANEL2,
                           activebackground=T.PANEL, activeforeground=T.TEXTO, font=T.fonte(10)).pack(anchor="w")
        cs = Cartao(self, "Sensores de temperatura", T.LARANJA)
        cs.pack(fill="x", padx=26, pady=8)
        self.sens_lbl = tk.Label(cs.corpo, text="", bg=T.PANEL, fg=T.MUDO, font=T.fonte(10), justify="left", anchor="w", wraplength=720)
        self.sens_lbl.pack(side="left", fill="x", expand=True)
        self.btn_pawn = Botao(cs.corpo, "Instalar driver de sensores", self.instalar_pawnio)
        self.btn_pawn.pack(side="right")
        cu = Cartao(self, "Atualizações", T.CIANO)
        cu.pack(fill="x", padx=26, pady=8)
        self.upd = tk.Label(cu.corpo, text=f"Versão instalada: {VERSAO}", bg=T.PANEL, fg=T.MUDO, font=T.fonte(10))
        self.upd.pack(side="left")
        Botao(cu.corpo, "Verificar agora", self.verificar).pack(side="right")
        c2 = Cartao(self, "Sobre")
        c2.pack(fill="x", padx=26, pady=8)
        tk.Label(c2.corpo, bg=T.PANEL, fg=T.MUDO, font=T.fonte(10), justify="left", anchor="w",
                 text=f"{APP} {VERSAO}\nAdministrador: {'sim' if is_admin() else 'NÃO (algumas funções ficam limitadas)'}\n"
                      f"Dados e logs: {PASTA}").pack(anchor="w")

    def on_show(self):
        self.atualizar_sensores()

    def atualizar_sensores(self):
        def fim(est):
            textos = {
                "ativo": ("Leitura de temperatura ativa (LibreHardwareMonitor embutido + driver PawnIO).", T.VERDE),
                "sem_pawnio": ("Leitor de sensores rodando, mas o driver PawnIO não está instalado. Sem ele, a maioria dos "
                               "processadores não informa a temperatura. O driver é de terceiros (pawnio.eu), assinado, e só "
                               "é instalado se você aprovar.", T.AMARELO),
                "desligado": ("Leitor de sensores desligado. Reinicie o NEXUS PC como Administrador.", T.AMARELO),
                "sem_binario": ("Esta versão não traz o leitor de sensores embutido. Abra o LibreHardwareMonitor para "
                                "ver as temperaturas.", T.MUDO)}
            t, cor = textos[est]
            self.sens_lbl.config(text=t, fg=cor)
            (self.btn_pawn.pack(side="right") if est == "sem_pawnio" else self.btn_pawn.pack_forget())
        self.app.bg(lhm.estado, fim, lambda e: None)

    def instalar_pawnio(self):
        if not messagebox.askyesno(APP, "Instalar o driver PawnIO (pawnio.eu)?\n\n"
                                        "• É um driver de kernel de terceiros, assinado, usado pelo LibreHardwareMonitor "
                                        "para ler sensores do processador.\n"
                                        "• Será criado um ponto de restauração antes.\n"
                                        "• Para remover depois: winget uninstall namazso.PawnIO\n\n"
                                        "Você aprova a instalação?"):
            return
        self.sens_lbl.config(text="Instalando...", fg=T.CIANO)
        self.app.bg(lambda: lhm.instalar_pawnio(), lambda r: (messagebox.showinfo(APP, r[1]), self.atualizar_sensores()),
                    lambda e: self.sens_lbl.config(text=f"Erro: {e}", fg=T.VERMELHO))

    def verificar(self):
        self.upd.config(text="Verificando...", fg=T.CIANO)

        def fim(res):
            nova, tag, url, msg = res
            self.upd.config(text=msg, fg=T.AMARELO if nova else T.VERDE)
            self.app.marcar_update(nova, url, msg)
            if nova and messagebox.askyesno(APP, f"{msg}\nAbrir a página para baixar?"):
                webbrowser.open(url)
        self.app.bg(up.verificar, fim)

    def salvar(self):
        self.cfg["restauracao_auto"] = self.v1.get()
        self.cfg["limpar_navegadores"] = self.v2.get()
        salvar_config(self.cfg)


# ================================================================================== app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP} {VERSAO}")
        self.geometry("1240x780")
        self.minsize(1100, 700)
        self.configure(bg=T.BG)
        T.aplicar_estilos(self)
        self.q = queue.Queue()
        self.ctx, self.problemas, self.geral, self.notas = None, [], None, None
        self.drivers, self.erros_pnp = [], []
        self.atual = None
        self.ultima = None
        self.gravador = bn.Gravador()
        self.visivel = True
        self.url_update = ""
        self.sens = hw.Sensores()

        lateral = tk.Frame(self, bg=T.SIDEBAR, width=230)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        tk.Label(lateral, text="NEXUS", bg=T.SIDEBAR, fg=T.CIANO, font=T.fonte(22, True)).pack(anchor="w", padx=22, pady=(22, 0))
        tk.Label(lateral, text="PC  •  diagnóstico e otimização", bg=T.SIDEBAR, fg=T.MUDO, font=T.fonte(8)).pack(anchor="w", padx=22, pady=(0, 18))
        self.itens = {}
        for chave, nome, ic in MENU:
            f = tk.Frame(lateral, bg=T.SIDEBAR, cursor="hand2")
            f.pack(fill="x")
            barra = tk.Frame(f, bg=T.SIDEBAR, width=3)
            barra.pack(side="left", fill="y")
            lb = tk.Label(f, text=f"  {ic}   {nome}", bg=T.SIDEBAR, fg=T.MUDO, font=T.fonte(10), anchor="w", pady=9)
            lb.pack(side="left", fill="x", expand=True)
            for w in (f, lb):
                w.bind("<Button-1>", lambda e, c=chave: self.ir(c))
                w.bind("<Enter>", lambda e, c=chave: self._hover(c, True))
                w.bind("<Leave>", lambda e, c=chave: self._hover(c, False))
            self.itens[chave] = (f, lb, barra)
        adm = is_admin()
        tk.Label(lateral, text="● Administrador" if adm else "⚠ Sem administrador", bg=T.SIDEBAR,
                 fg=T.VERDE if adm else T.AMARELO, font=T.fonte(9)).pack(side="bottom", anchor="w", padx=22, pady=14)

        self.lbl_update = tk.Label(lateral, text="", bg=T.SIDEBAR, fg=T.AMARELO, font=T.fonte(9, True), cursor="hand2",
                                   wraplength=200, justify="left")
        self.lbl_update.pack(side="bottom", anchor="w", padx=22)
        self.lbl_update.bind("<Button-1>", lambda e: self.url_update and webbrowser.open(self.url_update))
        self.bind("<Unmap>", lambda e: e.widget is self and setattr(self, "visivel", False))
        self.bind("<Map>", lambda e: e.widget is self and setattr(self, "visivel", True))
        self.conteudo = tk.Frame(self, bg=T.BG)
        self.conteudo.pack(side="left", fill="both", expand=True)
        classes = dict(dashboard=Dashboard, analise=Analise, diagnostico=Diagnostico, drivers=Drivers, game=GameBoost,
                       work=WorkBoost, monitor=Monitor, reparo=Reparo, limpeza=Limpeza, startup=Inicializacao,
                       historico=Historico, config=Config)
        self.paginas = {k: c(self) for k, c in classes.items()}
        self.ir("dashboard")
        self.after(50, self._poll)
        threading.Thread(target=self._monitorar, daemon=True).start()
        self.bg(up.verificar, lambda r: self.marcar_update(r[0], r[2], r[3]), lambda e: None)
        self.bg(lhm.iniciar, None, lambda e: None)
        self.protocol("WM_DELETE_WINDOW", self.fechar)

    # ---- navegação
    def _hover(self, chave, entrou):
        if chave != self.atual:
            f, lb, _ = self.itens[chave]
            cor = "#121826" if entrou else T.SIDEBAR
            f.config(bg=cor)
            lb.config(bg=cor, fg=T.TEXTO if entrou else T.MUDO)

    def ir(self, chave, iniciar=False):
        if self.atual:
            self.paginas[self.atual].pack_forget()
        self.atual = chave
        for k, (f, lb, barra) in self.itens.items():
            ativo = k == chave
            f.config(bg="#121826" if ativo else T.SIDEBAR)
            lb.config(bg="#121826" if ativo else T.SIDEBAR, fg=T.CIANO if ativo else T.MUDO)
            barra.config(bg=T.CIANO if ativo else T.SIDEBAR)
        pg = self.paginas[chave]
        pg.pack(fill="both", expand=True)
        pg.on_show()
        if iniciar and hasattr(pg, "iniciar"):
            self.after(100, pg.iniciar)

    def fechar(self):
        lhm.parar()
        self.destroy()

    def marcar_update(self, nova, url, msg):
        self.url_update = url if nova else ""
        self.lbl_update.config(text=("⬆ " + msg + "\n(clique para baixar)") if nova else "")

    def janela_texto(self, titulo, texto):
        j = tk.Toplevel(self)
        j.title(titulo)
        j.configure(bg=T.BG)
        j.geometry("720x520")
        tk.Label(j, text=titulo, bg=T.BG, fg=T.TEXTO, font=T.fonte(14, True)).pack(anchor="w", padx=16, pady=(12, 4))
        f, t = texto_rolavel(j, 20, mono=False)
        f.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        t.insert("end", texto)

    def exportar_html(self):
        if not self.ctx:
            messagebox.showinfo(APP, "Faça a Análise completa primeiro.")
            return
        from datetime import datetime as _dt
        arq = PASTA_REL / f"relatorio_{_dt.now():%Y%m%d_%H%M%S}.html"
        arq.write_text(rel.gerar(self.ctx, self.problemas, self.geral, self.notas), encoding="utf-8")
        webbrowser.open(arq.as_uri())

    # ---- threads
    def post(self, fn):
        self.q.put(fn)

    def bg(self, trabalho, fim=None, erro=None):
        def run():
            try:
                r = trabalho()
                if fim:
                    self.post(lambda: fim(r))
            except Exception as e:  # noqa: BLE001
                log.exception("falha em tarefa")
                self.post(lambda: (erro or (lambda x: messagebox.showerror(APP, f"Erro: {x}")))(e))
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            log.exception("erro na fila da interface")
        self.after(40, self._poll)

    def _monitorar(self):
        n = 0
        while True:
            try:
                if not self.visivel and not self.gravador.ativo:
                    time.sleep(2)
                    continue
                if n % 4 == 0 and self.atual in ("dashboard", "monitor"):
                    self.sens.atualizar_lento()
                s = self.sens.amostra()
                self.ultima = s
                self.post(lambda s=s: self._amostra(s))
            except Exception:  # noqa: BLE001
                log.exception("monitor")
            n += 1
            time.sleep(1)

    def _amostra(self, s):
        ov = self.paginas["game"].overlay
        if ov and ov.rodando:
            s["fps"] = ov.fps_atual
        self.gravador.add(s)
        pg = self.paginas.get(self.atual)
        if pg:
            pg.on_sample(s)


def main():
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
        if not is_admin():
            args = " ".join(f'"{a}"' for a in (sys.argv if not getattr(sys, "frozen", False) else sys.argv[1:]))
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
            return
    App().mainloop()
