#!/usr/bin/env python3
"""
Otimizador de PC para Windows
- Limpa todos os Temp
- Plano de energia de desempenho máximo + núcleos sempre ativos
- Ajustes de rede
- Otimiza discos (defrag em HDD, TRIM em SSD)
- Pontuação antes/depois + relatório
- Contador de FPS (overlay) via PresentMon

Rode como Administrador (o .exe já pede isso sozinho).
"""
import ctypes
import csv
import hashlib
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

APP = "Otimizador de PC"
VERSAO = "1.0.0"
IS_WIN = platform.system() == "Windows"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PASTA_DADOS = Path(os.environ.get("APPDATA", str(Path.home()))) / "OtimizadorPC"
ULTIMATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"


# ----------------------------------------------------------------- utilidades
def fmt(b):
    b = float(b)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run(cmd, timeout=None):
    """Roda um comando sem abrir janela preta. Retorna (codigo, saida)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def recurso(nome):
    """Caminho de um arquivo empacotado pelo PyInstaller (ou da pasta atual)."""
    base = getattr(sys, "_MEIPASS", str(Path(__file__).parent))
    return Path(base) / nome


# ------------------------------------------------------------------- limpeza
def pastas_temp():
    pastas = set()
    for var in ("TEMP", "TMP"):
        if os.environ.get(var):
            pastas.add(os.environ[var])
    win = os.environ.get("WINDIR", r"C:\Windows")
    pastas.add(str(Path(win) / "Temp"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pastas.add(str(Path(local) / "Temp"))
    return [p for p in pastas if Path(p).exists()]


def tamanho_temp():
    total = 0
    for pasta in pastas_temp():
        for raiz, _, arquivos in os.walk(pasta):
            for a in arquivos:
                try:
                    total += os.path.getsize(os.path.join(raiz, a))
                except OSError:
                    pass
    return total


def limpar_temp(log):
    liberado, qtd, pulados = 0, 0, 0
    for pasta in pastas_temp():
        for raiz, dirs, arquivos in os.walk(pasta, topdown=False):
            for a in arquivos:
                caminho = os.path.join(raiz, a)
                try:
                    tam = os.path.getsize(caminho)
                    os.remove(caminho)
                    liberado += tam
                    qtd += 1
                except OSError:
                    pulados += 1  # em uso: normal
            for d in dirs:
                try:
                    os.rmdir(os.path.join(raiz, d))
                except OSError:
                    pass
    # lixeira
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
        log("Lixeira esvaziada")
    except Exception:
        pass
    log(f"Temp: {qtd} arquivos removidos ({fmt(liberado)}); {pulados} em uso foram pulados")
    return liberado


# ------------------------------------------------------------------- energia
def guid_plano(nome_chaves):
    _, saida = run(["powercfg", "/list"])
    for linha in saida.splitlines():
        if any(k in linha.lower() for k in nome_chaves):
            for p in linha.split():
                if len(p) == 36 and p.count("-") == 4:
                    return p
    return None


def desempenho_maximo(log):
    # tenta criar/ativar o plano "Desempenho máximo" (Ultimate)
    run(["powercfg", "-duplicatescheme", ULTIMATE_GUID])
    guid = guid_plano(["desempenho máximo", "desempenho maximo", "ultimate"])
    if not guid:
        guid = guid_plano(["alto desempenho", "high performance"])
    if not guid:
        _, saida = run(["powercfg", "-duplicatescheme", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"])
        for p in saida.split():
            if len(p) == 36 and p.count("-") == 4:
                guid = p
    if guid:
        run(["powercfg", "/setactive", guid])
        log("Plano de energia: desempenho máximo ativado")
    else:
        log("Plano de energia: não consegui achar/criar o plano (pulei)")
    # CPU a 100%, todos os núcleos ativos (sem 'core parking'), sem suspender USB/disco
    ajustes = [
        ("sub_processor", "PROCTHROTTLINGMIN", "100"),
        ("sub_processor", "PROCTHROTTLINGMAX", "100"),
        ("sub_processor", "CPMINCORES", "100"),
        ("sub_processor", "CPMAXCORES", "100"),
        ("sub_processor", "PERFBOOSTMODE", "2"),
        ("sub_disk", "DISKIDLE", "0"),
    ]
    for sub, nome, val in ajustes:
        run(["powercfg", "/setacvalueindex", "scheme_current", sub, nome, val])
        run(["powercfg", "/setdcvalueindex", "scheme_current", sub, nome, val])
    run(["powercfg", "/setactive", "scheme_current"])
    log("CPU: mínimo/máximo 100% e núcleos sempre ativos (core parking off)")
    # remove qualquer limite de núcleos no boot
    run(["bcdedit", "/deletevalue", "numproc"])
    log(f"Núcleos: Windows usando todos os {os.cpu_count()} processadores lógicos")


# ---------------------------------------------------------------------- rede
def otimizar_rede(log, dns_rapido=False):
    run(["ipconfig", "/flushdns"])
    run(["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"])
    run(["netsh", "int", "tcp", "set", "global", "rss=enabled"])
    run(["netsh", "int", "tcp", "set", "global", "ecncapability=disabled"])
    run(["netsh", "int", "tcp", "set", "global", "timestamps=disabled"])
    log("Rede: cache DNS limpo, TCP auto-tuning normal, RSS ligado")
    if dns_rapido:
        _, saida = run(["powershell", "-NoProfile", "-Command",
                        "Get-NetAdapter | Where-Object Status -eq 'Up' | "
                        "Set-DnsClientServerAddress -ServerAddresses ('1.1.1.1','8.8.8.8'); 'ok'"])
        log("DNS: Cloudflare/Google aplicado" if "ok" in saida else "DNS: não consegui alterar")


# --------------------------------------------------------------------- discos
def discos_fixos():
    if not psutil:
        return []
    res = []
    for p in psutil.disk_partitions(all=False):
        if "fixed" in p.opts.lower() or p.fstype:
            if p.mountpoint and len(p.mountpoint) >= 2 and p.mountpoint[1] == ":":
                res.append(p.mountpoint[:2])
    return sorted(set(res))


def otimizar_discos(log):
    """defrag /O: o Windows escolhe a ação certa (desfragmenta HDD, TRIM em SSD)."""
    for d in discos_fixos():
        log(f"Disco {d}: otimizando (pode demorar em HDD)...")
        cod, saida = run(["defrag", d, "/O"])
        log(f"Disco {d}: concluído" if cod == 0 else f"Disco {d}: {saida.strip()[:120]}")


# ------------------------------------------------------------------- restauração
def criar_ponto_restauracao(log):
    cmd = ("Enable-ComputerRestore -Drive $env:SystemDrive; "
           "Checkpoint-Computer -Description 'Otimizador de PC' -RestorePointType MODIFY_SETTINGS")
    cod, saida = run(["powershell", "-NoProfile", "-Command", cmd], timeout=180)
    log("Ponto de restauração criado" if cod == 0 else
        "Ponto de restauração: não criado (o Windows só permite 1 a cada 24h)")


# -------------------------------------------------------------------- bench
def _hash_worker(buf, rodadas):
    for _ in range(rodadas):
        hashlib.sha256(buf).digest()


def bench_cpu():
    """MB/s de SHA-256 usando todos os núcleos (hashlib solta o GIL)."""
    n = os.cpu_count() or 1
    buf = os.urandom(8 * 1024 * 1024)
    rodadas = 6
    ts = [threading.Thread(target=_hash_worker, args=(buf, rodadas)) for _ in range(n)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dt = time.perf_counter() - t0
    return (n * rodadas * 8) / dt


def bench_disco():
    """MB/s de escrita sequencial em arquivo temporário (com fsync)."""
    caminho = PASTA_DADOS / "bench.tmp"
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    bloco = os.urandom(4 * 1024 * 1024)
    t0 = time.perf_counter()
    with open(caminho, "wb") as f:
        for _ in range(32):  # 128 MB
            f.write(bloco)
        f.flush()
        os.fsync(f.fileno())
    dt = time.perf_counter() - t0
    try:
        caminho.unlink()
    except OSError:
        pass
    return 128 / dt


def bench_ping():
    """Latência TCP média (ms) até 1.1.1.1:443; None se sem internet."""
    tempos = []
    for _ in range(5):
        try:
            t0 = time.perf_counter()
            with socket.create_connection(("1.1.1.1", 443), timeout=2):
                pass
            tempos.append((time.perf_counter() - t0) * 1000)
        except OSError:
            pass
    return statistics.median(tempos) if tempos else None


def contar_startup():
    if not IS_WIN:
        return 0
    import winreg
    n = 0
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                n += winreg.QueryInfoKey(k)[1]
        except OSError:
            pass
    return n


def medir():
    """Coleta métricas e calcula a pontuação (0-1000)."""
    m = {}
    m["cpu_mbs"] = bench_cpu()
    m["disco_mbs"] = bench_disco()
    m["ping_ms"] = bench_ping()
    m["temp_bytes"] = tamanho_temp() if IS_WIN else 0
    m["startup"] = contar_startup()
    if psutil:
        m["ram_livre_pct"] = 100 - psutil.virtual_memory().percent
        raiz = os.environ.get("SystemDrive", "C:") + "\\"
        u = shutil.disk_usage(raiz)
        m["disco_livre_pct"] = u.free / u.total * 100
        m["disco_livre_bytes"] = u.free
    else:
        m["ram_livre_pct"] = m["disco_livre_pct"] = 0
        m["disco_livre_bytes"] = 0
    m["pontos"] = pontuar(m)
    return m


def pontuar(m):
    def lim(x, a=0, b=1):
        return max(a, min(b, x))
    p = 0
    p += 300 * lim(m["cpu_mbs"] / 4000)             # CPU
    p += 200 * lim(m["disco_mbs"] / 1000)           # velocidade do disco
    p += 150 * lim(m["ram_livre_pct"] / 60)         # RAM livre
    p += 100 * lim(m["disco_livre_pct"] / 40)       # espaço livre
    p += 100 * (lim(1 - (m["ping_ms"] - 10) / 190) if m["ping_ms"] else 0)  # latência
    p += 80 * lim(1 - m["temp_bytes"] / (5 * 1024 ** 3))  # lixo em Temp
    p += 70 * lim(1 - m["startup"] / 15)            # itens na inicialização
    return round(p)


def relatorio_texto(antes, depois):
    def linha(nome, a, d, f=lambda x: f"{x:.1f}", melhor_maior=True):
        if a is None or d is None:
            return f"{nome:<22}{'-':>12}{'-':>12}"
        dif = d - a
        sinal = "+" if dif >= 0 else ""
        ok = (dif >= 0) == melhor_maior
        marca = "↑" if ok and dif != 0 else ("↓" if dif != 0 else "=")
        return f"{nome:<22}{f(a):>12}{f(d):>12}   {sinal}{f(dif)} {marca}"
    L = [f"RELATÓRIO - {datetime.now():%d/%m/%Y %H:%M}", "=" * 62,
         f"{'Item':<22}{'Antes':>12}{'Depois':>12}   Diferença",
         "-" * 62,
         linha("PONTOS (0-1000)", antes["pontos"], depois["pontos"], lambda x: f"{x:.0f}"),
         linha("CPU (MB/s)", antes["cpu_mbs"], depois["cpu_mbs"], lambda x: f"{x:.0f}"),
         linha("Disco escrita (MB/s)", antes["disco_mbs"], depois["disco_mbs"], lambda x: f"{x:.0f}"),
         linha("RAM livre (%)", antes["ram_livre_pct"], depois["ram_livre_pct"]),
         linha("Espaço livre (GB)", antes["disco_livre_bytes"] / 1024 ** 3,
               depois["disco_livre_bytes"] / 1024 ** 3),
         linha("Ping (ms)", antes["ping_ms"], depois["ping_ms"], melhor_maior=False),
         linha("Lixo em Temp (MB)", antes["temp_bytes"] / 1024 ** 2,
               depois["temp_bytes"] / 1024 ** 2, lambda x: f"{x:.0f}", melhor_maior=False),
         linha("Itens inicialização", antes["startup"], depois["startup"],
               lambda x: f"{x:.0f}", melhor_maior=False),
         "-" * 62]
    d = depois["pontos"] - antes["pontos"]
    pct = (d / antes["pontos"] * 100) if antes["pontos"] else 0
    L.append(f"Resultado: {'+' if d >= 0 else ''}{d} pontos ({pct:+.1f}%)")
    L.append("Obs.: medições variam um pouco a cada execução (programas abertos, cache).")
    return "\n".join(L)


# ------------------------------------------------------------ contador de FPS
class FpsOverlay:
    """Janela pequena, sempre no topo, mostrando FPS via PresentMon."""

    def __init__(self, master):
        self.master = master
        self.proc = None
        self.fps = {}          # app -> lista de frametimes (ms)
        self.lock = threading.Lock()
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.8)
        self.win.configure(bg="black")
        self.win.geometry("+20+20")
        self.lbl = tk.Label(self.win, text="FPS --", font=("Consolas", 20, "bold"),
                            fg="#00ff66", bg="black", padx=10, pady=4)
        self.lbl.pack()
        self.sub = tk.Label(self.win, text="", font=("Consolas", 9), fg="#aaaaaa", bg="black")
        self.sub.pack()
        self.lbl.bind("<ButtonPress-1>", self._ini)
        self.lbl.bind("<B1-Motion>", self._mov)
        self.lbl.bind("<Double-Button-1>", lambda e: self.fechar())
        self.rodando = True
        self._iniciar_presentmon()
        self._atualizar()

    def _ini(self, e):
        self._dx, self._dy = e.x, e.y

    def _mov(self, e):
        self.win.geometry(f"+{self.win.winfo_x() + e.x - self._dx}+{self.win.winfo_y() + e.y - self._dy}")

    def _iniciar_presentmon(self):
        exe = recurso("PresentMon.exe")
        if not exe.exists():
            exe = Path("PresentMon.exe")
        if not exe.exists():
            self.sub.config(text="PresentMon.exe não encontrado")
            return
        cmd = [str(exe), "--output_stdout", "--stop_existing_session",
               "--session_name", "OtimizadorPC_FPS", "--no_console_stats"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True, creationflags=NO_WINDOW)
        except OSError as e:
            self.sub.config(text=f"erro: {e}")
            return
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        leitor = csv.reader(self.proc.stdout)
        cab = None
        for linha in leitor:
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
                agora = time.time()
                with self.lock:
                    self.fps.setdefault(app, []).append((agora, ft))
            except (ValueError, KeyError):
                continue

    def _atualizar(self):
        if not self.rodando:
            return
        agora = time.time()
        melhor, nfps = None, 0
        with self.lock:
            for app, lista in list(self.fps.items()):
                lista[:] = [(t, f) for t, f in lista if agora - t <= 1.0]
                if len(lista) > nfps:
                    melhor, nfps = app, len(lista)
        if melhor and nfps:
            cor = "#00ff66" if nfps >= 55 else "#ffcc00" if nfps >= 30 else "#ff4444"
            self.lbl.config(text=f"FPS {nfps}", fg=cor)
            self.sub.config(text=melhor)
        else:
            self.lbl.config(text="FPS --", fg="#888888")
            if self.proc:
                self.sub.config(text="abra um jogo (duplo clique fecha)")
        self.win.after(500, self._atualizar)

    def fechar(self):
        self.rodando = False
        if self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.win.destroy()


# ----------------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP} {VERSAO}")
        self.geometry("720x640")
        self.minsize(640, 560)
        self.overlay = None
        self.ocupado = False
        self._ui()
        if IS_WIN and not is_admin():
            self.log("AVISO: não está como Administrador. Feche e abra com 'Executar como administrador'.")

    def _ui(self):
        topo = ttk.Frame(self, padding=10)
        topo.pack(fill="x")
        ttk.Label(topo, text=APP, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(topo, text="Marque o que quer aplicar e clique em OTIMIZAR.").pack(anchor="w")

        op = ttk.LabelFrame(self, text="Opções", padding=10)
        op.pack(fill="x", padx=10)
        self.v = {
            "restauracao": tk.BooleanVar(value=True),
            "temp": tk.BooleanVar(value=True),
            "energia": tk.BooleanVar(value=True),
            "rede": tk.BooleanVar(value=True),
            "dns": tk.BooleanVar(value=False),
            "discos": tk.BooleanVar(value=True),
            "boot": tk.BooleanVar(value=False),
        }
        textos = [
            ("restauracao", "Criar ponto de restauração antes (recomendado)"),
            ("temp", "Limpar TODOS os Temp + esvaziar lixeira"),
            ("energia", "Desempenho máximo + todos os núcleos ativos"),
            ("rede", "Otimizar rede (TCP, limpar DNS)"),
            ("dns", "Trocar DNS para Cloudflare/Google (1.1.1.1 / 8.8.8.8)"),
            ("discos", "Otimizar discos (defrag em HDD, TRIM em SSD) - pode demorar"),
            ("boot", "Reaplicar desempenho máximo toda vez que ligar o PC"),
        ]
        for chave, txt in textos:
            ttk.Checkbutton(op, text=txt, variable=self.v[chave]).pack(anchor="w")

        bt = ttk.Frame(self, padding=10)
        bt.pack(fill="x")
        self.btn = ttk.Button(bt, text="⚡ OTIMIZAR", command=self.otimizar)
        self.btn.pack(side="left")
        ttk.Button(bt, text="📊 Só medir pontos", command=self.so_medir).pack(side="left", padx=6)
        ttk.Button(bt, text="🎮 Contador de FPS", command=self.fps).pack(side="left")
        ttk.Button(bt, text="📁 Abrir relatórios", command=self.abrir_pasta).pack(side="left", padx=6)

        self.barra = ttk.Progressbar(self, mode="indeterminate")
        self.barra.pack(fill="x", padx=10)
        self.txt = tk.Text(self, height=18, font=("Consolas", 9), bg="#111", fg="#ddd", wrap="word")
        self.txt.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, msg):
        self.after(0, lambda: (self.txt.insert("end", msg + "\n"), self.txt.see("end")))

    def _rodar(self, alvo):
        if self.ocupado:
            return
        if not IS_WIN:
            messagebox.showerror(APP, "Este programa é só para Windows.")
            return
        self.ocupado = True
        self.btn.state(["disabled"])
        self.barra.start(12)

        def tarefa():
            try:
                alvo()
            except Exception as e:  # noqa: BLE001
                self.log(f"ERRO: {e}")
            finally:
                self.after(0, self._fim)
        threading.Thread(target=tarefa, daemon=True).start()

    def _fim(self):
        self.ocupado = False
        self.btn.state(["!disabled"])
        self.barra.stop()

    def so_medir(self):
        def t():
            self.log("Medindo (≈20s)...")
            m = medir()
            self.log(f"PONTOS: {m['pontos']}/1000 | CPU {m['cpu_mbs']:.0f} MB/s | "
                     f"disco {m['disco_mbs']:.0f} MB/s | ping "
                     f"{'%.0f ms' % m['ping_ms'] if m['ping_ms'] else 'sem internet'} | "
                     f"Temp {fmt(m['temp_bytes'])}")
        self._rodar(t)

    def otimizar(self):
        if not messagebox.askyesno(APP, "Isso vai limpar arquivos temporários e alterar configurações "
                                        "de energia/rede/discos. Continuar?"):
            return
        o = {k: x.get() for k, x in self.v.items()}

        def t():
            self.log("Medindo ANTES (≈20s)...")
            antes = medir()
            self.log(f"Pontos antes: {antes['pontos']}")
            if o["restauracao"]:
                criar_ponto_restauracao(self.log)
            if o["temp"]:
                limpar_temp(self.log)
            if o["energia"]:
                desempenho_maximo(self.log)
            if o["rede"]:
                otimizar_rede(self.log, dns_rapido=o["dns"])
            if o["boot"]:
                agendar_boot(self.log)
            if o["discos"]:
                otimizar_discos(self.log)
            self.log("Medindo DEPOIS...")
            depois = medir()
            rel = relatorio_texto(antes, depois)
            PASTA_DADOS.mkdir(parents=True, exist_ok=True)
            arq = PASTA_DADOS / f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.txt"
            arq.write_text(rel, encoding="utf-8")
            (PASTA_DADOS / "historico.json").open("a", encoding="utf-8").write(
                json.dumps({"data": datetime.now().isoformat(), "antes": antes["pontos"],
                            "depois": depois["pontos"]}) + "\n")
            self.log("\n" + rel)
            self.log(f"\nRelatório salvo em: {arq}")
        self._rodar(t)

    def fps(self):
        if self.overlay and self.overlay.rodando:
            return
        self.overlay = FpsOverlay(self)

    def abrir_pasta(self):
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            os.startfile(PASTA_DADOS)  # noqa: S606


def agendar_boot(log):
    exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{Path(__file__).resolve()}"'
    cod, saida = run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/RL", "HIGHEST",
                      "/TN", "OtimizadorPC_Desempenho", "/TR", f'{exe} --silencioso'])
    log("Tarefa de início criada (reaplica ao logar)" if cod == 0 else f"Tarefa de início falhou: {saida.strip()[:100]}")


def modo_silencioso():
    desempenho_maximo(lambda m: None)


def relancar_como_admin():
    if getattr(sys, "frozen", False):
        args = " ".join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    else:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                            " ".join([f'"{sys.argv[0]}"'] + sys.argv[1:]), None, 1)


def main():
    if "--silencioso" in sys.argv:
        if IS_WIN:
            modo_silencioso()
        return
    if IS_WIN and not is_admin():
        relancar_como_admin()
        return
    App().mainloop()


if __name__ == "__main__":
    main()
