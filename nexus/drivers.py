"""Central de drivers: inventário, classificação, Windows Update e instalação com aprovação."""
import json
import re
from datetime import date, datetime

from .core import HIST, PASTA, aslist, carregar_config, criar_ponto_restauracao, log, ps_json

_PS_DRIVERS = r"""
function D($d){ if($d){ try{ $d.ToString('yyyy-MM-dd') }catch{ "$d" } } else { '' } }
$o = [ordered]@{}
$o.drivers = @(Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName } |
   Select-Object DeviceName,DeviceClass,DriverVersion,@{n='data';e={D $_.DriverDate}},Manufacturer,
                 DriverProviderName,InfName,IsSigned,DeviceID)
$o.erros = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } |
   Select-Object Name,ConfigManagerErrorCode,DeviceID,PNPClass)
$o | ConvertTo-Json -Compress -Depth 4
"""

# códigos mais comuns do Gerenciador de Dispositivos
CODIGOS_ERRO = {
    1: "Dispositivo mal configurado", 3: "Driver corrompido ou pouca memória",
    10: "O dispositivo não consegue iniciar", 12: "Conflito de recursos",
    18: "Reinstale os drivers", 22: "Dispositivo desativado",
    28: "Drivers não instalados", 31: "Dispositivo não funciona corretamente",
    37: "Falha ao iniciar o driver", 39: "Driver corrompido ou ausente",
    43: "O Windows parou o dispositivo (reportou problema)", 52: "Assinatura digital do driver não verificada",
}

CLASSES_CRITICAS = {"DISPLAY", "NET", "MEDIA", "BLUETOOTH", "HIDCLASS", "SYSTEM", "SCSIADAPTER", "HDC"}
GENERICOS = ("basic display", "standard vga", "basic render", "genérico", "generic", "controlador de vídeo padrão",
             "adaptador de vídeo básico")
SEM_NOME = ("pci device", "dispositivo pci", "unknown device", "dispositivo desconhecido", "base system device",
            "dispositivo de sistema base", "controlador pci", "pci simple")


def ler_drivers():
    """Lê todos os drivers e classifica cada um. Retorna (lista_drivers, lista_erros)."""
    d = ps_json(_PS_DRIVERS, timeout=180, default={}) or {}
    drivers, erros = aslist(d.get("drivers")), aslist(d.get("erros"))
    for x in drivers:
        classificar(x)
    return drivers, erros


def _idade_anos(data_txt):
    try:
        return (date.today() - datetime.strptime(data_txt, "%Y-%m-%d").date()).days / 365.25
    except (ValueError, TypeError):
        return None


def classificar(drv):
    """Define drv['status'] (ok/generico/antigo) e drv['nota']. Sem data nova ≠ problema:
    só marca 'antigo' em classes críticas e de fabricantes que não são a Microsoft."""
    nome = (drv.get("DeviceName") or "").lower()
    classe = (drv.get("DeviceClass") or "").upper()
    prov = (drv.get("DriverProviderName") or drv.get("Manufacturer") or "").lower()
    drv["status"], drv["nota"] = "ok", ""
    if classe in ("DISPLAY", "NET", "MEDIA") and any(g in nome for g in GENERICOS):
        drv["status"] = "generico"
        drv["nota"] = "Driver genérico da Microsoft: funciona, mas sem o desempenho do driver do fabricante."
        return
    idade = _idade_anos(drv.get("data"))
    if classe in ("DISPLAY", "NET", "MEDIA", "BLUETOOTH") and "microsoft" not in prov and idade and idade > 2.5:
        drv["status"] = "antigo"
        drv["nota"] = (f"Driver com {idade:.1f} anos. Pode haver versão mais nova, "
                       "mas só atualize se houver problema ou ganho comprovado.")


def classificar_erros(erros):
    res = []
    for e in erros:
        cod = e.get("ConfigManagerErrorCode")
        nome = e.get("Name") or "Dispositivo desconhecido"
        res.append({"nome": nome, "codigo": cod, "id": e.get("DeviceID", ""),
                    "classe": e.get("PNPClass") or "",
                    "causa": CODIGOS_ERRO.get(cod, "Erro no Gerenciador de Dispositivos"),
                    "sem_driver": cod in (28, 1) or any(s in nome.lower() for s in SEM_NOME)})
    return res


# ------------------------------------------------------------------ Windows Update
_PS_BUSCA = r"""
function D($d){ if($d){ try{ $d.ToString('yyyy-MM-dd') }catch{ "$d" } } else { '' } }
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
$l = @($r.Updates | ForEach-Object { [pscustomobject]@{
   id=$_.Identity.UpdateID; titulo=$_.Title; fab=$_.DriverManufacturer; modelo=$_.DriverModel;
   classe=$_.DriverClass; data=(D $_.DriverVerDate); tamanho=[int64]$_.MaxDownloadSize } })
ConvertTo-Json -InputObject $l -Compress
"""

_PS_INSTALA = r"""
$ids = @(%IDS%)
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
$col = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $r.Updates) { if ($ids -contains $u.Identity.UpdateID) {
    if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$col.Add($u) } }
if ($col.Count -eq 0) { '{"itens":[],"reboot":false}'; exit }
$d = $s.CreateUpdateDownloader(); $d.Updates = $col; [void]$d.Download()
$i = $s.CreateUpdateInstaller(); $i.Updates = $col
$res = $i.Install()
$itens = @(); for ($k=0; $k -lt $col.Count; $k++) {
   $itens += [pscustomobject]@{ titulo=$col.Item($k).Title; codigo=$res.GetUpdateResult($k).ResultCode } }
ConvertTo-Json -InputObject ([pscustomobject]@{ itens=$itens; reboot=[bool]$res.RebootRequired }) -Compress -Depth 4
"""


def buscar_atualizacoes():
    """Drivers pendentes no Windows Update (fonte oficial). Retorna lista de dicts ou None se falhar."""
    d = ps_json(_PS_BUSCA, timeout=900, default=None, lista=True)
    if d is None:
        return None
    return [x for x in aslist(d) if isinstance(x, dict) and x.get("id")]


def salvar_snapshot(drivers):
    """Guarda os drivers atuais (nome/versão/data) para consulta e possível reversão manual."""
    arq = PASTA / f"drivers_antes_{datetime.now():%Y%m%d_%H%M%S}.json"
    try:
        arq.write_text(json.dumps(
            [{k: x.get(k) for k in ("DeviceName", "DeviceClass", "DriverVersion", "data", "InfName")}
             for x in drivers], ensure_ascii=False, indent=1), encoding="utf-8")
        return str(arq)
    except OSError as e:
        log.error("snapshot drivers: %s", e)
        return ""


def instalar_atualizacoes(selecionadas, drivers_atuais, progresso=lambda m: None):
    """Instala SOMENTE as atualizações aprovadas pelo usuário.
    Antes: ponto de restauração (se ativado) e registro dos drivers atuais.
    Retorna (ok, mensagem, precisa_reiniciar)."""
    ids = [s["id"] for s in selecionadas if re.fullmatch(r"[0-9a-fA-F-]{36}", s.get("id", ""))]
    if not ids:
        return False, "Nenhuma atualização selecionada.", False
    if carregar_config().get("restauracao_auto", True):
        progresso("Criando ponto de restauração...")
        ok, msg = criar_ponto_restauracao("antes de instalar drivers")
        progresso(msg)
    snap = salvar_snapshot(drivers_atuais)
    if snap:
        progresso(f"Drivers atuais salvos em {snap}")
    progresso(f"Baixando e instalando {len(ids)} driver(s)... pode demorar vários minutos.")
    script = _PS_INSTALA.replace("%IDS%", ",".join(f"'{i}'" for i in ids))
    d = ps_json(script, timeout=3600, default=None)
    if not d:
        HIST.registrar("Instalar drivers", f"{len(ids)} drivers (Windows Update)", "Falhou")
        return False, "A instalação não retornou resultado. Veja o log.", False
    itens = aslist(d.get("itens"))
    certos = [i for i in itens if i.get("codigo") == 2]
    for i in itens:
        progresso(("OK   " if i.get("codigo") == 2 else f"ERRO({i.get('codigo')}) ") + (i.get("titulo") or ""))
    HIST.registrar("Instalar drivers", "aprovado pelo usuário (Windows Update)",
                   f"{len(certos)}/{len(itens)} instalados" + (f"; backup {snap}" if snap else ""))
    return bool(certos), f"{len(certos)} de {len(itens)} drivers instalados.", bool(d.get("reboot"))


# ------------------------------------------------------------------------ vídeo
SITES_GPU = {
    "nvidia": ("NVIDIA", "https://www.nvidia.com/Download/index.aspx"),
    "geforce": ("NVIDIA", "https://www.nvidia.com/Download/index.aspx"),
    "amd": ("AMD", "https://www.amd.com/en/support/download/drivers.html"),
    "radeon": ("AMD", "https://www.amd.com/en/support/download/drivers.html"),
    "intel": ("Intel", "https://www.intel.com/content/www/us/en/download-center/home.html"),
}


def marca_gpu(nome):
    baixo = (nome or "").lower()
    for chave, v in SITES_GPU.items():
        if chave in baixo:
            return v
    return None
