"""Petites courbes d'évolution (SVG en ligne) pour l'interface web : une courbe par indicateur.

Une seule série par graphique (pas de légende : le titre de la carte nomme l'indicateur),
trait de 2 px, points de 8 px cerclés de blanc, dernier point étiqueté, infobulle au survol.
"""
from markupsafe import Markup, escape

L, H = 300, 128                   # repère du viewBox
G, D, HAUT, BAS = 34, 30, 12, 24  # marges : gauche (graduations), droite (étiquette), haut, bas (mois)


def _echelle_max(maxi):
    """Borne haute « ronde » de l'axe (1, 2, 2,5, 5 × 10^n)."""
    if maxi <= 0:
        return 1
    puissance = 10 ** (len(str(int(maxi))) - 1)
    for pas in (1, 2, 2.5, 5, 10):
        if maxi <= pas * puissance:
            return pas * puissance
    return 10 * puissance


def _nb(v):
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.1f}".replace(".", ",")
    return f"{int(v):,}".replace(",", " ")


def mini_courbe(points, cle):
    """points : [{"libelle", "indicateurs": {cle: valeur}}] du plus ancien au plus récent."""
    valeurs = [p["indicateurs"].get(cle) for p in points]
    connues = [v for v in valeurs if v is not None]
    if not connues:
        return Markup('<p class="aide courbe-vide">Aucune donnée sur la période.</p>')
    haut = _echelle_max(max(connues))
    n = len(points)
    largeur, hauteur = L - G - D, H - HAUT - BAS

    def x(i):
        return G + (largeur / 2 if n == 1 else i * largeur / (n - 1))

    def y(v):
        return HAUT + hauteur * (1 - v / haut)

    morceaux = [f'<svg class="courbe" viewBox="0 0 {L} {H}" role="img" aria-label="Évolution sur {n} mois">']
    for frac in (0, .5, 1):  # grille : 3 lignes fines, graduations à gauche
        yy = HAUT + hauteur * frac
        morceaux.append(f'<line class="grille" x1="{G}" x2="{L - D}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        morceaux.append(f'<text class="graduation" x="{G - 6}" y="{yy + 3.5:.1f}" text-anchor="end">{_nb(haut * (1 - frac))}</text>')
    pas = max(1, -(-n // 4))  # au plus ~4 libellés de mois, sinon ils se touchent
    affiches = {i for i in range(0, n, pas) if i == 0 or n - 1 - i >= pas} | {n - 1}  # le dernier mois, sans chevauchement
    for i, p in enumerate(points):
        if i in affiches:
            morceaux.append(f'<text class="mois" x="{x(i):.1f}" y="{H - 6}" text-anchor="middle">{escape(p["libelle"])}</text>')

    # Tracé : interrompu là où la donnée manque (mois sans export)
    segments, courant = [], []
    for i, v in enumerate(valeurs):
        if v is None:
            if courant:
                segments.append(courant)
            courant = []
        else:
            courant.append((x(i), y(v)))
    if courant:
        segments.append(courant)
    for seg in segments:
        chemin = " ".join(f"{'M' if k == 0 else 'L'}{a:.1f},{b:.1f}" for k, (a, b) in enumerate(seg))
        if len(seg) > 1:
            base = HAUT + hauteur
            morceaux.append(f'<path class="aire" d="{chemin} L{seg[-1][0]:.1f},{base} L{seg[0][0]:.1f},{base} Z"/>')
        morceaux.append(f'<path class="trait" d="{chemin}"/>')

    dernier = max(i for i, v in enumerate(valeurs) if v is not None)
    for i, (p, v) in enumerate(zip(points, valeurs)):
        if v is None:
            continue
        info = escape(f"{p['libelle']} : {_nb(v)}")
        morceaux.append(f'<g class="point{" dernier" if i == dernier else ""}"><title>{info}</title>'
                        f'<circle class="cible" cx="{x(i):.1f}" cy="{y(v):.1f}" r="11"/>'
                        f'<circle class="marque" cx="{x(i):.1f}" cy="{y(v):.1f}" r="4"/></g>')
    vx, vy = x(dernier), y(valeurs[dernier])
    morceaux.append(f'<text class="valeur" x="{vx + 8:.1f}" y="{vy + 4:.1f}">{_nb(valeurs[dernier])}</text>')
    morceaux.append("</svg>")
    return Markup("".join(morceaux))


def variation(points, cle):
    """Écart entre les deux derniers mois connus : (delta, texte) ou None."""
    connues = [p["indicateurs"].get(cle) for p in points if p["indicateurs"].get(cle) is not None]
    if len(connues) < 2:
        return None
    delta = connues[-1] - connues[-2]
    if isinstance(delta, float):
        delta = round(delta, 1)
    texte = "stable" if delta == 0 else ("+" if delta > 0 else "−") + _nb(abs(delta))
    return delta, texte

