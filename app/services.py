"""Données d'un client pour un mois : sources disponibles, état, consolidation, cycle de vie des rapports."""
import os
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .config import PRESTATAIRE, STOCKAGE_DIR
from .modeles import ANALYSE_OK, BROUILLON, VALIDE, ExportKsc, Hebdo, Rapport
from .moteur.analyse import analyser_mdr, consolider, en_json
from .moteur.lecture_hebdo import depuis_json
from .moteur.outils import bornes_mois, fmt_mois
from .moteur.redaction import contenu_par_defaut
from .moteur import bilan as mbilan
from .rendu.pdf import INDICATEURS_EVOLUTION, MOIS_COURTS, html_bilan, html_rapport, pdf_depuis_html

TYPES = ("protection", "menaces", "vulnerabilites")


def hebdos_du_mois(db, annee, mois):
    """Hebdos analysés utiles au mois : chacun contient l'historique des 30 jours précédents,
    donc ceux déposés jusqu'à 5 semaines après la fin du mois peuvent couvrir ses derniers jours."""
    debut, fin = bornes_mois(annee, mois)
    lignes = db.scalars(select(Hebdo).where(Hebdo.statut == ANALYSE_OK,
                                            Hebdo.debut >= debut - timedelta(days=7),
                                            Hebdo.debut < fin + timedelta(days=35))
                        .order_by(Hebdo.debut, Hebdo.depose_le)).all()
    return [depuis_json(h.donnees) for h in lignes]


def exports_du_mois(db, client_id, annee, mois):
    """Tous les exports déposés pour le client et le mois (plus récents d'abord)."""
    return db.scalars(select(ExportKsc).where(ExportKsc.client_id == client_id, ExportKsc.annee == annee,
                                              ExportKsc.mois == mois)
                      .order_by(ExportKsc.depose_le.desc())).all()


def exports_retenus(exports):
    """Export en vigueur par type : le dernier analysé avec succès."""
    retenus = {}
    for e in exports:
        if e.statut == ANALYSE_OK and e.type and not e.remplace and e.type not in retenus:
            retenus[e.type] = e
    return retenus


def couverture_mdr(client, annee, mois, hebdos):
    if not client.avec_mdr:
        return None
    debut, fin = bornes_mois(annee, mois)
    mdr = analyser_mdr(hebdos, set(client.tenants_mdr), debut, fin)
    a_venir = mdr["jours_a_venir"]
    return {"tenant_trouve": mdr["tenant_trouve"], "jours": len(mdr["jours"]), "total": (fin - debut).days,
            "manquants": [j for j in mdr["jours_manquants"] if j not in a_venir],  # en retard : hebdo à déposer
            "a_venir": a_venir, "max": mdr["max"]}


def dernier_rapport(db, client_id, annee, mois, statut=None, periodicite="mensuel"):
    """Dernière version d'un rapport (pour un bilan : mois = premier mois de la période)."""
    requete = select(Rapport).where(Rapport.client_id == client_id, Rapport.periodicite == periodicite,
                                    Rapport.annee == annee, Rapport.mois == mois)
    if statut:
        requete = requete.where(Rapport.statut == statut)
    return db.scalar(requete.order_by(Rapport.version.desc()))


def etat_client(db, client, annee, mois, hebdos):
    """Synthèse pour le tableau de bord."""
    exports = exports_du_mois(db, client.id, annee, mois)
    retenus = exports_retenus(exports)
    en_cours = {e.type or "?" for e in exports if e.statut in ("en_attente", "en_cours")}
    erreurs = [e for e in exports if e.statut == "erreur"]
    ksc = {}
    for t in TYPES:
        if t in retenus:
            ksc[t] = "ok"
        elif en_cours:
            ksc[t] = "cours"
        else:
            ksc[t] = "attente"
    mdr = couverture_mdr(client, annee, mois, hebdos)
    rapport = dernier_rapport(db, client.id, annee, mois)
    manque_ksc = client.avec_ksc and len(retenus) < 3
    manque_mdr = mdr is not None and (not mdr["tenant_trouve"] or mdr["manquants"])
    if rapport:
        etat = "Validé" if rapport.statut == VALIDE else "Brouillon"
    elif not retenus and (mdr is None or not mdr["jours"]):
        etat = "Incomplet"
    else:
        etat = "Prêt" if not (manque_ksc or manque_mdr) else "Partiel"
    return {"client": client, "ksc": ksc, "en_cours": bool(en_cours), "erreurs": erreurs,
            "mdr": mdr, "rapport": rapport, "etat": etat, "nb_exports": len(retenus)}


def rapport_precedent(db, client_id, annee, mois):
    """Dernier rapport validé du mois précédent."""
    pa, pm = (annee - 1, 12) if mois == 1 else (annee, mois - 1)
    return dernier_rapport(db, client_id, pa, pm, VALIDE)


def indicateurs_precedents(db, client_id, annee, mois):
    precedent = rapport_precedent(db, client_id, annee, mois)
    return precedent.indicateurs if precedent else None


def actions_a_suivre(db, client_id, annee, mois):
    """Actions du mois précédent encore ouvertes, à reprendre dans le suivi du nouveau rapport."""
    precedent = rapport_precedent(db, client_id, annee, mois)
    if not precedent:
        return []
    anciennes = precedent.contenu.get("actions", []) + precedent.contenu.get("suivi", [])
    return [{"action": a["action"], "priorite": a["priorite"], "responsable": a.get("responsable", ""),
             "statut": a.get("statut", "À faire"), "commentaire": ""}
            for a in anciennes if a.get("statut", "À faire") in ("À faire", "En cours")]


INDICATEURS_SUIVIS = INDICATEURS_EVOLUTION  # (clé, libellé) des courbes d'évolution


def _rang(annee, mois):
    return annee * 12 + mois - 1


def point_historique(rapport):
    """Un mois de l'historique : indicateurs et niveau de risque d'un rapport mensuel."""
    return {"annee": rapport.annee, "mois": rapport.mois,
            "libelle": f"{MOIS_COURTS[rapport.mois - 1]} {str(rapport.annee)[2:]}",
            "niveau": rapport.contenu.get("niveau_risque"), "indicateurs": rapport.indicateurs or {},
            "rapport_id": rapport.id, "version": rapport.version}


def historique(db, client_id, annee, mois, nb_mois=12, inclure_courant=True):
    """Derniers rapports mensuels validés du client (dernière version de chaque mois), du plus ancien au plus récent."""
    fin = _rang(annee, mois) + (1 if inclure_courant else 0)
    debut = fin - nb_mois
    valides = db.scalars(select(Rapport).where(
        Rapport.client_id == client_id, Rapport.periodicite == "mensuel", Rapport.statut == VALIDE,
        Rapport.annee * 12 + Rapport.mois - 1 >= debut, Rapport.annee * 12 + Rapport.mois - 1 < fin)
        .order_by(Rapport.annee, Rapport.mois, Rapport.version)).all()
    par_mois = {(r.annee, r.mois): r for r in valides}  # la dernière version l'emporte
    return [point_historique(r) for _, r in sorted(par_mois.items())]


def consolider_client(db, client, annee, mois):
    """Données consolidées (JSON) du client pour le mois, à partir des sources déposées."""
    hebdos = hebdos_du_mois(db, annee, mois) if client.avec_mdr else []
    retenus = exports_retenus(exports_du_mois(db, client.id, annee, mois))
    profil = {"nom": client.nom, "tenants_mdr": client.tenants_mdr, "mdr": client.avec_mdr,
              "suggerer_mdr": client.suggerer_mdr}
    d = consolider(profil, annee, mois, hebdos, {t: e.donnees for t, e in retenus.items()},
                   indicateurs_precedents(db, client.id, annee, mois))
    # Mois précédents validés (11 au plus) : courbes d'évolution du rapport, figées à la validation
    d["historique"] = historique(db, client.id, annee, mois, nb_mois=11, inclure_courant=False)
    return d


# --------------------------------------------------------------------------- #
# Cycle de vie des rapports
# --------------------------------------------------------------------------- #
def _profil(client):
    return {"mdr": client.avec_mdr, "ksc": client.avec_ksc, "suggerer_mdr": client.suggerer_mdr,
            "tenants_mdr": list(client.tenants_mdr or [])}


def creer_brouillon(db, client, annee, mois, utilisateur, base=None):
    """Nouvelle version en brouillon. base : rapport dont on reprend les textes (nouvelle version d'un validé)."""
    d = consolider_client(db, client, annee, mois)
    precedent = dernier_rapport(db, client.id, annee, mois)
    contenu = (dict(base.contenu) if base else
               contenu_par_defaut(d, PRESTATAIRE["nom"], actions_a_suivre(db, client.id, annee, mois)))
    if not base:  # points bloquants des interventions du mois, cochés « reprendre dans le plan d'action »
        from .interventions import actions_pour_plan
        contenu["actions"] = contenu["actions"] + actions_pour_plan(db, client.id, annee, mois)
    debut, fin = bornes_mois(annee, mois)
    rapport = Rapport(client_id=client.id, periodicite="mensuel", annee=annee, mois=mois, debut=debut, fin=fin,
                      version=(precedent.version + 1) if precedent else 1, statut=BROUILLON,
                      profil=_profil(client), donnees=d, contenu=contenu, indicateurs=d["indicateurs"],
                      cree_par_id=utilisateur.id)
    db.add(rapport)
    db.flush()
    return rapport


def actualiser_brouillon(db, rapport, reinitialiser_textes=False):
    """Recalcule les chiffres à partir des fichiers déposés ; les textes sont conservés sauf demande contraire."""
    client = rapport.client
    d = consolider_client(db, client, rapport.annee, rapport.mois)
    rapport.donnees, rapport.indicateurs, rapport.profil = d, d["indicateurs"], _profil(client)
    if reinitialiser_textes:
        suivi = rapport.contenu.get("suivi") or actions_a_suivre(db, client.id, rapport.annee, rapport.mois)
        rapport.contenu = contenu_par_defaut(d, PRESTATAIRE["nom"], suivi)


def generer_pdf(rapport, date_rapport=None):
    rendu = html_rapport if rapport.periodicite == "mensuel" else html_bilan
    return pdf_depuis_html(rendu(rapport.donnees, rapport.contenu, PRESTATAIRE, date_rapport or date.today()))


def libelle_rapport(rapport):
    """« Septembre 2026 » pour un mensuel, « T3 2026 » / « S2 2026 » pour un bilan."""
    if rapport.periodicite == "mensuel":
        return fmt_mois(rapport.annee, rapport.mois)
    return mbilan.libelle_court(rapport.periodicite, rapport.annee, mbilan.numero_periode(rapport.periodicite, rapport.mois))


def nom_fichier_rapport(rapport, extension="pdf"):
    genre = "Rapport mensuel" if rapport.periodicite == "mensuel" else f"Bilan {rapport.periodicite}"
    return f"{genre} sécurité - {rapport.client.nom} - {libelle_rapport(rapport)} - v{rapport.version}.{extension}"


# --------------------------------------------------------------------------- #
# Bilans trimestriels et semestriels (à partir des mensuels validés)
# --------------------------------------------------------------------------- #
def mensuels_de_periode(db, client_id, periodicite, annee, numero):
    """Dernière version validée de chaque mois de la période, au format attendu par consolider_bilan."""
    mois = mbilan.mois_de_periode(periodicite, annee, numero)
    valides = db.scalars(select(Rapport).where(
        Rapport.client_id == client_id, Rapport.periodicite == "mensuel", Rapport.statut == VALIDE,
        Rapport.annee == annee, Rapport.mois >= mois[0][1], Rapport.mois <= mois[-1][1])
        .order_by(Rapport.mois, Rapport.version)).all()
    par_mois = {(r.annee, r.mois): r for r in valides}
    return [{"id": r.id, "annee": r.annee, "mois": r.mois, "version": r.version,
             "valide_le": r.valide_le.isoformat() if r.valide_le else None,
             "contenu": r.contenu, "donnees": r.donnees, "indicateurs": r.indicateurs or {}}
            for r in par_mois.values()]


def consolider_bilan_client(db, client, periodicite, annee, numero):
    d = mbilan.consolider_bilan({"nom": client.nom, "mdr": client.avec_mdr}, periodicite, annee, numero,
                                mensuels_de_periode(db, client.id, periodicite, annee, numero))
    return en_json(d)


def creer_bilan(db, client, periodicite, annee, numero, utilisateur, base=None):
    d = consolider_bilan_client(db, client, periodicite, annee, numero)
    debut, fin = mbilan.bornes_periode(periodicite, annee, numero)
    precedent = dernier_rapport(db, client.id, annee, debut.month, periodicite=periodicite)
    contenu = dict(base.contenu) if base else mbilan.contenu_bilan_defaut(d, PRESTATAIRE["nom"])
    rapport = Rapport(client_id=client.id, periodicite=periodicite, annee=annee, mois=debut.month, debut=debut, fin=fin,
                      version=(precedent.version + 1) if precedent else 1, statut=BROUILLON, profil=_profil(client),
                      donnees=d, contenu=contenu, indicateurs=mbilan.indicateurs_bilan(d), cree_par_id=utilisateur.id)
    db.add(rapport)
    db.flush()
    return rapport


def actualiser_bilan(db, rapport, reinitialiser_textes=False):
    numero = mbilan.numero_periode(rapport.periodicite, rapport.mois)
    d = consolider_bilan_client(db, rapport.client, rapport.periodicite, rapport.annee, numero)
    rapport.donnees, rapport.indicateurs, rapport.profil = d, mbilan.indicateurs_bilan(d), _profil(rapport.client)
    if reinitialiser_textes:
        rapport.contenu = mbilan.contenu_bilan_defaut(d, PRESTATAIRE["nom"])


def valider(db, rapport, utilisateur):
    """Génère le PDF définitif, l'archive et fige le rapport."""
    maintenant = datetime.now()
    pdf = generer_pdf(rapport, maintenant.date())
    if rapport.periodicite == "mensuel":
        periode = f"{rapport.annee}-{rapport.mois:02d}"
    else:
        periode = f"{rapport.periodicite}-{libelle_rapport(rapport).replace(' ', '-')}"
    # Chemin relatif toujours avec « / » : la base reste valable sous Linux comme sous Windows
    relatif = "/".join(("rapports", str(rapport.client_id), periode, f"v{rapport.version}-{maintenant:%Y%m%d%H%M%S}.pdf"))
    chemin = os.path.join(STOCKAGE_DIR, relatif)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "wb") as f:
        f.write(pdf)
    rapport.pdf, rapport.statut = relatif, VALIDE
    rapport.valide_par_id, rapport.valide_le = utilisateur.id, maintenant
