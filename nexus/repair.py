"""Reparação do Windows: SFC, DISM, CHKDSK e ferramentas nativas, com explicação e resultado claro."""
import os
import subprocess

from .core import HIST, IS_WIN, NO_WINDOW, log

SYSDRIVE = os.environ.get("SystemDrive", "C:")

# chave: nome, o que faz, comando, destrutivo/modifica o sistema, duração
FERRAMENTAS = {
    "sfc_verificar": dict(
        nome="SFC — verificar arquivos do Windows", cmd=["sfc", "/verifyonly"], altera=False, tempo="5 a 15 min",
        desc="O Verificador de Arquivos do Sistema confere se algum arquivo protegido do Windows foi alterado ou "
             "corrompido. Neste modo ele SÓ VERIFICA e não muda nada."),
    "sfc_reparar": dict(
        nome="SFC — reparar arquivos do Windows", cmd=["sfc", "/scannow"], altera=True, tempo="10 a 30 min",
        desc="Mesma verificação, mas substitui por cópias corretas os arquivos protegidos que estiverem danificados. "
             "É um reparo seguro e oficial; só rode se a verificação acusou problemas."),
    "dism_verificar": dict(
        nome="DISM — verificar imagem do Windows", cmd=["DISM", "/Online", "/Cleanup-Image", "/ScanHealth"], altera=False,
        tempo="5 a 20 min",
        desc="Examina o repositório de componentes do Windows (a 'imagem' usada pelo SFC para se reparar). "
             "Somente verifica; não altera nada."),
    "dism_reparar": dict(
        nome="DISM — reparar imagem do Windows", cmd=["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], altera=True,
        tempo="10 a 40 min",
        desc="Repara a imagem do Windows baixando componentes saudáveis pelo Windows Update. Precisa de internet. "
             "Use se o DISM acusou corrupção ou o SFC não consegue reparar."),
    "chkdsk": dict(
        nome=f"CHKDSK — verificar disco {SYSDRIVE} (somente leitura)", cmd=["chkdsk", SYSDRIVE], altera=False,
        tempo="2 a 10 min",
        desc="Verifica o sistema de arquivos do disco do Windows sem corrigir nada. Se acusar erros, o reparo "
             "(chkdsk /f) exige reiniciar o PC e deve ser feito com backup em dia."),
}


def _limpar(txt):
    return txt.replace("\x00", "").replace("\r", "")


def executar(chave, saida, cancelar=lambda: False):
    """Roda a ferramenta mostrando a saída linha a linha via saida(texto). Retorna (codigo, texto_completo)."""
    f = FERRAMENTAS[chave]
    if not IS_WIN:
        saida("Disponível somente no Windows.")
        return -1, ""
    acumulado = []
    try:
        p = subprocess.Popen(f["cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    except OSError as e:
        saida(f"Não foi possível iniciar: {e}")
        return -1, ""
    buf = b""
    while True:
        pedaco = p.stdout.read(64)
        if not pedaco:
            break
        buf += pedaco
        if b"\n" in buf or len(buf) > 200:
            partes = buf.split(b"\n")
            buf = partes.pop()
            for linha in partes:
                t = _limpar(linha.decode("utf-8", "replace")).strip()
                if t:
                    acumulado.append(t)
                    saida(t)
        if cancelar():
            p.terminate()
            saida("Cancelado pelo usuário.")
            break
    t = _limpar(buf.decode("utf-8", "replace")).strip()
    if t:
        acumulado.append(t)
        saida(t)
    p.wait()
    texto = "\n".join(acumulado)
    HIST.registrar("Reparação: " + f["nome"], "solicitado pelo usuário", f"código {p.returncode}")
    return p.returncode, texto


def interpretar(chave, codigo, texto):
    """Traduz a saída da ferramenta para linguagem simples. Retorna (estado, mensagem)
    com estado em 'ok', 'problema', 'reparado' ou 'erro'."""
    t = texto.lower()
    if chave.startswith("sfc"):
        if "não encontrou nenhuma violação" in t or "did not find any integrity violations" in t:
            return "ok", "Nenhum arquivo do Windows está corrompido."
        if "reparou com êxito" in t or "successfully repaired" in t:
            return "reparado", "Foram encontrados arquivos corrompidos e o Windows os reparou. Reinicie o PC."
        if "não pôde reparar" in t or "unable to fix" in t:
            return "problema", "Há arquivos corrompidos que o SFC não conseguiu reparar. Rode o DISM (reparar) e depois o SFC de novo."
        if "encontrou violações" in t or "found integrity violations" in t:
            return "problema", "Foram encontrados arquivos corrompidos. Rode 'SFC — reparar arquivos do Windows'."
        if "reinicializ" in t or "restart" in t or "pending" in t:
            return "erro", "Há um reparo/atualização pendente. Reinicie o PC e tente novamente."
        return ("erro", "Não foi possível concluir. Verifique se está como Administrador.") if codigo else ("ok", "Concluído.")
    if chave.startswith("dism"):
        if "nenhuma corrupção" in t or "no component store corruption" in t:
            return "ok", "A imagem do Windows está íntegra."
        if "operação foi concluída com êxito" in t or "completed successfully" in t:
            return "reparado" if chave == "dism_reparar" else "ok", "Operação concluída com sucesso."
        if "repar" in t and "corrup" in t and "reparável" in t or "repairable" in t:
            return "problema", "A imagem tem corrupção reparável. Rode 'DISM — reparar imagem do Windows'."
        return ("erro", "O DISM não concluiu. Verifique internet e permissões de Administrador.") if codigo else ("ok", "Concluído.")
    if chave == "chkdsk":
        if "nenhum problema foi encontrado" in t or "found no problems" in t or "no problems" in t:
            return "ok", "O sistema de arquivos não tem erros."
        if "encontrou" in t and "erro" in t or "errors found" in t:
            return "problema", "Foram encontrados erros no disco. Faça backup e agende o reparo (chkdsk /f) com cautela."
        return ("erro", "Não foi possível verificar o disco (precisa de Administrador).") if codigo else ("ok", "Concluído.")
    return "ok", "Concluído."
