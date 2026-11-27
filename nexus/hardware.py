"""Identificação de hardware e leitura de sensores (WMI, psutil, nvidia-smi, LibreHardwareMonitor)."""
import shutil
import time

from .core import IS_WIN, aslist, log, ps, ps_json, run

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_INVENTARIO_PS = r"""
function D($d){ if($d){ try{ $d.ToString('yyyy-MM-dd') }catch{ "$d" } } else { '' } }
$o = [ordered]@{}
$o.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,
        @{n='boot';e={D $_.LastBootUpTime}},@{n='bootdias';e={[int]((Get-Date)-$_.LastBootUpTime).TotalDays}}
$o.cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed)
$o.placa = @(Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product)
$o.bios = @(Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,@{n='data';e={D $_.ReleaseDate}})
$o.gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion,
        @{n='driverdata';e={D $_.DriverDate}},CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate)
$o.ram = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,Capacity,Speed,ConfiguredClockSpeed,PartNumber,
        @{n='slot';e={$_.DeviceLocator}})
$o.discos = @(Get-PhysicalDisk -ErrorAction SilentlyContinue | Select-Object FriendlyName,
        @{n='tipo';e={"$($_.MediaType)"}},Size,@{n='saude';e={"$($_.HealthStatus)"}},@{n='estado';e={"$($_.OperationalStatus)"}},
        @{n='barramento';e={"$($_.BusType)"}})
$o.rede = @(Get-CimInstance Win32_NetworkAdapter | Where-Object { $_.PhysicalAdapter } |
        Select-Object Name,NetEnabled,Speed)
$o.usb = @(Get-PnpDevice -Class USB -PresentOnly -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FriendlyName)
$o.monitores = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue |
        ForEach-Object { ($_.UserFriendlyName | Where-Object {$_ -ne 0} | ForEach-Object {[char]$_}) -join '' })
$o.bateria = @(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object EstimatedChargeRemaining)
$o | ConvertTo-Json -Compress -Depth 4
"""


def ler_inventario():
    """Retorna dict com todo o hardware identificado ({} se falhar)."""
    d = ps_json(_INVENTARIO_PS, timeout=120, default={}) or {}
    for k in ("cpu", "placa", "bios", "gpu", "ram", "discos", "rede", "usb", "monitores", "bateria"):
        d[k] = aslist(d.get(k))
    d["os"] = d.get("os") or {}
    if isinstance(d["os"], list) and d["os"]:
        d["os"] = d["os"][0]
    return d


def resumo_gpu(g):
    ram = g.get("AdapterRAM") or 0
    if ram < 0:  # WMI devolve 32 bits com sinal
        ram += 2 ** 32
    return ram


# ----------------------------------------------------------------------- sensores
_SENSORES_PS = r"""
$o = [ordered]@{lhm=@(); acpi=$null; gpu_engine=$null}
try {
  $o.lhm = @(Get-CimInstance -Namespace root\LibreHardwareMonitor -ClassName Sensor -ErrorAction Stop |
     Where-Object { $_.SensorType -in 'Temperature','Power','Fan','Load','Clock','Control' } |
     Select-Object Identifier,SensorType,Name,Value)
} catch {}
try {
  $z = Get-CimInstance -Namespace root\wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop
  $m = ($z | ForEach-Object { $_.CurrentTemperature / 10 - 273.15 } | Measure-Object -Maximum).Maximum
  if ($m -gt 0 -and $m -lt 130) { $o.acpi = [math]::Round($m,1) }
} catch {}
try {
  $c = (Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction Stop).CounterSamples
  $o.gpu_engine = [math]::Min(100, [math]::Round(($c | Measure-Object CookedValue -Sum).Sum,1))
} catch {}
ConvertTo-Json -InputObject $o -Compress -Depth 4
"""

_NVSMI = ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,"
          "power.draw,clocks.gr,clocks.max.gr,fan.speed,driver_version,clocks_throttle_reasons.active",
          "--format=csv,noheader,nounits"]


def _num(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def ler_nvidia():
    """Dados da GPU NVIDIA via nvidia-smi (ou None)."""
    if not shutil.which("nvidia-smi"):
        return None
    cod, saida = run(_NVSMI, timeout=5)
    if cod != 0:
        return None
    p = [x.strip() for x in saida.strip().splitlines()[0].split(",")]
    if len(p) < 11:
        return None
    return {"nome": p[0], "temp": _num(p[1]), "uso": _num(p[2]), "vram_usada": _num(p[3]),
            "vram_total": _num(p[4]), "consumo": _num(p[5]), "freq": _num(p[6]),
            "freq_max": _num(p[7]), "fan": _num(p[8]), "driver": p[9], "throttle": p[10]}


class Sensores:
    """Coleta rápida (psutil) a cada chamada; coleta lenta (PowerShell) em cache."""

    def __init__(self):
        self.lento = {"cpu_temp": None, "gpu_util": None, "fontes": []}
        self.lento_t = 0
        self._io = psutil.disk_io_counters() if psutil else None
        self._io_t = time.time()
        psutil and psutil.cpu_percent(None)

    def atualizar_lento(self):
        d = ps_json(_SENSORES_PS, timeout=20, default=None)
        if d:
            self.lento = self._combinar(d)
        self.lento_t = time.time()

    @staticmethod
    def _combinar(d):
        """Une LibreHardwareMonitor (preferido), ACPI e contador de GPU do Windows."""
        from . import lhm
        r = {"cpu_temp": None, "gpu_util": d.get("gpu_engine"), "fontes": []}
        dados = lhm.interpretar(aslist(d.get("lhm"))) if d.get("lhm") else {}
        if dados:
            r.update(dados)
            r["fontes"].append("LibreHardwareMonitor")
        if r.get("cpu_temp") is None and d.get("acpi") is not None:
            r["cpu_temp"] = d["acpi"]
            r["fontes"].append("ACPI")
        return r

    def amostra(self):
        s = {"cpu": 0.0, "cpu_freq": None, "ram_pct": 0.0, "ram_usada": 0, "ram_total": 0,
             "disco_leitura": 0.0, "disco_escrita": 0.0, "cpu_temp": self.lento.get("cpu_temp"),
             "gpu_util": self.lento.get("gpu_util"), "gpu_temp": None, "gpu_vram": None,
             "gpu_consumo": None, "gpu_freq": None, "gpu_fan": None, "gpu_nome": None,
             "gpu_throttle": None, "fontes": self.lento.get("fontes", []), "cpu_consumo": self.lento.get("cpu_consumo"),
             "disco_temp": self.lento.get("disco_temp"), "ventoinhas": self.lento.get("ventoinhas")}
        for k in ("gpu_temp", "gpu_consumo", "gpu_freq", "gpu_fan"):
            s[k] = self.lento.get(k)
        if psutil:
            s["cpu"] = psutil.cpu_percent(None)
            f = psutil.cpu_freq()
            s["cpu_freq"] = f.current if f else None
            m = psutil.virtual_memory()
            s["ram_pct"], s["ram_usada"], s["ram_total"] = m.percent, m.used, m.total
            io = psutil.disk_io_counters()
            agora = time.time()
            if io and self._io and agora > self._io_t:
                dt = agora - self._io_t
                s["disco_leitura"] = (io.read_bytes - self._io.read_bytes) / dt / 1048576
                s["disco_escrita"] = (io.write_bytes - self._io.write_bytes) / dt / 1048576
            self._io, self._io_t = io, agora
        nv = ler_nvidia()
        if nv:
            s.update(gpu_temp=nv["temp"], gpu_util=nv["uso"], gpu_consumo=nv["consumo"],
                     gpu_freq=nv["freq"], gpu_fan=nv["fan"], gpu_nome=nv["nome"],
                     gpu_throttle=nv["throttle"],
                     gpu_vram=(nv["vram_usada"], nv["vram_total"]))
        return s


def discos_uso():
    """[(letra, total, usado, livre)] dos discos fixos."""
    res = []
    if not psutil:
        return res
    for p in psutil.disk_partitions(all=False):
        if IS_WIN and "fixed" not in p.opts.lower():
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
            res.append((p.mountpoint, u.total, u.used, u.free))
        except OSError:
            pass
    return res


def top_processos(n=8):
    """Processos que mais consomem memória: [(nome, pid, ram_bytes, cpu_pct)]."""
    if not psutil:
        return []
    lista = []
    for p in psutil.process_iter(["name", "pid", "memory_info"]):
        try:
            lista.append((p.info["name"] or "?", p.info["pid"], p.info["memory_info"].rss, 0.0))
        except (psutil.Error, AttributeError):
            continue
    lista.sort(key=lambda x: x[2], reverse=True)
    return lista[:n]


def programas_inicializacao():
    """[(nome, comando, origem)] das chaves Run do registro e da pasta Inicializar."""
    itens = []
    if not IS_WIN:
        return itens
    import os
    import winreg
    for raiz, nome_raiz in ((winreg.HKEY_CURRENT_USER, "Usuário"), (winreg.HKEY_LOCAL_MACHINE, "Todos os usuários")):
        try:
            with winreg.OpenKey(raiz, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    itens.append((n, str(v), nome_raiz))
                    i += 1
        except OSError:
            continue
    pasta = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(pasta):
        for f in os.listdir(pasta):
            if f.lower() != "desktop.ini":
                itens.append((f, os.path.join(pasta, f), "Pasta Inicializar"))
    return itens
