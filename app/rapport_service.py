"""Rapport d'activité du service technique (mensuel, trimestriel, semestriel, annuel).

Consolide, pour la période : interventions (validées), assistances mensuelles, techniciens, certifications,
formations, activités internes, problèmes récurrents et reporting de sécurité (rapports mensuels clients).
Les données sont figées dans le rapport à la validation, comme pour les rapports clients.
"""
import os
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import select

from . import service_technique as st
from .config import PRESTATAIRE, STOCKAGE_DIR
from .modeles import (BROUILLON, MODES_INTERVENTION, PERIODICITES_SERVICE, TYPES_ACTIVITE, VALIDE, ActiviteInterne,
                      AssistancePlanifiee, Certification, Formation, Rapport, RapportService, Utilisateur)
from .moteur.analyse import en_json
from .moteur.outils import bornes_mois, fmt_mois
from .rendu.pdf import html_service, pdf_depuis_html

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
NOMS = {"mensuel": "mois", "trimestriel": "trimestre", "semestriel": "semestre", "annuel": "année"}


# --------------------------------------------------------------------------- #
# Périodes
# --------------------------------------------------------------------------- #
def nb_periodes(periodicite):
    return 12 // PERIODICITES_SERVICE[periodicite]


def mois_de_periode(periodicite, annee, numero):
    n = PERIODICITES_SERVICE[periodicite]
    return [(annee, m) for m in range((numero - 1) * n + 1, numero * n + 1)]


def bornes(periodicite, annee, numero):
    mois = mois_de_periode(periodicite, annee, numero)
    return bornes_mois(*mois[0])[0], bornes_mois(*mois[-1])[1]


def libelle(periodicite, annee, numero):
    if periodicite == "mensuel":
        return fmt_mois(annee, numero)
    if periodicite == "annuel":
        return f"Année {annee}"
    rang = "1er" if numero == 1 else f"{numero}e"
    return f"{rang} {NOMS[periodicite]} {annee}"


def libelle_court(periodicite, annee, numero):
    return {"mensuel": f"{MOIS_COURTS[numero - 1]} {annee}", "trimestriel": f"T{numero} {annee}",
            "semestriel": f"S{numero} {annee}", "annuel": str(annee)}[periodicite]


def periode_par_defaut(periodicite, aujourd_hui=None):
    """Période en cours (on rédige souvent en fin de période)."""
    j = aujourd_hui or date.today()
    n = PERIODICITES_SERVICE[periodicite]
    return j.year, (j.month - 1) // n + 1


# --------------------------------------------------------------------------- #
# Consolidation
# --------------------------------------------------------------------------- #
def consolider(db, periodicite, annee, numero):
    debut, fin = bornes(periodicite, annee, numero)
    for a, m in mois_de_periode(periodicite, annee, numero):
        st.rapprocher(db, a, m)
    interventions = st.interventions_periode(db, debut, fin)
    heures = [st.duree_heures(i) for i in interventions]

    # Évolution par mois (graphique)
    par_mois = []
    for a, m in mois_de_periode(periodicite, annee, numero):
        d, f = bornes_mois(a, m)
        du_mois = [i for i in interventions if d <= i.date_debut < f]
        par_mois.append({"libelle": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}", "interventions": len(du_mois),
                         "heures": round(sum(st.duree_heures(i) or 0 for i in du_mois), 1)})

    # Assistances mensuelles
    rang = lambda a, m: a * 12 + m
    assistances = db.scalars(select(AssistancePlanifiee).where(
        AssistancePlanifiee.annee * 12 + AssistancePlanifiee.mois >= rang(debut.year, debut.month),
        AssistancePlanifiee.annee * 12 + AssistancePlanifiee.mois <= rang(*mois_de_periode(periodicite, annee, numero)[-1]))).all()
    etats = Counter(st.etat(a)[0] for a in assistances)
    dues = len(assistances) - etats.get("reportee", 0)

    def resume(i):
        return {"numero": i.numero, "client": i.client.nom, "type": i.libelle_type, "date": i.date_debut.isoformat(),
                "objet": (i.objet or "").replace("**", "")[:300], "statut": i.statut_global, "intervenants": i.intervenants}

    faits = [resume(i) for i in interventions if i.type in ("deploiement", "migration", "audit")]
    incidents = [resume(i) for i in interventions if i.type == "incident"]

    # Techniciens, certifications, formations
    techniciens = [{"nom": l["utilisateur"].nom, "role": l["utilisateur"].libelle_role, "interventions": l["interventions"],
                    "heures": l["heures"], "clients": l["clients"], "certifications": l["certifications"], "formations": l["formations"]}
                   for l in st.classement_techniciens(db, debut, fin)]
    certifs_obtenues = [{"technicien": c.utilisateur.nom, "intitule": c.intitule, "editeur": c.editeur,
                         "obtenue_le": c.obtenue_le.isoformat(), "expire_le": c.expire_le.isoformat() if c.expire_le else None}
                        for c in db.scalars(select(Certification).where(Certification.obtenue_le >= debut, Certification.obtenue_le < fin)
                                            .order_by(Certification.obtenue_le))]
    aujourd_hui = date.today()
    valides = db.scalars(select(Certification).join(Utilisateur).where(
        Utilisateur.actif.is_(True), (Certification.expire_le.is_(None)) | (Certification.expire_le >= aujourd_hui))).all()
    a_renouveler = [{"technicien": c.utilisateur.nom, "intitule": c.intitule, "expire_le": c.expire_le.isoformat()}
                    for c in valides if c.expire_le and c.expire_le <= aujourd_hui + timedelta(days=90)]
    formations = [{"technicien": f.utilisateur.nom, "intitule": f.intitule, "organisme": f.organisme, "statut": f.statut,
                   "heures": f.heures, "debut": f.debut.isoformat() if f.debut else None, "fin": f.fin.isoformat() if f.fin else None}
                  for f in db.scalars(select(Formation).where(
                      (Formation.fin.is_(None)) | (Formation.fin >= debut), (Formation.debut.is_(None)) | (Formation.debut < fin))
                      .order_by(Formation.debut))]
    activites = db.scalars(select(ActiviteInterne).where(ActiviteInterne.date >= debut, ActiviteInterne.date < fin)
                           .order_by(ActiviteInterne.date)).all()

    # Reporting de sécurité : rapports mensuels clients validés dans la période
    rapports = db.scalars(select(Rapport).where(Rapport.periodicite == "mensuel", Rapport.statut == VALIDE,
                                                Rapport.valide_le >= debut, Rapport.valide_le < fin)).all()
    delais = [(r.valide_le.date() - r.fin).days for r in rapports if r.valide_le]

    clients = st.classement_clients(db, debut, fin)
    return {
        "periodicite": periodicite, "annee": annee, "numero": numero, "libelle": libelle(periodicite, annee, numero),
        "libelle_court": libelle_court(periodicite, annee, numero), "nom_periode": NOMS[periodicite],
        "debut": debut.isoformat(), "fin": fin.isoformat(), "fin_incluse": (fin - timedelta(days=1)).isoformat(),
        "chiffres": {
            "interventions": len(interventions), "heures": round(sum(h or 0 for h in heures), 1),
            "sans_heures": sum(1 for h in heures if h is None), "clients": len({i.client_id for i in interventions}),
            "sur_site": sum(1 for i in interventions if i.mode == "site"), "importees": sum(1 for i in interventions if i.source == "import"),
            "points_bloquants": sum(len(i.points_bloquants or []) for i in interventions),
            "assistances_dues": dues, "assistances_realisees": etats.get("realisee", 0), "assistances_reportees": etats.get("reportee", 0),
            "assistances_retard": etats.get("retard", 0),
            "taux_assistance": round(100 * etats.get("realisee", 0) / dues) if dues else None,
            "certifications_obtenues": len(certifs_obtenues), "certifications_valides": len(valides),
            "formations": len(formations), "activites_internes": len(activites),
            "heures_internes": round(sum(a.duree_heures or 0 for a in activites), 1),
            "rapports_securite": len(rapports), "delai_moyen": round(sum(delais) / len(delais), 1) if delais else None,
        },
        "par_type": dict(Counter(i.libelle_type for i in interventions).most_common()),
        "par_mode": {MODES_INTERVENTION.get(k, k): v for k, v in Counter(i.mode for i in interventions).most_common()},
        "statuts": dict(Counter(i.statut_global for i in interventions)),
        "par_mois": par_mois,
        "clients": [{"nom": l["client"].nom, "interventions": l["interventions"], "heures": l["heures"],
                     "types": dict(l["types"]), "dues": l.get("dues"), "faites": l.get("faites"), "conformite": l["conformite"],
                     "points": l["points"], "derniere": l["derniere"].isoformat() if l["derniere"] else None} for l in clients],
        "techniciens": techniciens,
        "faits_marquants": faits, "incidents": incidents,
        "recurrents": [{**p, "derniere": p["derniere"].isoformat() if p["derniere"] else None}
                       for p in st.problemes_recurrents(db, depuis=debut)][:10],
        "certifications_obtenues": certifs_obtenues,
        "certifications_par_editeur": dict(Counter(c.editeur for c in valides).most_common()),
        "certifications_a_renouveler": a_renouveler,
        "formations": formations,
        "activites": [{"date": a.date.isoformat(), "type": TYPES_ACTIVITE.get(a.type, a.type), "titre": a.titre,
                       "description": a.description, "participants": a.participants, "duree": a.duree_heures} for a in activites],
        "activites_par_type": dict(Counter(TYPES_ACTIVITE.get(a.type, a.type) for a in activites).most_common()),
    }


def contenu_par_defaut(d):
    c = d["chiffres"]
    synthese = (f"Au cours du {d['nom_periode'] if d['periodicite'] != 'annuel' else 'exercice'} ({d['libelle'].lower() if d['periodicite'] == 'mensuel' else d['libelle']}), "
                f"le service technique de {PRESTATAIRE['nom']} a réalisé **{c['interventions']} intervention(s)** "
                f"pour **{c['clients']} client(s)**, représentant **{str(c['heures']).replace('.', ',')} heure(s)** de présence")
    synthese += f", dont {c['sur_site']} sur site." if c["interventions"] else "."
    if c["assistances_dues"]:
        synthese += (f" Les assistances mensuelles ont été assurées à **{c['taux_assistance']} %** "
                     f"({c['assistances_realisees']} sur {c['assistances_dues']}).")
    if c["certifications_obtenues"]:
        synthese += f" L'équipe a obtenu **{c['certifications_obtenues']} certification(s)** sur la période."
    faits = [f"{f['type']} chez {f['client']} ({f['date'][8:10]}/{f['date'][5:7]}) : {f['objet'][:140]}" for f in d["faits_marquants"][:6]]
    perspectives = []
    if c["assistances_retard"]:
        perspectives.append(f"Rattraper les {c['assistances_retard']} assistance(s) mensuelle(s) en retard.")
    for p in d["recurrents"][:3]:
        perspectives.append(f"Standardiser le traitement du problème récurrent « {p['probleme']} » ({len(p['clients'])} clients).")
    for x in d["certifications_a_renouveler"][:3]:
        perspectives.append(f"Renouveler la certification « {x['intitule']} » de {x['technicien']} avant le {x['expire_le'][8:10]}/{x['expire_le'][5:7]}/{x['expire_le'][:4]}.")
    return {"synthese": synthese, "faits_marquants": faits,
            "perspectives": perspectives or ["Poursuivre les assistances mensuelles et le suivi des actions correctives."],
            "conclusion": "Le service technique poursuivra son accompagnement des clients au cours de la période suivante."}


# --------------------------------------------------------------------------- #
# Cycle de vie
# --------------------------------------------------------------------------- #
def dernier(db, periodicite, annee, numero, statut=None):
    requete = select(RapportService).where(RapportService.periodicite == periodicite, RapportService.annee == annee,
                                           RapportService.numero == numero)
    if statut:
        requete = requete.where(RapportService.statut == statut)
    return db.scalar(requete.order_by(RapportService.version.desc()))


def creer(db, periodicite, annee, numero, utilisateur, base=None):
    d = consolider(db, periodicite, annee, numero)
    debut, fin = bornes(periodicite, annee, numero)
    precedent = dernier(db, periodicite, annee, numero)
    r = RapportService(periodicite=periodicite, annee=annee, numero=numero, debut=debut, fin=fin,
                       version=(precedent.version + 1) if precedent else 1, statut=BROUILLON, donnees=en_json(d),
                       contenu=dict(base.contenu) if base else contenu_par_defaut(d), cree_par_id=utilisateur.id)
    db.add(r)
    db.flush()
    return r


def actualiser(db, r, reinitialiser_textes=False):
    d = consolider(db, r.periodicite, r.annee, r.numero)
    r.donnees = en_json(d)
    if reinitialiser_textes:
        r.contenu = contenu_par_defaut(d)


def generer_pdf(r, jour=None):
    return pdf_depuis_html(html_service(r.donnees, r.contenu, PRESTATAIRE, jour or date.today()))


def nom_fichier(r):
    return f"Rapport d'activité service technique - {libelle_court(r.periodicite, r.annee, r.numero)} - v{r.version}.pdf"


def valider(db, r, utilisateur):
    maintenant = datetime.now()
    pdf = generer_pdf(r, maintenant.date())
    relatif = "/".join(("service", f"{r.periodicite}-{libelle_court(r.periodicite, r.annee, r.numero).replace(' ', '-')}",
                        f"v{r.version}-{maintenant:%Y%m%d%H%M%S}.pdf"))
    chemin = os.path.join(STOCKAGE_DIR, relatif)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "wb") as f:
        f.write(pdf)
    r.pdf, r.statut, r.valide_par_id, r.valide_le = relatif, VALIDE, utilisateur.id, maintenant
