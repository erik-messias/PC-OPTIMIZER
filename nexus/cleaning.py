"""Limpeza inteligente: mostra o que será removido (tamanho, local, consequência) antes de apagar."""
import ctypes
import glob
import os
from ctypes import wintypes

from .core import HIST, IS_WIN, fmt_bytes, log


def _env(nome, padrao=""):
    return os.environ.get(nome, padrao)


def _categorias():
    local, win, prog = _env("LOCALAPPDATA"), _env("WINDIR", r"C:\Windows"), _env("PROGRAMDATA")
    temp = _env("TEMP")
    return [
        dict(chave="temp_usuario", nome="Arquivos temporários do usuário",
             caminhos=[p for p in {temp, os.path.join(local, "Temp") if local else ""} if p],
             consequencia="Seguro. Arquivos em uso por programas abertos são pulados.", padrao=True),
        dict(chave="temp_windows", nome="Arquivos temporários do Windows",
             caminhos=[os.path.join(win, "Temp")],
             consequencia="Seguro. Precisa de Administrador; arquivos em uso são pulados.", padrao=True),
        dict(chave="lixeira", nome="Lixeira", caminhos=[], especial="lixeira",
             consequencia="Os arquivos na lixeira deixam de poder ser restaurados.", padrao=True),
        dict(chave="wer", nome="Relatórios antigos de erros do Windows",
             caminhos=[os.path.join(prog, "Microsoft", "Windows", "WER", "ReportArchive"),
                       os.path.join(prog, "Microsoft", "Windows", "WER", "ReportQueue")],
             consequencia="Seguro. Só remove relatórios de falhas já enviados ou ignorados.", padrao=True),
        dict(chave="dumps", nome="Despejos de memória (crash dumps)",
             caminhos=[os.path.join(win, "Minidump"), os.path.join(local, "CrashDumps")] if local else [],
             consequencia="Seguro, mas apaga informações usadas para investigar telas azuis.", padrao=True),
        dict(chave="miniaturas", nome="Cache de miniaturas do Explorer",
             caminhos=[os.path.join(local, "Microsoft", "Windows", "Explorer", "thumbcache_*.db")] if local else [],
             consequencia="O Windows recria sozinho; pastas de imagens demoram um pouco mais na 1ª abertura.",
             padrao=True),
        dict(chave="wu_download", nome="Arquivos de atualização já baixados",
             caminhos=[os.path.join(win, "SoftwareDistribution", "Download")],
             consequencia="O Windows Update baixa de novo se precisar. Precisa de Administrador.", padrao=False),
        dict(chave="navegadores", nome="Cache de navegadores (Edge, Chrome, Firefox)",
             caminhos=([os.path.join(local, "Microsoft", "Edge", "User Data", "*", "Cache", "Cache_Data"),
                        os.path.join(local, "Microsoft", "Edge", "User Data", "*", "Code Cache"),
                        os.path.join(local, "Google", "Chrome", "User Data", "*", "Cache", "Cache_Data"),
                        os.path.join(local, "Google", "Chrome", "User Data", "*", "Code Cache"),
                        os.path.join(local, "Mozilla", "Firefox", "Profiles", "*", "cache2")] if local else []),
             consequencia="Senhas e histórico NÃO são afetados, mas sites carregam mais devagar na 1ª vez. "
                          "Feche os navegadores antes.", padrao=False, exige_autorizacao=True),
    ]


class _RBInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("tamanho", ctypes.c_longlong), ("itens", ctypes.c_longlong)]


def _tam_lixeira():
    if not IS_WIN:
        return 0, 0
    info = _RBInfo()
    info.cbSize = ctypes.sizeof(_RBInfo)
    try:
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return info.tamanho, info.itens
    except Exception:  # noqa: BLE001
        pass
    return 0, 0


def _expandir(padrao):
    return glob.glob(padrao) if any(c in padrao for c in "*?") else ([padrao] if os.path.exists(padrao) else [])


def _arquivos(cat):
    """Gera (caminho_arquivo) de todos os arquivos que a categoria removeria."""
    for padrao in cat["caminhos"]:
        for alvo in _expandir(padrao):
            if os.path.isfile(alvo):
                yield alvo
            elif os.path.isdir(alvo):
                for raiz, _, arqs in os.walk(alvo):
                    for a in arqs:
                        yield os.path.join(raiz, a)


def analisar():
    """Retorna lista de categorias com 'bytes', 'arquivos' e 'locais'."""
    res = []
    for cat in _categorias():
        total = n = 0
        if cat.get("especial") == "lixeira":
            total, n = _tam_lixeira()
        else:
            for f in _arquivos(cat):
                try:
                    total += os.path.getsize(f)
                    n += 1
                except OSError:
                    pass
        cat["bytes"], cat["arquivos"] = total, n
        cat["locais"] = "; ".join(cat["caminhos"]) if cat["caminhos"] else "Lixeira do Windows"
        res.append(cat)
    return res


def limpar(chaves, progresso=lambda m: None):
    """Remove apenas as categorias escolhidas. Retorna bytes liberados."""
    liberado = 0
    for cat in _categorias():
        if cat["chave"] not in chaves:
            continue
        b = n = pulados = 0
        if cat.get("especial") == "lixeira":
            b, _ = _tam_lixeira()
            try:
                ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
                n = 1
            except Exception:  # noqa: BLE001
                pulados = 1
        else:
            for f in _arquivos(cat):
                try:
                    tam = os.path.getsize(f)
                    os.remove(f)
                    b += tam
                    n += 1
                except OSError:
                    pulados += 1
            for padrao in cat["caminhos"]:
                for alvo in _expandir(padrao):
                    if os.path.isdir(alvo):
                        for raiz, dirs, _ in os.walk(alvo, topdown=False):
                            for d in dirs:
                                try:
                                    os.rmdir(os.path.join(raiz, d))
                                except OSError:
                                    pass
        liberado += b
        progresso(f"{cat['nome']}: {fmt_bytes(b)} liberados ({pulados} itens em uso foram pulados)")
        HIST.registrar("Limpeza", cat["nome"], f"{fmt_bytes(b)} liberados")
    return liberado
