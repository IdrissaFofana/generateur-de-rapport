"""Fonctions utilitaires : dates françaises, nettoyage de texte, formatage."""
import re
from datetime import date, datetime

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
_MOIS_IDX = {m: i + 1 for i, m in enumerate(MOIS_FR)}
_MOIS_IDX.update({"fevrier": 2, "aout": 8, "decembre": 12})

# Format KSC : "septembre 23, 2026 14:06:46"
_RE_DATE_KSC = re.compile(
    r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)"
    r"\s+(\d{1,2}),\s*(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
    re.IGNORECASE)
# Format MDR : "31.08.2026 00:00"
_RE_DATE_MDR = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?")


def nettoyer(texte):
    """Aplatit les retours à la ligne et recolle les mots coupés par un tiret."""
    if texte is None:
        return ""
    t = texte.replace("\n", " ")
    t = re.sub(r"-\s+(?=[A-Za-z0-9])", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def date_ksc(texte):
    """Convertit une date KSC en datetime (ou None)."""
    if not texte:
        return None
    m = _RE_DATE_KSC.search(nettoyer(texte))
    if not m:
        return None
    mois = _MOIS_IDX[m.group(1).lower()]
    h, mi, s = (int(x) if x else 0 for x in m.group(4, 5, 6))
    return datetime(int(m.group(3)), mois, int(m.group(2)), h, mi, s)


def dates_ksc(texte):
    """Toutes les dates KSC trouvées dans un texte."""
    t = nettoyer(texte)
    return [date_ksc(m.group(0)) for m in _RE_DATE_KSC.finditer(t)]


def date_mdr(texte):
    if not texte:
        return None
    m = _RE_DATE_MDR.search(texte)
    if not m:
        return None
    h, mi = (int(x) if x else 0 for x in m.group(4, 5))
    return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), h, mi)


def fmt_date(d):
    """1er septembre 2026"""
    if d is None:
        return "—"
    if isinstance(d, datetime):
        d = d.date()
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS_FR[d.month - 1]} {d.year}"


def fmt_date_courte(d):
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y")


def fmt_mois(annee, mois):
    return f"{MOIS_FR[mois - 1].capitalize()} {annee}"


def fmt_nb(n):
    """Nombre avec espace insécable pour les milliers."""
    return f"{n:,}".replace(",", " ")


def fmt_pct(part, total):
    if not total:
        return "0 %"
    return f"{100 * part / total:.1f} %".replace(".", ",")


def pluriel(n, singulier, pluriel_=None):
    return singulier if n <= 1 else (pluriel_ or singulier + "s")


def bornes_mois(annee, mois):
    debut = date(annee, mois, 1)
    fin = date(annee + (mois == 12), mois % 12 + 1, 1)
    return debut, fin  # fin exclue


def mois_courant(aujourd_hui=None):
    """Mois traité par défaut : le mois en cours à partir du 25, sinon le précédent."""
    auj = aujourd_hui or date.today()
    if auj.day >= 25:
        return auj.year, auj.month
    return (auj.year - 1, 12) if auj.month == 1 else (auj.year, auj.month - 1)


def mois_decale(annee, mois, delta):
    """(annee, mois) décalé de delta mois (négatif = vers le passé)."""
    rang = annee * 12 + mois - 1 + delta
    return rang // 12, rang % 12 + 1
