"""Verificação de atualização pelo GitHub Releases."""
import json
import re
import urllib.request

from .core import VERSAO, log

REPO = "erik-messias/PC-OPTIMIZER"


def _versao(txt):
    return tuple(int(x) for x in re.findall(r"\d+", txt or "")[:3]) or (0,)


def verificar(timeout=6):
    """Retorna (nova_disponivel, tag, url, mensagem)."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "NexusPC", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.info("update: %s", e)
        return False, "", "", "Não foi possível verificar (sem internet?)."
    tag, url = d.get("tag_name", ""), d.get("html_url", "")
    if _versao(tag) > _versao(VERSAO):
        return True, tag, url, f"Nova versão disponível: {tag}"
    return False, tag, url, f"Você está na versão mais recente ({VERSAO})."
