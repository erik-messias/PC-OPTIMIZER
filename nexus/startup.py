"""Gerenciador de inicialização: lista, avalia e ativa/desativa programas de forma reversível.
Usa o mesmo mecanismo do Gerenciador de Tarefas (StartupApproved), sem apagar nenhuma entrada."""
import os
import re
import struct
import time

from .core import HIST, IS_WIN, aslist, log, ps_json

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

if IS_WIN:
    import winreg

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN32 = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APROV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"

# (nome da origem, hive, chave Run, chave StartupApproved)
FONTES = [("Usuário", "HKCU", RUN, APROV + r"\Run"),
          ("Todos os usuários", "HKLM", RUN, APROV + r"\Run"),
          ("Todos (32 bits)", "HKLM", RUN32, APROV + r"\Run32")]

PROTEGIDOS = ("securityhealth", "windows defender", "windowsdefender", "msmpeng", "windows security")
DESATIVAR = ("spotify", "discord", "steam", "teams", "onedrive", "epicgames", "epic games", "adobe", "skype",
             "whatsapp", "zoom", "telegram", "ccleaner", "itunes", "dropbox", "googledrive", "update", "updater",
             "launcher", "battle.net", "origin", "ubisoft", "gog", "utorrent", "bittorrent", "cortana")
MANTER = ("realtek", "nvidia", "amd", "radeon", "intel", "synaptics", "touchpad", "logi", "razer", "audio",
          "bluetooth", "wacom", "antivirus", "defender", "security", "vpn")


def _hive(nome):
    return winreg.HKEY_CURRENT_USER if nome == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def _executavel(cmd):
    cmd = os.path.expandvars(cmd.strip())
    if cmd.startswith('"'):
        return cmd[1:cmd.find('"', 1)] if '"' in cmd[1:] else cmd[1:]
    m = re.match(r"(.+?\.(?:exe|bat|cmd|lnk))", cmd, re.I)
    return m.group(1) if m else cmd.split(" ")[0]


def _estado(hive, chave_aprov, nome):
    """True = habilitado. Sem registro de aprovação, o Windows considera habilitado."""
    try:
        with winreg.OpenKey(_hive(hive), chave_aprov) as k:
            dados, _ = winreg.QueryValueEx(k, nome)
            return not (dados and dados[0] % 2 == 1)
    except OSError:
        return True


def definir_estado(hive, chave_aprov, nome, habilitar):
    """Escreve o byte de estado igual ao Gerenciador de Tarefas. Retorna (ok, msg)."""
    if habilitar:
        dados = b"\x02\x00\x00\x00" + b"\x00" * 8
    else:
        ft = int((time.time() + 11644473600) * 10_000_000)
        dados = b"\x03\x00\x00\x00" + struct.pack("<Q", ft)
    try:
        with winreg.CreateKeyEx(_hive(hive), chave_aprov, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, nome, 0, winreg.REG_BINARY, dados)
        return True, "ok"
    except OSError as e:
        return False, f"{e} (execute como Administrador para itens de 'Todos os usuários')"


def _fabricantes(caminhos):
    """{caminho: (fabricante, existe)} com uma única chamada ao PowerShell."""
    if not caminhos:
        return {}
    lista = ",".join("'" + c.replace("'", "''") + "'" for c in caminhos)
    d = ps_json(
        "$r=@(); foreach($p in @(" + lista + ")){ $e=Test-Path -LiteralPath $p; $f=''; "
        "if($e){ try{ $f=(Get-Item -LiteralPath $p).VersionInfo.CompanyName }catch{} } "
        "$r += [pscustomobject]@{p=$p;f=\"$f\";e=$e} }; ConvertTo-Json -InputObject $r -Compress",
        timeout=60, default=[], lista=True)
    return {x["p"]: (x.get("f") or "", bool(x.get("e"))) for x in aslist(d) if isinstance(x, dict)}


def _recomendar(nome, cmd, existe):
    n = f"{nome} {cmd}".lower()
    if not existe:
        return "suspeito", "O arquivo não existe mais. Entrada órfã ou possivelmente indesejada."
    if any(s in n for s in PROTEGIDOS):
        return "proteger", "Componente de segurança do Windows. Mantenha ativado."
    if any(s in n for s in ("\\temp\\", "appdata\\local\\temp", "\\users\\public\\")):
        return "suspeito", "Executa de uma pasta temporária, o que é incomum. Investigue antes de manter."
    if any(s in n for s in MANTER):
        return "manter", "Componente de hardware/segurança. Em geral deve ficar ativado."
    if any(s in n for s in DESATIVAR):
        return "desativar", "Costuma ser seguro desativar: o programa abre quando você precisar."
    return "avaliar", "Sem recomendação. Se não reconhece ou não usa, pode desativar."


def listar():
    """Retorna lista de dicts: nome, cmd, origem, habilitado, fab, existe, rec, motivo, ram, hive, chave_aprov."""
    itens = []
    if not IS_WIN:
        return itens
    for origem, hive, chave, aprov in FONTES:
        try:
            with winreg.OpenKey(_hive(hive), chave) as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    itens.append(dict(nome=n, cmd=str(v), origem=origem, hive=hive, chave_aprov=aprov,
                                      habilitado=_estado(hive, aprov, n), pasta=False))
                    i += 1
        except OSError:
            continue
    pasta = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(pasta):
        for f in os.listdir(pasta):
            if f.lower() != "desktop.ini":
                itens.append(dict(nome=f, cmd=os.path.join(pasta, f), origem="Pasta Inicializar", hive="HKCU",
                                  chave_aprov=APROV + r"\StartupFolder", pasta=True,
                                  habilitado=_estado("HKCU", APROV + r"\StartupFolder", f)))
    exes = {it["nome"]: _executavel(it["cmd"]) for it in itens}
    info = _fabricantes(sorted({e for e in exes.values() if e}))
    rodando = {}
    if psutil:
        for p in psutil.process_iter(["exe", "memory_info"]):
            try:
                if p.info["exe"]:
                    rodando[p.info["exe"].lower()] = rodando.get(p.info["exe"].lower(), 0) + p.info["memory_info"].rss
            except (psutil.Error, AttributeError):
                continue
    for it in itens:
        exe = exes[it["nome"]]
        fab, existe = info.get(exe, ("", os.path.exists(exe)))
        it["fab"], it["existe"] = fab, existe
        it["ram"] = rodando.get(exe.lower(), 0)
        it["rec"], it["motivo"] = _recomendar(it["nome"], it["cmd"], existe)
    ordem = {"suspeito": 0, "desativar": 1, "avaliar": 2, "manter": 3, "proteger": 4}
    itens.sort(key=lambda x: (not x["habilitado"], ordem[x["rec"]], x["nome"].lower()))
    return itens


def alternar(item, habilitar, motivo="pedido do usuário"):
    """Ativa/desativa a inicialização automática (reversível). Retorna (ok, msg)."""
    if not habilitar and item["rec"] == "proteger":
        return False, "Este item é de segurança do Windows e não será desativado."
    ok, msg = definir_estado(item["hive"], item["chave_aprov"], item["nome"], habilitar)
    if not ok:
        return False, msg
    HIST.registrar("Inicialização " + ("ativada" if habilitar else "desativada"), f"{item['nome']} ({motivo})", "Concluída",
                   {"tipo": "startup", "hive": item["hive"], "chave": item["chave_aprov"], "nome": item["nome"],
                    "habilitar": not habilitar})
    return True, f"{item['nome']}: " + ("ativado" if habilitar else "desativado") + " na inicialização."
