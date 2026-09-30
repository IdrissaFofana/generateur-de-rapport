"""Service technique : assistances mensuelles planifiées, classements, base de connaissances, techniciens.

Règle métier : un client sous « assistance mensuelle » doit recevoir au moins une assistance par mois.
Chaque mois, une assistance « à planifier » est créée pour lui ; elle devient « réalisée » dès qu'un rapport
d'intervention validé du mois la couvre (type assistance ou maintenance, ou rapport rédigé depuis le planning).
"""
import re
import unicodedata
from collections import Counter
from datetime import date, datetime

from sqlalchemy import String, cast, func, or_, select

from .modeles import (VALIDE, AssistancePlanifiee, Certification, Client, Formation, Intervention, Utilisateur)
from .moteur.outils import bornes_mois

TYPES_COMPTES = ("assistance", "maintenance")  # interventions qui valent assistance mensuelle


# --------------------------------------------------------------------------- #
# Planification
# --------------------------------------------------------------------------- #
def clients_sous_assistance(db, annee, mois):
    debut, fin = bornes_mois(annee, mois)
    return db.scalars(select(Client).where(
        Client.actif.is_(True), Client.assistance_mensuelle.is_(True),
        or_(Client.assistance_depuis.is_(None), Client.assistance_depuis < fin)).order_by(Client.nom)).all()


def assurer_planning(db, annee, mois):
    """Crée les assistances « à planifier » manquantes du mois, puis rapproche les rapports réalisés."""
    existants = set(db.scalars(select(AssistancePlanifiee.client_id).where(
        AssistancePlanifiee.annee == annee, AssistancePlanifiee.mois == mois)))
    crees = 0
    for c in clients_sous_assistance(db, annee, mois):
        if c.id not in existants:
            db.add(AssistancePlanifiee(client_id=c.id, annee=annee, mois=mois, statut="a_planifier", justification=""))
            crees += 1
    db.flush()
    rapprocher(db, annee, mois)
    return crees


def rapprocher(db, annee, mois):
    """Une assistance non réalisée devient réalisée si un rapport validé du mois la couvre."""
    debut, fin = bornes_mois(annee, mois)
    for a in db.scalars(select(AssistancePlanifiee).where(AssistancePlanifiee.annee == annee, AssistancePlanifiee.mois == mois,
                                                          AssistancePlanifiee.statut != "realisee")):
        lie = a.intervention if a.intervention_id else None
        if lie is None or lie.statut != VALIDE:
            lie = db.scalar(select(Intervention).where(
                Intervention.client_id == a.client_id, Intervention.statut == VALIDE, Intervention.type.in_(TYPES_COMPTES),
                Intervention.date_debut >= debut, Intervention.date_debut < fin).order_by(Intervention.date_debut))
        if lie is not None and lie.statut == VALIDE:
            a.intervention_id, a.statut = lie.id, "realisee"
            a.date_prevue = a.date_prevue or lie.date_debut


def etat(a, aujourd_hui=None):
    """(clé, libellé) affichés : ajoute « en retard » quand la date prévue ou le mois est dépassé."""
    aujourd_hui = aujourd_hui or date.today()
    if a.statut in ("realisee", "reportee"):
        return a.statut, {"realisee": "Réalisée", "reportee": "Reportée"}[a.statut]
    fin_mois = bornes_mois(a.annee, a.mois)[1]
    if aujourd_hui >= fin_mois or (a.date_prevue and a.date_prevue < aujourd_hui):
        return "retard", "En retard"
    return a.statut, {"a_planifier": "À planifier", "planifiee": "Planifiée"}[a.statut]


def planning(db, annee, mois):
    lignes = db.scalars(select(AssistancePlanifiee).where(AssistancePlanifiee.annee == annee, AssistancePlanifiee.mois == mois)
                        .join(Client).order_by(Client.nom)).all()
    comptes = Counter(etat(a)[0] for a in lignes)
    dues = len(lignes)
    faites = comptes.get("realisee", 0)
    return {"lignes": lignes, "comptes": comptes, "dues": dues, "realisees": faites,
            "taux": round(100 * faites / (dues - comptes.get("reportee", 0))) if dues - comptes.get("reportee", 0) else None}


# --------------------------------------------------------------------------- #
# Durées et classements
# --------------------------------------------------------------------------- #
def duree_heures(i):
    """Heures de présence : (départ − arrivée) × nombre de jours ; None si les heures ne sont pas renseignées."""
    if not (i.heure_debut and i.heure_fin):
        return None
    par_jour = (datetime.combine(date.min, i.heure_fin) - datetime.combine(date.min, i.heure_debut)).total_seconds() / 3600
    if par_jour <= 0:
        return None
    return round(par_jour * ((i.date_fin - i.date_debut).days + 1), 1)


def interventions_periode(db, debut, fin, valides_seulement=True):
    requete = select(Intervention).where(Intervention.date_debut >= debut, Intervention.date_debut < fin)
    if valides_seulement:
        requete = requete.where(Intervention.statut == VALIDE)
    return db.scalars(requete.order_by(Intervention.date_debut)).all()


def classement_clients(db, debut, fin):
    """Par client : interventions, types, heures, assistances dues / réalisées, points bloquants, dernière visite."""
    lignes = {}
    for i in interventions_periode(db, debut, fin):
        l = lignes.setdefault(i.client_id, {"client": i.client, "interventions": 0, "types": Counter(), "heures": 0.0,
                                            "points": 0, "derniere": None, "site": 0})
        l["interventions"] += 1
        l["types"][i.libelle_type] += 1
        l["heures"] += duree_heures(i) or 0
        l["points"] += len(i.points_bloquants or [])
        l["site"] += 1 if i.mode == "site" else 0
        l["derniere"] = max(filter(None, (l["derniere"], i.date_fin)))
    rang = lambda a, m: a * 12 + m
    for a in db.scalars(select(AssistancePlanifiee).where(
            AssistancePlanifiee.annee * 12 + AssistancePlanifiee.mois >= rang(debut.year, debut.month),
            AssistancePlanifiee.annee * 12 + AssistancePlanifiee.mois < rang(fin.year, fin.month) + (1 if fin.day > 1 else 0))):
        l = lignes.setdefault(a.client_id, {"client": a.client, "interventions": 0, "types": Counter(), "heures": 0.0,
                                            "points": 0, "derniere": None, "site": 0})
        l["dues"] = l.get("dues", 0) + (0 if a.statut == "reportee" else 1)
        l["faites"] = l.get("faites", 0) + (1 if a.statut == "realisee" else 0)
    for l in lignes.values():
        l["heures"] = round(l["heures"], 1)
        l["conformite"] = round(100 * l["faites"] / l["dues"]) if l.get("dues") else None
    return sorted(lignes.values(), key=lambda l: (-l["interventions"], l["client"].nom))


def _normaliser(texte):
    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def participe(utilisateur, intervention):
    """Un utilisateur a participé si son nom figure parmi les intervenants (saisie libre, casse et accents ignorés)."""
    nom = _normaliser(utilisateur.nom)
    return any(nom and (nom == _normaliser(x) or nom in _normaliser(x)) for x in intervention.intervenants or [])


def classement_techniciens(db, debut, fin):
    utilisateurs = db.scalars(select(Utilisateur).where(Utilisateur.actif.is_(True)).order_by(Utilisateur.nom)).all()
    interventions = interventions_periode(db, debut, fin)
    lignes = []
    for u in utilisateurs:
        siennes = [i for i in interventions if participe(u, i)]
        certifs = db.scalars(select(Certification).where(Certification.utilisateur_id == u.id,
                                                          Certification.obtenue_le >= debut, Certification.obtenue_le < fin)).all()
        formations = db.scalars(select(Formation).where(Formation.utilisateur_id == u.id, or_(
            Formation.fin.is_(None), Formation.fin >= debut), or_(Formation.debut.is_(None), Formation.debut < fin))).all()
        if not (siennes or certifs or formations or u.role in ("operateur", "validateur")):
            continue
        lignes.append({"utilisateur": u, "interventions": len(siennes), "heures": round(sum(duree_heures(i) or 0 for i in siennes), 1),
                       "clients": len({i.client_id for i in siennes}), "types": Counter(i.libelle_type for i in siennes),
                       "certifications": len(certifs), "formations": len(formations)})
    return sorted(lignes, key=lambda l: (-l["interventions"], l["utilisateur"].nom))


# --------------------------------------------------------------------------- #
# Certifications
# --------------------------------------------------------------------------- #
def etat_certification(c, aujourd_hui=None):
    aujourd_hui = aujourd_hui or date.today()
    if c.expire_le is None:
        return "valide", "Sans expiration"
    jours = (c.expire_le - aujourd_hui).days
    if jours < 0:
        return "expiree", f"Expirée depuis {-jours} j"
    if jours <= 90:
        return "bientot", f"Expire dans {jours} j"
    return "valide", f"Valide jusqu'au {c.expire_le:%d/%m/%Y}"


# --------------------------------------------------------------------------- #
# Base de connaissances
# --------------------------------------------------------------------------- #
def rechercher(db, texte, limite=60):
    """Interventions validées (ou importées) dont un champ contient tous les mots recherchés."""
    mots = [m for m in re.split(r"\s+", texte.strip()) if len(m) >= 2][:6]
    if not mots:
        return []
    corpus = func.concat_ws(" ", Intervention.objet, cast(Intervention.resultat, String), cast(Intervention.points_bloquants, String),
                            cast(Intervention.recommandations, String), cast(Intervention.travaux, String), Intervention.texte_source)
    requete = select(Intervention).where(or_(Intervention.statut == VALIDE, Intervention.source == "import"))
    for m in mots:
        requete = requete.where(corpus.ilike(f"%{m}%"))
    resultats = []
    for i in db.scalars(requete.order_by(Intervention.date_debut.desc()).limit(limite)):
        extraits = []
        for champ in [i.objet] + list(i.resultat or []) + [p.get("probleme", "") + " — " + (p.get("action") or p.get("impact") or "")
                                                            for p in i.points_bloquants or []] + list(i.recommandations or []):
            if champ and any(m.lower() in champ.lower() for m in mots):
                extraits.append(champ)
        if not extraits and i.texte_source:
            pos = min((i.texte_source.lower().find(m.lower()) for m in mots if m.lower() in i.texte_source.lower()), default=0)
            extraits.append("… " + " ".join(i.texte_source[max(pos - 90, 0):pos + 160].split()) + " …")
        resultats.append({"intervention": i, "extraits": extraits[:3]})
    return resultats


MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "sur", "pour", "dans", "par", "au", "aux", "a",
              "en", "est", "pas", "ne", "l", "d", "sont", "avec", "the", "of"}


def mots_significatifs(texte):
    """Mots d'un problème, sans mots vides, avec une racinisation légère (pluriel, accents) : « Ports fermés » ≈ « port fermé »."""
    mots = re.findall(r"[a-z0-9]+", _normaliser(texte))
    racines = set()
    for m in mots:
        if m in MOTS_VIDES or len(m) <= 2:
            continue
        if len(m) > 3 and m[-1] in "sx" and not m.isdigit():
            m = m[:-1]
        racines.add(m)
    return racines


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


SEUIL_SIMILARITE = 0.6


def problemes_recurrents(db, depuis=None, minimum_clients=2):
    """Points bloquants rencontrés chez plusieurs clients. Regroupement glouton par similarité de Jaccard
    (≥ 60 % de mots significatifs communs) : tolère les variations de formulation."""
    groupes = []
    requete = select(Intervention).where(or_(Intervention.statut == VALIDE, Intervention.source == "import"))
    if depuis:
        requete = requete.where(Intervention.date_debut >= depuis)
    for i in db.scalars(requete.order_by(Intervention.date_debut)):
        for p in i.points_bloquants or []:
            mots = mots_significatifs(p.get("probleme", ""))
            if not mots:
                continue
            g = max(groupes, key=lambda g: jaccard(mots, g["mots"]), default=None)
            if g is None or jaccard(mots, g["mots"]) < SEUIL_SIMILARITE:
                g = {"mots": set(mots), "libelles": Counter(), "clients": set(), "occurrences": 0, "actions": Counter(), "derniere": None}
                groupes.append(g)
            g["libelles"][p["probleme"].strip()] += 1
            g["clients"].add(i.client.nom)
            g["occurrences"] += 1
            if p.get("action"):
                g["actions"][p["action"].strip()] += 1
            g["derniere"] = max(filter(None, (g["derniere"], i.date_debut)))
    resultat = [{"probleme": g["libelles"].most_common(1)[0][0], "clients": sorted(g["clients"]), "occurrences": g["occurrences"],
                 "action": g["actions"].most_common(1)[0][0] if g["actions"] else None, "derniere": g["derniere"]}
                for g in groupes if len(g["clients"]) >= minimum_clients]
    return sorted(resultat, key=lambda x: (-len(x["clients"]), -x["occurrences"]))
