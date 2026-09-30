"""Import d'anciens rapports d'intervention (PDF ou Word) : extraction du texte et des champs par indices.

Les formats historiques varient (modèle « rapport d'intervention » à libellés, rapports globaux de plusieurs
pages) : on cherche des repères robustes (nom d'un client connu, dates, type dans le titre, sections numérotées,
puces). Tout ce qui n'est pas trouvé reste vide et le rapport importé passe par une vérification humaine ; le
texte complet est conservé pour la base de connaissances.
"""
import io
import re
import unicodedata
from datetime import date, time

TYPES_MOTS = [  # ordre : le plus spécifique d'abord
    ("migration", ("migration", "reconstruction")), ("deploiement", ("deploiement", "installation")),
    ("incident", ("incident", "compromission", "infection")), ("audit", ("audit",)), ("formation", ("formation",)),
    ("maintenance", ("maintenance", "mise a jour")), ("assistance", ("assistance", "support", "depannage")),
]
PUCES = ("•", "-", "–", "▪", "◦", "*", "", "·")
RE_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
RE_HEURES = re.compile(r"(\d{1,2})\s*[hH:]\s*(\d{2})?\s*(?:-|–|à|a)\s*(\d{1,2})\s*[hH:]\s*(\d{2})?")
RE_TITRE = re.compile(r"^\s*(\d{1,2})[.)]\s+(.{3,90})$")
RE_STATUT = re.compile(r"statut\s+global\s*:?\s*\W*\s*(ok|partiel|échec|echec)", re.IGNORECASE)


def _plat(texte):
    return unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()


def extraire_texte(contenu, extension):
    """Texte brut d'un PDF (PyMuPDF) ou d'un Word (paragraphes puis cellules des tableaux, dans l'ordre)."""
    if extension == ".pdf":
        import fitz
        with fitz.open(stream=contenu, filetype="pdf") as d:
            return "\n".join(p.get_text() for p in d)
    import docx
    document = docx.Document(io.BytesIO(contenu))
    morceaux = [p.text for p in document.paragraphs]
    for t in document.tables:
        for ligne in t.rows:
            vus = []
            for cellule in ligne.cells:  # les cellules fusionnées sont répétées par python-docx
                if cellule.text not in vus:
                    vus.append(cellule.text)
            morceaux.append(" | ".join(v.strip() for v in vus if v.strip()))
    return "\n".join(morceaux)


def _date(j, m, a):
    try:
        return date(int(a), int(m), int(j))
    except ValueError:
        return None


def _sections(lignes):
    """{titre normalisé: [lignes]} pour les titres numérotés « 1. Objet … »."""
    sections, courant = {}, None
    for l in lignes:
        m = RE_TITRE.match(l)
        if m and not RE_DATE.search(l):
            courant = _plat(m.group(2)).strip(" :")
            sections[courant] = []
        elif courant is not None:
            sections[courant].append(l)
    return sections


def _section(sections, *mots):
    """Première section dont le titre contient un des mots, par ordre de priorité des mots."""
    for m in mots:
        for titre, contenu in sections.items():
            if m in titre:
                return contenu
    return []


def _recoller_puces(lignes):
    """Dans les PDF, une puce est souvent extraite seule sur sa ligne : on la recolle au texte qui suit."""
    resultat, i = [], 0
    while i < len(lignes):
        t = lignes[i].strip()
        if t in PUCES and i + 1 < len(lignes):
            resultat.append(t + " " + lignes[i + 1].strip())
            i += 2
            continue
        resultat.append(lignes[i])
        i += 1
    return resultat


EN_TETES = {"module / solution", "resultat", "actions effectuees", "domaine", "niveau", "element", "valeur",
            "blocage / probleme", "impact / consequence"}


def _elements(lignes, maximum=40):
    """Puces d'une section (une puce sur plusieurs lignes est recollée) ; à défaut, ses lignes non vides."""
    if any(l.strip()[:1] in PUCES for l in lignes):
        puces = []
        for l in lignes:
            t = l.strip()
            if not t or (t.isupper() and len(t) > 10):  # vide, ou en-tête / pied de page répété en majuscules
                continue
            if t[:1] in PUCES:
                puces.append(t.lstrip("".join(PUCES)).strip())
            elif puces and not puces[-1].rstrip().endswith((".", ";", "!", "?", ":")) and not t.endswith(":"):
                puces[-1] += " " + t  # la puce précédente n'était pas terminée : suite sur la ligne suivante
        return [p for p in puces if len(p) > 3][:maximum]
    return [l.strip() for l in lignes if len(l.strip()) > 3 and not l.strip().endswith(":")][:maximum]


def analyser(texte, clients, utilisateurs=()):
    """clients : [(id, nom, code, tenants)] · utilisateurs : noms connus. Renvoie les champs trouvés et la liste
    des champs manquants (à vérifier)."""
    lignes = _recoller_puces([l.rstrip() for l in (texte or "").splitlines()])
    plat = _plat(texte)
    r = {"client_id": None, "type": None, "date_debut": None, "date_fin": None, "heure_debut": None, "heure_fin": None,
         "intervenants": [], "objet": "", "contexte": "", "resultat": [], "statut_global": None, "points_bloquants": [],
         "recommandations": []}

    # Client : nom (ou tenant) d'un client connu le plus cité, ou valeur après « Client : »
    scores = {}
    for cid, nom, code, tenants in clients:
        for cle in {nom, *(tenants or [])}:
            if cle and len(cle) >= 3:
                n = len(re.findall(r"(?<![a-z0-9])" + re.escape(_plat(cle)) + r"(?![a-z0-9])", plat))
                scores[cid] = scores.get(cid, 0) + n
    if scores and max(scores.values()) > 0:
        r["client_id"] = max(scores, key=scores.get)

    # Type : d'abord dans le début du document (titre), puis partout
    for zone in (plat[:600], plat):
        trouve = next((t for t, mots in TYPES_MOTS if any(m in zone for m in mots)), None)
        if trouve:
            r["type"] = trouve
            break

    # Dates : « du … au … », sinon les premières dates du document
    dates = [d for d in (_date(*m.groups()) for m in RE_DATE.finditer(texte)) if d and 2015 <= d.year <= 2100]
    m = re.search(r"du\s+(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})\s+au\s+(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", texte, re.IGNORECASE)
    if m:
        r["date_debut"] = _date(*RE_DATE.search(m.group(1)).groups())
        r["date_fin"] = _date(*RE_DATE.search(m.group(2)).groups())
    elif dates:
        r["date_debut"] = r["date_fin"] = dates[0]
    h = RE_HEURES.search(texte)
    if h:
        try:
            r["heure_debut"] = time(int(h.group(1)), int(h.group(2) or 0))
            r["heure_fin"] = time(int(h.group(3)), int(h.group(4) or 0))
        except ValueError:
            pass

    # Intervenants : utilisateurs connus cités dans le document
    r["intervenants"] = [u for u in utilisateurs if u and _plat(u) in plat]

    # Sections
    sections = _sections(lignes)
    objet = _section(sections, "objet", "objectif")
    r["objet"] = " ".join(l.strip() for l in objet if l.strip())[:2000]
    r["contexte"] = " ".join(l.strip() for l in _section(sections, "contexte") if l.strip())[:1000]
    resultat = _section(sections, "resultat global", "resultat", "actions realisees", "travaux realises", "deroulement", "realisation")
    r["resultat"] = [x for x in _elements(resultat) if not RE_STATUT.search(x) and not _plat(x).startswith(("statut", "resume"))
                     and _plat(x).strip(" :") not in EN_TETES]
    r["recommandations"] = _elements(_section(sections, "recommandation", "preconisation"), 20)
    s = RE_STATUT.search(texte)
    if s:
        r["statut_global"] = {"ok": "OK", "partiel": "Partiel"}.get(s.group(1).lower(), "Échec")

    # Points bloquants : une puce = un problème, la ligne suivante (non puce) = son impact
    bloquants = _section(sections, "bloquant", "anomalie", "difficulte", "probleme")
    courant = None
    for l in bloquants:
        t = l.strip()
        if not t or _plat(t).startswith(("blocage", "impact")):
            continue
        if t[:1] in PUCES:
            courant = {"probleme": t.lstrip("".join(PUCES)).strip(), "impact": "", "action": "", "responsable": "",
                       "echeance": None, "plan_action": False}
            r["points_bloquants"].append(courant)
        elif courant is not None:
            courant["impact"] = (courant["impact"] + " " + t).strip()  # impact, éventuellement sur plusieurs lignes
    r["points_bloquants"] = r["points_bloquants"][:15]

    manquants = [libelle for cle, libelle in (("client_id", "client"), ("type", "type"), ("date_debut", "date"),
                                                ("objet", "objet"), ("resultat", "résultat")) if not r[cle]]
    r["manquants"] = manquants
    return r
