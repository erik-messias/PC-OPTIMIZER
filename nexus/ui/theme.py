"""Identidade visual do NEXUS PC: preto/grafite, azul elétrico e ciano, roxo secundário."""
import sys
from tkinter import ttk

BG = "#080b12"
SIDEBAR = "#0b0f18"
PANEL = "#10151f"
PANEL2 = "#151b28"
BORDA = "#1e2736"
TEXTO = "#e6edf3"
MUDO = "#7d8a9c"
CIANO = "#22d3ee"
AZUL = "#3b82f6"
ROXO = "#a78bfa"
VERDE = "#34d399"
VERMELHO = "#f87171"
AMARELO = "#fbbf24"
LARANJA = "#fb923c"

GRAVIDADE_COR = {"crítico": VERMELHO, "alto": LARANJA, "médio": AMARELO, "baixo": AZUL, "info": MUDO}

if sys.platform == "win32":
    F = "Segoe UI"
    FS = "Segoe UI Semibold"
    FM = "Consolas"
else:
    F, FS, FM = "DejaVu Sans", "DejaVu Sans", "DejaVu Sans Mono"


def fonte(tam=10, negrito=False, mono=False):
    fam = FM if mono else F
    return (fam, tam, "bold") if negrito else (fam, tam)


def cor_nota(n):
    return VERDE if n >= 85 else CIANO if n >= 70 else AMARELO if n >= 50 else VERMELHO


def rotulo_nota(n):
    return "Excelente" if n >= 90 else "Bom" if n >= 75 else "Atenção" if n >= 50 else "Crítico"


def aplicar_estilos(root):
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXTO, rowheight=26,
                borderwidth=0, font=(F, 10), bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Treeview.Heading", background=PANEL2, foreground=CIANO, relief="flat", font=(FS, 10), borderwidth=0)
    s.map("Treeview", background=[("selected", "#1d3557")], foreground=[("selected", "#ffffff")])
    s.map("Treeview.Heading", background=[("active", PANEL2)])
    for o in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        s.configure(o, background=BORDA, troughcolor=PANEL, bordercolor=PANEL, lightcolor=BORDA, darkcolor=BORDA,
                    arrowcolor=MUDO, relief="flat", gripcount=0)
        s.map(o, background=[("active", MUDO), ("pressed", CIANO)])
    s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXTO, arrowcolor=CIANO,
                bordercolor=BORDA, lightcolor=PANEL2, darkcolor=PANEL2, selectbackground=PANEL2, selectforeground=TEXTO)
    s.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXTO)],
          selectbackground=[("readonly", PANEL2)], selectforeground=[("readonly", TEXTO)])
    for w in ("Checkbutton", "Radiobutton"):
        root.option_add(f"*{w}.highlightThickness", 0)
    root.option_add("*TCombobox*Listbox.background", PANEL2)
    root.option_add("*TCombobox*Listbox.foreground", TEXTO)
    root.option_add("*TCombobox*Listbox.selectBackground", "#1d3557")


def misturar(c1, c2, t):
    """Mistura duas cores hex (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))
