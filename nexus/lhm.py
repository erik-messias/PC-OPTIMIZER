"""Sensores de temperatura: LibreHardwareMonitor embutido (iniciado oculto) + driver PawnIO opcional.
O LibreHardwareMonitor publica os sensores em WMI (root\\LibreHardwareMonitor), que o NEXUS PC lê."""
import ctypes
import os
import shutil
import subprocess
import threading
import time
from ctypes import wintypes

from .core import HIST, IS_WIN, NO_WINDOW, PASTA, criar_ponto_restauracao, log, recurso, run

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

PASTA_LHM = PASTA / "lhm"
EXE = "LibreHardwareMonitor.exe"
_proc = None
_iniciado_por_nos = False

_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration><appSettings>
<add key="startMinMenuItem" value="true" />
<add key="minTrayMenuItem" value="true" />
<add key="minCloseMenuItem" value="true" />
</appSettings></configuration>
"""


def embutido():
    return recurso("lhm").joinpath(EXE).exists()


def rodando():
    if not psutil:
        return False
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() == EXE.lower():
                return True
        except psutil.Error:
            continue
    return False


def pawnio_instalado():
    if not IS_WIN:
        return False
    cod, _ = run(["sc", "query", "PawnIO"])
    if cod == 0:
        return True
    return any(os.path.isdir(os.path.join(os.environ.get(v, ""), "PawnIO")) for v in ("ProgramFiles", "ProgramFiles(x86)"))


def estado():
    """'ativo', 'sem_pawnio', 'sem_binario' ou 'desligado' (para mensagens ao usuário)."""
    if rodando():
        return "ativo" if pawnio_instalado() else "sem_pawnio"
    return "desligado" if embutido() else "sem_binario"


def _esconder_janela(pid):
    """Esconde a janela do LibreHardwareMonitor (caso a configuração de minimizar não pegue)."""
    user32 = ctypes.windll.user32
    achou = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            achou.append(hwnd)
        return True
    for _ in range(30):
        achou.clear()
        user32.EnumWindows(cb, 0)
        for h in achou:
            user32.ShowWindow(h, 0)  # SW_HIDE
        time.sleep(0.5)


def iniciar():
    """Copia o LibreHardwareMonitor para a pasta de dados e o abre oculto. Retorna True se está rodando."""
    global _proc, _iniciado_por_nos
    if not IS_WIN:
        return False
    if rodando():
        return True
    if not embutido():
        log.info("lhm: binário não embutido")
        return False
    try:
        origem = recurso("lhm")
        if not (PASTA_LHM / EXE).exists():
            shutil.copytree(origem, PASTA_LHM, dirs_exist_ok=True)
        cfg = PASTA_LHM / "LibreHardwareMonitor.config"
        if not cfg.exists():
            cfg.write_text(_CONFIG, encoding="utf-8")
        _proc = subprocess.Popen([str(PASTA_LHM / EXE)], cwd=str(PASTA_LHM), creationflags=NO_WINDOW)
        _iniciado_por_nos = True
        threading.Thread(target=_esconder_janela, args=(_proc.pid,), daemon=True).start()
        log.info("lhm iniciado pid %s", _proc.pid)
        return True
    except Exception:  # noqa: BLE001
        log.exception("lhm: falha ao iniciar")
        return False


def parar():
    global _proc
    if _proc and _iniciado_por_nos:
        try:
            _proc.terminate()
        except OSError:
            pass
        _proc = None


def reiniciar():
    parar()
    for p in (psutil.process_iter(["name"]) if psutil else []):
        try:
            if (p.info["name"] or "").lower() == EXE.lower():
                p.terminate()
        except psutil.Error:
            continue
    time.sleep(1.5)
    return iniciar()


def instalar_pawnio(progresso=lambda m: None):
    """Instala o driver PawnIO via winget (precisa de aprovação do usuário na interface). Retorna (ok, msg)."""
    if shutil.which("winget") is None:
        return False, "winget não encontrado. Baixe o instalador em https://pawnio.eu"
    progresso("Criando ponto de restauração...")
    criar_ponto_restauracao("antes de instalar o driver PawnIO")
    progresso("Instalando o driver PawnIO (winget)...")
    cod, saida = run(["winget", "install", "--id", "namazso.PawnIO", "--exact", "--silent",
                      "--accept-package-agreements", "--accept-source-agreements"], timeout=600)
    ok = cod == 0 or "já está instalado" in saida.lower() or "already installed" in saida.lower()
    HIST.registrar("Instalar driver PawnIO", "sensores de temperatura (aprovado pelo usuário)",
                   "Instalado" if ok else f"Falhou ({cod})")
    if ok:
        reiniciar()
        return True, "Driver instalado. Se a temperatura não aparecer, reinicie o PC."
    return False, f"Falha ao instalar: {saida.strip()[-200:]}"


# --------------------------------------------------------------- interpretação
_PRIO_CPU = ("cpu package", "core (tctl/tdie)", "core max", "cpu (tctl/tdie)", "tctl/tdie", "core average")


def interpretar(linhas):
    """linhas = [{Identifier, SensorType, Name, Value}] do WMI do LibreHardwareMonitor.
    Retorna dict com cpu_temp, cpu_consumo, gpu_*, disco_temp, ventoinhas."""
    r = {}
    cpu_t, gpu = [], {}
    discos, fans = [], []
    for x in linhas:
        ident = (x.get("Identifier") or "").lower()
        tipo, nome = (x.get("SensorType") or ""), (x.get("Name") or "")
        v = x.get("Value")
        if v is None:
            continue
        v = float(v)
        if ident.startswith(("/intelcpu", "/amdcpu")):
            if tipo == "Temperature":
                cpu_t.append((nome.lower(), v))
            elif tipo == "Power" and "package" in nome.lower():
                r["cpu_consumo"] = v
        elif "/gpu-" in ident or ident.startswith("/gpu"):
            n = nome.lower()
            if tipo == "Temperature" and ("core" in n or "gpu" in n) and "hot" not in n:
                gpu.setdefault("gpu_temp", v)
            elif tipo == "Load" and n in ("gpu core", "d3d 3d"):
                gpu.setdefault("gpu_util", v)
            elif tipo == "Power" and ("package" in n or "gpu power" in n or n == "gpu core"):
                gpu.setdefault("gpu_consumo", v)
            elif tipo == "Clock" and n == "gpu core":
                gpu.setdefault("gpu_freq", v)
            elif tipo == "Control" and "fan" in n or tipo == "Fan":
                gpu.setdefault("gpu_fan", v)
        elif ident.startswith(("/nvme", "/hdd", "/ssd", "/storage")) and tipo == "Temperature":
            discos.append(v)
        if tipo == "Fan" and not ("/gpu" in ident):
            fans.append((nome, v))
    if cpu_t:
        for chave in _PRIO_CPU:
            achado = [v for n, v in cpu_t if n == chave]
            if achado:
                r["cpu_temp"] = achado[0]
                break
        else:
            r["cpu_temp"] = max(v for _, v in cpu_t)
    r.update(gpu)
    if discos:
        r["disco_temp"] = max(discos)
    if fans:
        r["ventoinhas"] = fans
    return r
