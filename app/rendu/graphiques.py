"""Graphiques du rapport, produits à partir des données JSON.

Format « svg » (vectoriel, pour le PDF HTML) ou « png » (pour l'export Word).
"""
import glob
import io
import os
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

# Palette validée (daltonisme) — tons proches de la charte ESAY
SERIE = "#1E6FA8"
SERIE_CLAIRE = "#9DC3E0"
ORANGE = "#E08A2C"
CRITIQUE = "#C0392B"
BON = "#3C8D2F"
GRIS = "#A7B1B8"
ENCRE = "#1F2933"
ENCRE_DOUCE = "#5B6770"
GRILLE = "#E3E7EA"

# Police Carlito embarquée : mêmes mesures de texte dans les graphiques que dans le document
for _police in glob.glob(os.path.join(os.path.dirname(__file__), "..", "static", "polices", "*.ttf")):
    font_manager.fontManager.addfont(_police)

plt.rcParams.update({
    "font.family": ["Carlito", "Calibri", "DejaVu Sans"],
    "font.size": 9, "axes.edgecolor": GRILLE, "axes.labelcolor": ENCRE_DOUCE,
    "xtick.color": ENCRE_DOUCE, "ytick.color": ENCRE,
    "axes.spines.top": False, "axes.spines.right": False,
    "svg.fonttype": "none",  # texte conservé en texte : police du document, net et sélectionnable
})


def _exporter(fig, fmt):
    tampon = io.BytesIO()
    fig.tight_layout()
    fig.savefig(tampon, format=fmt, dpi=200, facecolor="white")
    plt.close(fig)
    donnees = tampon.getvalue()
    if fmt == "svg":
        texte = donnees.decode("utf-8")
        return texte[texte.index("<svg"):]  # sans l'en-tête XML, pour l'insertion en ligne
    return donnees


def _jours(debut, fin):
    return [debut + timedelta(d) for d in range((fin - debut).days)]


def _axe_jours(ax, debut, fin):
    ax.set_xlim(debut - timedelta(hours=18), fin - timedelta(hours=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(bymonthday=range(1, 32, 3)))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.grid(True, color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)


def _barres_classement(ax, libelles, valeurs):
    pos = list(range(len(libelles)))[::-1]
    ax.set_yticks(pos)
    ax.set_yticklabels(libelles)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    return pos


def postes_mdr(mdr, debut, fin, fmt="svg"):
    jours = {date.fromisoformat(j): n for j, n in mdr["jours"]}
    manquants = [date.fromisoformat(j) for j in mdr["jours_manquants"]]
    moyenne = mdr["moyenne_ouvres"]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    x = sorted(jours)
    ax.bar(x, [jours[j] for j in x], color=[SERIE if j.weekday() < 5 else SERIE_CLAIRE for j in x],
           width=0.75, edgecolor="white", linewidth=0.8, zorder=2)
    for j in manquants:
        ax.axvspan(j - timedelta(hours=10), j + timedelta(hours=10), facecolor="#E9EDF0",
                   edgecolor="#AEB8C0", hatch="///", linewidth=0.5, zorder=1)
    legende = [Patch(color=SERIE, label="Jour ouvré"), Patch(color=SERIE_CLAIRE, label="Week-end")]
    if manquants:
        legende.append(Patch(facecolor="#E9EDF0", edgecolor="#AEB8C0", hatch="///", label="Données non disponibles"))
    if moyenne:
        ax.axhline(moyenne, color=ENCRE_DOUCE, linestyle="--", linewidth=1, zorder=3)
        legende.append(Line2D([], [], color=ENCRE_DOUCE, linestyle="--",
                              label=f"Moyenne jours ouvrés : {moyenne:.1f}".replace(".", ",")))
    _axe_jours(ax, debut, fin)
    ax.set_ylabel("Postes actifs")
    ax.legend(handles=legende, loc="upper left", bbox_to_anchor=(0, 1.22), ncol=4, frameon=False, fontsize=8)
    return _exporter(fig, fmt)


def etat_parc(p, fmt="svg"):
    ok, avert, crit = p["ok"], p["avertissement"], p["critique"]
    total = ok + avert + crit or 1
    fig, ax = plt.subplots(figsize=(7.2, 1.1))
    gauche, legende = 0, []
    for valeur, couleur, libelle in ((ok, BON, "OK"), (avert, ORANGE, "Avertissement"), (crit, CRITIQUE, "Critique")):
        legende.append(Patch(color=couleur, label=f"{libelle} : {valeur}"))
        if valeur:
            ax.barh(0, valeur, left=gauche, color=couleur, height=0.6, edgecolor="white", linewidth=2)
            if valeur / total > 0.15:
                ax.text(gauche + valeur / 2, 0, f"{valeur / total:.0%}".replace("%", " %"), ha="center",
                        va="center", color="white", fontsize=9, fontweight="bold")
            gauche += valeur
    ax.set_xlim(0, total)
    ax.axis("off")
    ax.legend(handles=legende, loc="upper center", bbox_to_anchor=(0.5, 0.05), ncol=3, frameon=False, fontsize=8.5)
    return _exporter(fig, fmt)


def categories_menaces(m, fmt="svg"):
    cats = list(m["categories"].items())
    libelles, valeurs = [c for c, _ in cats], [n for _, n in cats]
    fig, ax = plt.subplots(figsize=(7.2, 0.45 + 0.32 * len(cats)))
    pos = _barres_classement(ax, libelles, valeurs)
    ax.barh(pos, valeurs, color=SERIE, height=0.6, edgecolor="white")
    maxi = max(valeurs) if valeurs else 1
    for p_, v in zip(pos, valeurs):
        ax.text(v + maxi * 0.01, p_, str(v), va="center", fontsize=8, color=ENCRE)
    ax.set_xlim(0, maxi * 1.12)
    return _exporter(fig, fmt)


def detections_par_jour(m, debut, fin, fmt="svg"):
    par_jour = {date.fromisoformat(j): n for j, n in m["par_jour"].items()}
    jours = _jours(debut, fin)
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    ax.bar(jours, [par_jour.get(j, 0) for j in jours], color=SERIE, width=0.75, edgecolor="white", linewidth=0.8)
    _axe_jours(ax, debut, fin)
    ax.set_ylabel("Détections")
    return _exporter(fig, fmt)


def vulnerabilites_applis(v, fmt="svg", maxi=8):
    top = sorted(v["applications"], key=lambda x: -x[1]["total"])[:maxi]
    crit = [i["critiques"] for _, i in top]
    elev = [i["elevees"] for _, i in top]
    autres = [i["total"] - i["critiques"] - i["elevees"] for _, i in top]
    fig, ax = plt.subplots(figsize=(7.2, 0.6 + 0.34 * len(top)))
    pos = _barres_classement(ax, [a for a, _ in top], [i["total"] for _, i in top])
    ax.barh(pos, crit, color=CRITIQUE, height=0.6, edgecolor="white", linewidth=1.5, label="Critique")
    ax.barh(pos, elev, left=crit, color=ORANGE, height=0.6, edgecolor="white", linewidth=1.5, label="Élevée")
    if any(autres):
        ax.barh(pos, autres, left=[c + e for c, e in zip(crit, elev)], color=GRIS, height=0.6,
                edgecolor="white", linewidth=1.5, label="Autre")
    haut = max((i["total"] for _, i in top), default=1)
    for p_, (_, i) in zip(pos, top):
        ax.text(i["total"] + haut * 0.01, p_, str(i["total"]), va="center", fontsize=8, color=ENCRE)
    ax.set_xlim(0, haut * 1.1)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    return _exporter(fig, fmt)


def barres_mensuelles(libelles, valeurs, etiquette, fmt="svg"):
    """Barres verticales (une par mois), valeur au-dessus de chaque barre non nulle."""
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    x = list(range(len(libelles)))
    ax.bar(x, valeurs, color=SERIE, width=0.6 if len(x) > 3 else 0.4, edgecolor="white", linewidth=0.8, zorder=2)
    haut = max(valeurs) if valeurs and max(valeurs) else 1
    for xi, v in zip(x, valeurs):
        if v:
            ax.text(xi, v + haut * 0.03, f"{v:g}".replace(".", ","), ha="center", va="bottom", fontsize=8, color=ENCRE)
    ax.set_xticks(x)
    ax.set_xticklabels(libelles, fontsize=8)
    ax.set_ylim(0, haut * 1.2)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    ax.yaxis.grid(True, color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0)
    ax.set_ylabel(etiquette)
    return _exporter(fig, fmt)


def barres_horizontales(paires, fmt="svg"):
    """Classement horizontal [(libellé, valeur)], du plus grand au plus petit."""
    libelles, valeurs = [p[0] for p in paires], [p[1] for p in paires]
    fig, ax = plt.subplots(figsize=(7.2, 0.45 + 0.32 * len(paires)))
    pos = _barres_classement(ax, libelles, valeurs)
    ax.barh(pos, valeurs, color=SERIE, height=0.6, edgecolor="white")
    maxi = max(valeurs) if valeurs else 1
    for p_, v in zip(pos, valeurs):
        ax.text(v + maxi * 0.01, p_, f"{v:g}".replace(".", ","), va="center", fontsize=8, color=ENCRE)
    ax.set_xlim(0, maxi * 1.12)
    return _exporter(fig, fmt)


def evolution(points, indicateurs, fmt="svg"):
    """Petits multiples : une courbe par indicateur (échelles indépendantes, jamais de double axe).
    points : [{"libelle", "indicateurs"}] du plus ancien au plus récent · indicateurs : [(clé, titre)]."""
    suivis = [(c, t) for c, t in indicateurs if any(p["indicateurs"].get(c) is not None for p in points)]
    if len(points) < 2 or not suivis:
        return None
    colonnes = 2 if len(suivis) > 1 else 1
    lignes = -(-len(suivis) // colonnes)
    fig, axes = plt.subplots(lignes, colonnes, figsize=(7.2, 1.85 * lignes), squeeze=False)
    x = list(range(len(points)))
    libelles = [p["libelle"] for p in points]
    for ax, (cle, titre) in zip(axes.flat, suivis):
        y = [p["indicateurs"].get(cle) for p in points]
        xs = [i for i, v in zip(x, y) if v is not None]
        ys = [v for v in y if v is not None]
        ax.fill_between(xs, ys, color=SERIE, alpha=0.1, linewidth=0)
        ax.plot(xs, ys, color=SERIE, linewidth=2, solid_capstyle="round", solid_joinstyle="round", zorder=3)
        ax.scatter(xs, ys, s=30, color=SERIE, edgecolors="white", linewidths=1.5, zorder=4)
        dernier = ys[-1]
        ax.annotate(f"{dernier:g}".replace(".", ","), (xs[-1], dernier), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8.5, fontweight="bold", color=ENCRE)
        ax.set_title(titre, loc="left", fontsize=9, color=ENCRE, pad=4)
        ax.set_xticks(x)
        ax.set_xticklabels(libelles, fontsize=7)
        pas = max(1, round(len(points) / 6))
        for i, lib in enumerate(ax.get_xticklabels()):
            lib.set_visible(i % pas == 0 or i == len(points) - 1)
        ax.set_ylim(bottom=0, top=max(ys) * 1.25 or 1)
        ax.set_xlim(-0.3, len(points) - 0.4)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
        ax.yaxis.grid(True, color=GRILLE, linewidth=0.8)
        ax.tick_params(axis="both", length=0, labelsize=7)
        ax.set_axisbelow(True)
    for ax in list(axes.flat)[len(suivis):]:
        ax.axis("off")
    return _exporter(fig, fmt)


def tous(d, fmt="svg"):
    """Tous les graphiques applicables au rapport : {nom: svg | png}."""
    debut, fin = date.fromisoformat(d["debut"]), date.fromisoformat(d["fin"])
    g = {}
    if d["mdr"] and d["mdr"]["jours"]:
        g["mdr"] = postes_mdr(d["mdr"], debut, fin, fmt)
    if d["protection"]:
        g["parc"] = etat_parc(d["protection"], fmt)
    if d["menaces"] and d["menaces"]["detections"]:
        g["categories"] = categories_menaces(d["menaces"], fmt)
        g["menaces_jour"] = detections_par_jour(d["menaces"], debut, fin, fmt)
    if d["vulnerabilites"] and d["vulnerabilites"]["applications"]:
        g["vulns"] = vulnerabilites_applis(d["vulnerabilites"], fmt)
    return g
