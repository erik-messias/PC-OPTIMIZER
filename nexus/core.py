"""Base do NEXUS PC: utilidades, logs, configurações, histórico (SQLite) e restauração."""
import ctypes
import json
import logging
import os
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP = "NEXUS PC"
VERSAO = "2.0.0"
IS_WIN = platform.system() == "Windows"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PASTA = Path(os.environ.get("APPDATA", str(Path.home()))) / "NexusPC"
PASTA_LOGS = PASTA / "logs"
PASTA_REL = PASTA / "relatorios"
for _p in (PASTA, PASTA_LOGS, PASTA_REL):
    try:
        _p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

# ------------------------------------------------------------------- logging
log = logging.getLogger("nexus")
if not log.handlers:
    log.setLevel(logging.INFO)
    try:
        _h = RotatingFileHandler(PASTA_LOGS / "nexus.log", maxBytes=1_000_000,
                                 backupCount=3, encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(_h)
    except OSError:
        log.addHandler(logging.NullHandler())


# ----------------------------------------------------------------- utilidades
def fmt_bytes(b):
    b = float(b or 0)
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
    """Roda um comando sem abrir janela. Retorna (codigo, saida)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -2, "tempo esgotado"
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def ps(script, timeout=120):
    """Roda PowerShell. Retorna (codigo, saida)."""
    if not IS_WIN:
        return -1, "somente Windows"
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-Command", "$ProgressPreference='SilentlyContinue';"
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script], timeout=timeout)


def ps_json(script, timeout=120, default=None, lista=False):
    """Roda PowerShell e converte a saída JSON em objeto Python (lista=True se esperar array)."""
    cod, saida = ps(script, timeout)
    pares = (("[", "]"), ("{", "}")) if lista else (("{", "}"), ("[", "]"))
    for ab, fe in pares:
        try:
            i, j = saida.index(ab), saida.rindex(fe)
            return json.loads(saida[i:j + 1])
        except ValueError:
            continue
    log.warning("ps_json sem JSON (cod %s): %s", cod, saida[:200])
    return default


def aslist(x):
    """PowerShell devolve objeto único em vez de lista quando só há 1 item."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def recurso(nome):
    base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent))
    return Path(base) / nome


# ---------------------------------------------------------------- configurações
_CONF = PASTA / "config.json"
PADRAO = {"restauracao_auto": True, "limpar_navegadores": False, "intervalo_monitor_s": 1}


def carregar_config():
    try:
        return {**PADRAO, **json.loads(_CONF.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(PADRAO)


def salvar_config(c):
    try:
        _CONF.write_text(json.dumps(c, indent=2), encoding="utf-8")
    except OSError as e:
        log.error("config: %s", e)


# -------------------------------------------------------------------- histórico
class Historico:
    """Registro de todas as alterações, com possibilidade de reversão."""

    def __init__(self):
        self.arq = PASTA / "historico.db"
        with self._con() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS historico(
                id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, acao TEXT, motivo TEXT,
                resultado TEXT, reversivel INTEGER, desfazer TEXT, revertido INTEGER DEFAULT 0)""")

    def _con(self):
        return sqlite3.connect(self.arq)

    def registrar(self, acao, motivo, resultado, desfazer=None):
        """desfazer = dict {'tipo': ..., ...} ou None se não for reversível."""
        with self._con() as c:
            cur = c.execute(
                "INSERT INTO historico(data,acao,motivo,resultado,reversivel,desfazer) VALUES(?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), acao, motivo, resultado,
                 1 if desfazer else 0, json.dumps(desfazer) if desfazer else None))
            log.info("HIST %s | %s | %s", acao, motivo, resultado)
            return cur.lastrowid

    def listar(self, limite=200):
        with self._con() as c:
            return c.execute("SELECT id,data,acao,motivo,resultado,reversivel,revertido,desfazer "
                             "FROM historico ORDER BY id DESC LIMIT ?", (limite,)).fetchall()

    def marcar_revertido(self, id_):
        with self._con() as c:
            c.execute("UPDATE historico SET revertido=1 WHERE id=?", (id_,))

    def reverter(self, id_):
        """Desfaz uma alteração registrada. Retorna (ok, mensagem)."""
        with self._con() as c:
            row = c.execute("SELECT desfazer,revertido FROM historico WHERE id=?", (id_,)).fetchone()
        if not row or not row[0]:
            return False, "Esta alteração não pode ser revertida automaticamente."
        if row[1]:
            return False, "Já foi revertida."
        d = json.loads(row[0])
        tipo = d.get("tipo")
        if tipo == "plano_energia":
            cod, saida = run(["powercfg", "/setactive", d["guid"]])
            ok = cod == 0
        elif tipo == "gpu_pref":
            cod, saida = ps(_ps_gpu_pref_restore(d["exe"], d.get("anterior")))
            ok = cod == 0
        elif tipo == "startup":
            from . import startup
            ok, saida = startup.definir_estado(d["hive"], d["chave"], d["nome"], d["habilitar"])
            cod = 0 if ok else 1
        else:
            return False, "Tipo de reversão desconhecido."
        if ok:
            self.marcar_revertido(id_)
            self.registrar("Reversão", f"Desfez alteração #{id_}", "Concluída")
            return True, "Alteração revertida."
        return False, f"Falhou: {saida.strip()[:150]}"


def _ps_gpu_pref_restore(exe, anterior):
    chave = "HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"
    exe_ps = exe.replace("'", "''")
    if anterior:
        a = anterior.replace("'", "''")
        return f"Set-ItemProperty -Path '{chave}' -Name '{exe_ps}' -Value '{a}'"
    return f"Remove-ItemProperty -Path '{chave}' -Name '{exe_ps}' -ErrorAction SilentlyContinue"


HIST = Historico()


# ------------------------------------------------------------------ restauração
def criar_ponto_restauracao(motivo="NEXUS PC"):
    """Cria ponto de restauração. Retorna (ok, mensagem)."""
    desc = f"NEXUS PC - {motivo}"[:60].replace("'", "")
    cmd = ("Enable-ComputerRestore -Drive $env:SystemDrive -ErrorAction SilentlyContinue; "
           f"Checkpoint-Computer -Description '{desc}' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop")
    cod, saida = ps(cmd, timeout=240)
    if cod == 0:
        HIST.registrar("Ponto de restauração", motivo, "Criado")
        return True, "Ponto de restauração criado."
    msg = "Não criado (o Windows permite 1 a cada 24h, ou a proteção do sistema está desligada)."
    HIST.registrar("Ponto de restauração", motivo, "Não criado")
    return False, msg


# ----------------------------------------------------------------- plano de energia
def plano_ativo():
    """(guid, nome) do plano de energia atual."""
    cod, saida = run(["powercfg", "/getactivescheme"])
    guid = nome = ""
    for p in saida.split():
        if len(p) == 36 and p.count("-") == 4:
            guid = p
    if "(" in saida and ")" in saida:
        nome = saida[saida.rindex("(") + 1:saida.rindex(")")]
    return guid, nome


def _guid_por_nome(chaves):
    _, saida = run(["powercfg", "/list"])
    for linha in saida.splitlines():
        if any(k in linha.lower() for k in chaves):
            for p in linha.split():
                if len(p) == 36 and p.count("-") == 4:
                    return p
    return None


PLANOS = {
    "maximo": (["desempenho máximo", "desempenho maximo", "ultimate", "alto desempenho", "high performance"],
               "e9a42b02-d5df-448d-aa00-03f14749eb61"),
    "equilibrado": (["equilibrado", "balanced"], None),
    "economia": (["economia de energia", "power saver"], None),
}


def aplicar_plano(chave, motivo):
    """Troca o plano de energia registrando o anterior para reversão."""
    if not IS_WIN:
        return False, "somente Windows"
    ant_guid, ant_nome = plano_ativo()
    nomes, dup = PLANOS[chave]
    guid = _guid_por_nome(nomes)
    if not guid and dup:
        run(["powercfg", "-duplicatescheme", dup])
        guid = _guid_por_nome(nomes)
    if not guid:
        return False, "Plano de energia não encontrado neste PC."
    cod, saida = run(["powercfg", "/setactive", guid])
    if cod != 0:
        return False, saida.strip()[:150]
    _, novo = plano_ativo()
    HIST.registrar("Plano de energia", motivo, f"{ant_nome} → {novo}",
                   {"tipo": "plano_energia", "guid": ant_guid} if ant_guid else None)
    return True, f"Plano de energia: {novo}"
