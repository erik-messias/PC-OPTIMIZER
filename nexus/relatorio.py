"""Relatório completo em HTML (arquivo único, abre em qualquer navegador)."""
from datetime import datetime
from html import escape

from . import diagnostics as dg
from .core import fmt_bytes

_COR = {"crítico": "#f87171", "alto": "#fb923c", "médio": "#fbbf24", "baixo": "#3b82f6", "info": "#7d8a9c"}


def _cor_nota(n):
    return "#34d399" if n >= 85 else "#22d3ee" if n >= 70 else "#fbbf24" if n >= 50 else "#f87171"


def gerar(ctx, problemas, geral, notas):
    inv = ctx.get("inv", {})
    so = inv.get("os") or {}
    hw = []
    for c in inv.get("cpu", []):
        hw.append(("Processador", f"{c.get('Name', '').strip()} — {c.get('NumberOfCores')} núcleos / {c.get('NumberOfLogicalProcessors')} threads"))
    for p in inv.get("placa", []):
        hw.append(("Placa-mãe", f"{p.get('Manufacturer')} {p.get('Product')}"))
    for b in inv.get("bios", []):
        hw.append(("BIOS", f"{b.get('Manufacturer')} {b.get('SMBIOSBIOSVersion')} ({b.get('data')})"))
    for g in inv.get("gpu", []):
        hw.append(("Vídeo", f"{g.get('Name')} — driver {g.get('DriverVersion')} ({g.get('driverdata')})"))
    ram = inv.get("ram", [])
    if ram:
        hw.append(("Memória", f"{fmt_bytes(sum((m.get('Capacity') or 0) for m in ram))} em {len(ram)} pente(s), "
                              f"{max((m.get('Speed') or 0) for m in ram)} MHz"))
    for d in inv.get("discos", []):
        hw.append(("Disco", f"{d.get('FriendlyName')} — {d.get('tipo')} {fmt_bytes(d.get('Size'))} — saúde {d.get('saude')}"))
    e = escape
    cats = "".join(
        f'<div class="cat"><span>{e(c)}</span><div class="bar"><i style="width:{notas[c][0]}%;background:{_cor_nota(notas[c][0])}"></i></div>'
        f'<b style="color:{_cor_nota(notas[c][0])}">{notas[c][0]}</b></div>' for c in dg.CATEGORIAS)
    probs = "".join(
        f'<div class="p" style="border-left-color:{_COR[p.gravidade]}"><div class="t"><b>{e(p.titulo)}</b>'
        f'<span style="color:{_COR[p.gravidade]}">{p.gravidade.upper()}</span><em>{p.status}</em></div>'
        f'<p>{e(p.explicacao)}</p>'
        + (f'<p class="m"><b>Possíveis causas:</b> {e("; ".join(p.causas))}</p>' if p.causas else "")
        + (f'<p class="m"><b>Recomendação:</b> {e(p.recomendacao)}</p>' if p.recomendacao else "")
        + (f'<p class="m"><b>Evidência:</b> {e(p.evidencia)}</p>' if p.evidencia else "") + "</div>" for p in problemas)
    hwh = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in hw)
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>NEXUS PC — Relatório</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{background:#080b12;color:#e6edf3;font:15px/1.5 Segoe UI,system-ui,sans-serif;margin:0;padding:32px;max-width:960px;margin:auto}}
h1{{color:#22d3ee;margin:0}}h2{{color:#a78bfa;font-size:13px;letter-spacing:.1em;text-transform:uppercase;margin-top:32px}}
.sub{{color:#7d8a9c}}.score{{font-size:72px;font-weight:700;line-height:1}}.cat{{display:flex;gap:12px;align-items:center;margin:8px 0}}
.cat span{{width:130px}}.bar{{flex:1;height:10px;background:#151b28;border-radius:5px;overflow:hidden}}.bar i{{display:block;height:100%}}
table{{width:100%;border-collapse:collapse}}td{{padding:6px 8px;border-bottom:1px solid #1e2736}}td:first-child{{color:#7d8a9c;width:130px}}
.p{{background:#10151f;border-left:4px solid;border-radius:6px;padding:10px 14px;margin:10px 0}}.p p{{margin:6px 0}}
.t{{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}}.t em{{color:#7d8a9c;font-style:normal;margin-left:auto}}.m{{color:#9fb0c3;font-size:14px}}
@media print{{body{{background:#fff;color:#000}}}}</style>
<h1>NEXUS PC</h1><div class="sub">Relatório de análise — {datetime.now():%d/%m/%Y %H:%M} — {e(so.get('Caption', ''))} (build {e(str(so.get('BuildNumber', '')))})</div>
<h2>Saúde do sistema</h2><div class="score" style="color:{_cor_nota(geral)}">{geral}<span style="font-size:24px;color:#7d8a9c"> / 100</span></div>
<div style="margin-top:16px">{cats}</div>
<p class="sub">Problemas confirmados descontam: crítico −35, alto −20, médio −10, baixo −4; suspeitas descontam metade. Hardware antigo não perde pontos.</p>
<h2>Hardware</h2><table>{hwh}</table>
<h2>Problemas ({len(problemas)})</h2>{probs or '<p>Nenhum problema encontrado.</p>'}
</html>"""
