"""Parc des clients (exports « État de la protection » mois par mois) et usage des licences."""
from datetime import date

from sqlalchemy import select

from .modeles import ANALYSE_OK, Contrat, ExportKsc
from .moteur import parc as mparc
from .moteur.analyse import analyser_mdr
from .moteur.outils import bornes_mois, mois_courant, mois_decale
from .services import hebdos_du_mois

ECHEANCE_PROCHE, ECHEANCE_A_PREVOIR = 30, 90  # jours


def exports_protection(db, client_id, annee, mois, nb_mois=12):
    """[(annee, mois, donnees | None)] des nb_mois jusqu'à (annee, mois) : export de protection retenu de chaque mois
    (dernier dépôt analysé avec succès)."""
    periode = [mois_decale(annee, mois, -k) for k in range(nb_mois - 1, -1, -1)]
    debut = periode[0][0] * 12 + periode[0][1]
    lignes = db.scalars(select(ExportKsc).where(
        ExportKsc.client_id == client_id, ExportKsc.type == "protection", ExportKsc.statut == ANALYSE_OK,
        ExportKsc.annee * 12 + ExportKsc.mois >= debut, ExportKsc.annee * 12 + ExportKsc.mois <= annee * 12 + mois)
        .order_by(ExportKsc.depose_le)).all()
    retenus = {(e.annee, e.mois): e.donnees for e in lignes}  # le plus récent l'emporte
    return [(a, m, retenus.get((a, m))) for a, m in periode]


def dernier_export_protection(db, client_id):
    e = db.scalar(select(ExportKsc).where(ExportKsc.client_id == client_id, ExportKsc.type == "protection",
                                          ExportKsc.statut == ANALYSE_OK)
                  .order_by(ExportKsc.annee.desc(), ExportKsc.mois.desc(), ExportKsc.depose_le.desc()))
    return e


def parc_client(db, client, annee, mois, nb_mois=12):
    mois_exports = exports_protection(db, client.id, annee, mois, nb_mois)
    historique = mparc.historique_appareils(mois_exports)
    dernier = next(((a, m, p) for a, m, p in reversed(mois_exports) if p), None)
    planning = []
    if dernier:
        reference = date.fromisoformat(dernier[2]["genere_le"][:10]) if dernier[2].get("genere_le") else date.today()
        planning = mparc.planning_fin_de_support(dernier[2]["appareils"], max(reference, date.today()))
    return {"historique": historique, "planning": planning, "dernier": dernier}


# --------------------------------------------------------------------------- #
# Contrats et licences
# --------------------------------------------------------------------------- #
def usage_client(db, client, hebdos=None):
    """Usage réel à comparer aux licences : appareils administrés (dernier export KSC)
    et postes supervisés MDR (maximum journalier du mois traité)."""
    usage = {"ksc": None, "ksc_mois": None, "mdr": None, "mdr_mois": None}
    e = dernier_export_protection(db, client.id)
    if e:
        usage["ksc"] = e.donnees.get("nb_appareils") or len(e.donnees.get("appareils", []))
        usage["ksc_mois"] = (e.annee, e.mois)
    if client.avec_mdr:
        annee, mois = mois_courant()
        debut, fin = bornes_mois(annee, mois)
        mdr = analyser_mdr(hebdos if hebdos is not None else hebdos_du_mois(db, annee, mois),
                           set(client.tenants_mdr or []), debut, fin)
        if mdr["max"]:
            usage["mdr"], usage["mdr_mois"] = mdr["max"], (annee, mois)
    return usage


def etat_contrat(contrat, usage, seuil_sous_utilisation, aujourd_hui=None):
    auj = aujourd_hui or date.today()
    utilise = usage.get(contrat.produit.lower()) if contrat.produit in ("KSC", "MDR") else None
    etat = {"utilise": utilise, "taux": None, "statut": "sans-donnee", "libelle": "Pas de donnée d'usage",
            "jours": (contrat.echeance - auj).days if contrat.echeance else None}
    if utilise is not None and contrat.licences:
        etat["taux"] = round(100 * utilise / contrat.licences)
        if utilise > contrat.licences:
            etat.update(statut="depassement", libelle=f"Dépassement : {utilise - contrat.licences} de plus que les licences")
        elif etat["taux"] < seuil_sous_utilisation:
            etat.update(statut="sous-utilise", libelle=f"Sous-utilisé : {contrat.licences - utilise} licence(s) inutilisée(s)")
        else:
            etat.update(statut="ok", libelle="Conforme")
    j = etat["jours"]
    if j is None:
        etat["echeance"] = ("aucune", "Sans échéance")
    elif j < 0:
        etat["echeance"] = ("expire", f"Expiré depuis {-j} jour(s)")
    elif j <= ECHEANCE_PROCHE:
        etat["echeance"] = ("proche", f"Dans {j} jour(s)")
    elif j <= ECHEANCE_A_PREVOIR:
        etat["echeance"] = ("a-prevoir", f"Dans {j} jours")
    else:
        etat["echeance"] = ("ok", f"Dans {j} jours")
    return etat


def contrats_avec_etat(db, clients, seuil_sous_utilisation):
    """[(contrat, etat)] des contrats actifs des clients donnés, échéances les plus proches d'abord."""
    ids = [c.id for c in clients]
    contrats = db.scalars(select(Contrat).where(Contrat.actif.is_(True), Contrat.client_id.in_(ids))).all()
    annee, mois = mois_courant()
    hebdos = hebdos_du_mois(db, annee, mois) if any(c.avec_mdr for c in clients) else []
    usages = {c.id: usage_client(db, c, hebdos) for c in clients if any(k.client_id == c.id for k in contrats)}
    lignes = [(k, etat_contrat(k, usages[k.client_id], seuil_sous_utilisation)) for k in contrats]
    return sorted(lignes, key=lambda l: (l[1]["jours"] if l[1]["jours"] is not None else 10 ** 6, l[0].client.nom))
