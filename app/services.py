"""Données d'un client pour un mois : sources disponibles, état, consolidation, cycle de vie des rapports."""
import os
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .config import PRESTATAIRE, STOCKAGE_DIR
from .modeles import ANALYSE_OK, BROUILLON, VALIDE, ExportKsc, Hebdo, Rapport
from .moteur.analyse import analyser_mdr, consolider
from .moteur.lecture_hebdo import depuis_json
from .moteur.outils import bornes_mois, fmt_mois
from .moteur.redaction import contenu_par_defaut
from .rendu.pdf import html_rapport, pdf_depuis_html

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
    return {"tenant_trouve": mdr["tenant_trouve"], "jours": len(mdr["jours"]),
            "total": (fin - debut).days, "manquants": mdr["jours_manquants"], "max": mdr["max"]}


def dernier_rapport(db, client_id, annee, mois, statut=None):
    requete = select(Rapport).where(Rapport.client_id == client_id, Rapport.periodicite == "mensuel",
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


def consolider_client(db, client, annee, mois):
    """Données consolidées (JSON) du client pour le mois, à partir des sources déposées."""
    hebdos = hebdos_du_mois(db, annee, mois) if client.avec_mdr else []
    retenus = exports_retenus(exports_du_mois(db, client.id, annee, mois))
    profil = {"nom": client.nom, "tenants_mdr": client.tenants_mdr, "mdr": client.avec_mdr,
              "suggerer_mdr": client.suggerer_mdr}
    return consolider(profil, annee, mois, hebdos, {t: e.donnees for t, e in retenus.items()},
                      indicateurs_precedents(db, client.id, annee, mois))


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
    html = html_rapport(rapport.donnees, rapport.contenu, PRESTATAIRE, date_rapport or date.today())
    return pdf_depuis_html(html)


def nom_fichier_rapport(rapport, extension="pdf"):
    return (f"Rapport mensuel sécurité - {rapport.client.nom} - {fmt_mois(rapport.annee, rapport.mois)}"
            f" - v{rapport.version}.{extension}")


def valider(db, rapport, utilisateur):
    """Génère le PDF définitif, l'archive et fige le rapport."""
    maintenant = datetime.now()
    pdf = generer_pdf(rapport, maintenant.date())
    relatif = os.path.join("rapports", str(rapport.client_id), f"{rapport.annee}-{rapport.mois:02d}",
                           f"v{rapport.version}-{maintenant:%Y%m%d%H%M%S}.pdf")
    chemin = os.path.join(STOCKAGE_DIR, relatif)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "wb") as f:
        f.write(pdf)
    rapport.pdf, rapport.statut = relatif, VALIDE
    rapport.valide_par_id, rapport.valide_le = utilisateur.id, maintenant
