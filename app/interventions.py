"""Rapports d'intervention : numérotation, contexte proposé, validation (PDF), envoi au client, plan d'action."""
import os
from collections import Counter
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from sqlalchemy import func, select

from . import alertes, config, parc
from .config import PRESTATAIRE, STOCKAGE_DIR
from .modeles import BROUILLON, VALIDE, Intervention
from .moteur import parc as mparc
from .moteur.outils import bornes_mois
from .rendu.pdf import html_intervention, pdf_depuis_html


def prochain_numero(db, client, annee):
    """RI-2026-HUD-004 : compteur par client, remis à 1 chaque année."""
    sequence = (db.scalar(select(func.max(Intervention.sequence)).where(
        Intervention.client_id == client.id, Intervention.annee == annee)) or 0) + 1
    return sequence, f"RI-{annee}-{client.code_rapport}-{sequence:03d}"


def contexte_propose(db, client):
    """Contexte chiffré pré-rempli à partir du dernier export « État de la protection » du client."""
    e = parc.dernier_export_protection(db, client.id)
    if e is None:
        return {"postes": "", "serveurs": "", "systemes": "", "version_ksc": "", "autres": ""}
    appareils = e.donnees.get("appareils", [])
    serveurs = sum(1 for a in appareils if a.get("serveur"))
    total = e.donnees.get("nb_appareils") or len(appareils)
    systemes = Counter(mparc.systeme_court(a["os"]) for a in appareils)
    return {"postes": str(max(total - serveurs, 0)), "serveurs": str(serveurs),
            "systemes": ", ".join(f"{nom} ({n})" for nom, n in systemes.most_common()),
            "version_ksc": "", "autres": f"D'après l'export KSC de {e.mois:02d}/{e.annee}."}


def creer(db, client, type_, utilisateur, jour=None, base=None):
    """Nouvelle intervention en brouillon (vide, ou reprise d'une intervention précédente)."""
    jour = jour or date.today()
    sequence, numero = prochain_numero(db, client, jour.year)
    intervention = Intervention(
        numero=numero, client_id=client.id, annee=jour.year, sequence=sequence, type=type_,
        date_debut=jour, date_fin=jour, statut=BROUILLON, cree_par_id=utilisateur.id,
        intervenants=[utilisateur.nom], contexte=contexte_propose(db, client), envoye_a="")
    if base is not None:  # suite d'une intervention : on reprend le fond, pas les dates ni le résultat
        intervention.type, intervention.mode = base.type, base.mode
        intervention.interlocuteur, intervention.intervenants = base.interlocuteur, list(base.intervenants)
        intervention.heure_debut, intervention.heure_fin = base.heure_debut, base.heure_fin
        intervention.objet, intervention.contexte = base.objet, dict(base.contexte)
        intervention.travaux = [dict(t) for t in base.travaux]
        intervention.points_bloquants = [dict(p) for p in base.points_bloquants]
        intervention.recommandations = list(base.recommandations)
    db.add(intervention)
    db.flush()
    return intervention


def generer_pdf(intervention):
    return pdf_depuis_html(html_intervention(intervention, PRESTATAIRE))


def nom_fichier(intervention):
    return f"{intervention.numero} - {intervention.titre} - {intervention.client.nom}.pdf"


def valider(db, intervention, utilisateur):
    """PDF définitif archivé ; le rapport n'est plus modifiable (il peut être rouvert par un validateur)."""
    maintenant = datetime.now()
    intervention.valide_par_id, intervention.valide_le = utilisateur.id, maintenant
    db.flush()
    pdf = generer_pdf(intervention)
    relatif = "/".join(("interventions", str(intervention.client_id), f"{intervention.numero}-{maintenant:%Y%m%d%H%M%S}.pdf"))
    chemin = os.path.join(STOCKAGE_DIR, relatif)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "wb") as f:
        f.write(pdf)
    intervention.pdf, intervention.statut = relatif, VALIDE


def lire_pdf(intervention):
    from .stockage import absolu
    with open(absolu(intervention.pdf), "rb") as f:
        return f.read()


# --------------------------------------------------------------------------- #
# Envoi au client
# --------------------------------------------------------------------------- #
def _texte_envoi(intervention):
    periode = (f"le {intervention.date_debut:%d/%m/%Y}" if intervention.date_debut == intervention.date_fin
               else f"du {intervention.date_debut:%d/%m/%Y} au {intervention.date_fin:%d/%m/%Y}")
    return (f"Bonjour,\n\nVeuillez trouver ci-joint le {intervention.titre.lower()} n° {intervention.numero} "
            f"concernant notre intervention {periode}.\n\nStatut global : {intervention.statut_global}.\n\n"
            f"Nous restons à votre disposition pour toute question.\n\nCordialement,\n"
            f"{PRESTATAIRE['signataire']}\n{PRESTATAIRE['nom_complet']}\n")


def sujet_envoi(intervention):
    return f"{intervention.titre} {intervention.numero} — {intervention.client.nom}"


def brouillon_eml(intervention):
    """Message prêt à envoyer (s'ouvre comme brouillon dans Outlook), PDF joint."""
    m = EmailMessage()
    m["Subject"] = sujet_envoi(intervention)
    m["To"] = ", ".join(intervention.client.emails_rapports or [])
    if config.SMTP["expediteur"]:
        m["From"] = config.SMTP["expediteur"]
    m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid()
    m["X-Unsent"] = "1"  # Outlook : ouvrir en mode rédaction
    m.set_content(_texte_envoi(intervention))
    m.add_attachment(lire_pdf(intervention), maintype="application", subtype="pdf", filename=nom_fichier(intervention))
    return m.as_bytes()


def envoyer(intervention, destinataires):
    """Envoi par le serveur de messagerie interne ; lève une exception en cas d'échec."""
    if not alertes.email_configure():
        raise RuntimeError("Serveur de messagerie non configuré (SMTP_HOTE, SMTP_EXPEDITEUR) : utilisez le brouillon Outlook.")
    if not destinataires:
        raise RuntimeError("Aucun destinataire : renseignez les adresses du client dans sa fiche.")
    alertes.envoyer_email(destinataires, sujet_envoi(intervention), _texte_envoi(intervention), None,
                          pieces_jointes=[(nom_fichier(intervention), lire_pdf(intervention))])
    intervention.envoye_le, intervention.envoye_a = datetime.now(), ", ".join(destinataires)


# --------------------------------------------------------------------------- #
# Points bloquants repris dans le plan d'action du rapport mensuel
# --------------------------------------------------------------------------- #
def actions_pour_plan(db, client_id, annee, mois):
    """Points bloquants cochés « reprendre dans le plan d'action » des interventions validées du mois."""
    debut, fin = bornes_mois(annee, mois)
    interventions = db.scalars(select(Intervention).where(
        Intervention.client_id == client_id, Intervention.statut == VALIDE,
        Intervention.date_debut >= debut, Intervention.date_debut < fin).order_by(Intervention.date_debut)).all()
    actions = []
    for i in interventions:
        for p in i.points_bloquants:
            if p.get("plan_action"):
                texte = p.get("action") or f"Traiter : {p.get('probleme', '')}"
                actions.append({"action": texte, "pourquoi": f"Point bloquant de l'intervention {i.numero} : {p.get('probleme', '')}"
                                + (f" — {p['impact']}" if p.get("impact") else ""),
                                "priorite": "Haute", "responsable": p.get("responsable") or PRESTATAIRE["nom"], "statut": "À faire"})
    return actions


# --------------------------------------------------------------------------- #
# Import d'anciens rapports (PDF / Word) : fichier conservé, champs extraits, vérification humaine
# --------------------------------------------------------------------------- #
def importer(db, contenu, extension, nom_fichier_origine, utilisateur, client_defaut=None):
    """Crée une intervention « à vérifier » à partir d'un ancien rapport. Lève ValueError si le client est introuvable."""
    from .moteur.import_intervention import analyser, extraire_texte
    from .modeles import Client, Utilisateur
    from .stockage import empreinte, enregistrer
    h = empreinte(contenu)
    doublon = db.scalar(select(Intervention).where(Intervention.fichier_source.like(f"%{h}%")))
    if doublon is not None:
        raise ValueError(f"déjà importé ({doublon.numero})")
    texte = extraire_texte(contenu, extension)
    clients = [(c.id, c.nom, c.code_rapport, c.tenants_mdr) for c in db.scalars(select(Client))]
    noms = db.scalars(select(Utilisateur.nom)).all()
    champs = analyser(texte, clients, noms)
    client = db.get(Client, champs["client_id"] or client_defaut) if (champs["client_id"] or client_defaut) else None
    if client is None:
        raise ValueError("client non reconnu dans le document : choisissez un client par défaut")
    jour = champs["date_debut"] or date.today()
    intervention = creer(db, client, champs["type"] or "assistance", utilisateur, jour)
    chemin, _ = enregistrer(contenu, "interventions", "import", str(client.id), extension=extension)
    intervention.source, intervention.a_verifier = "import", True
    intervention.fichier_source, intervention.nom_fichier_source = chemin, nom_fichier_origine[:300]
    intervention.texte_source = texte
    intervention.date_fin = champs["date_fin"] or jour
    intervention.heure_debut, intervention.heure_fin = champs["heure_debut"], champs["heure_fin"]
    intervention.intervenants = champs["intervenants"] or []
    intervention.objet = champs["objet"]
    intervention.contexte = {**intervention.contexte, "autres": champs["contexte"][:500]} if champs["contexte"] else {
        "postes": "", "serveurs": "", "systemes": "", "version_ksc": "", "autres": ""}
    intervention.resultat = champs["resultat"]
    intervention.statut_global = champs["statut_global"] or "OK"
    intervention.points_bloquants = champs["points_bloquants"]
    intervention.recommandations = champs["recommandations"]
    return intervention, champs["manquants"]


def confirmer_import(db, intervention, utilisateur):
    """Import vérifié : le rapport est archivé tel quel (le fichier d'origine reste la référence)."""
    intervention.statut, intervention.a_verifier = VALIDE, False
    intervention.valide_par_id, intervention.valide_le = utilisateur.id, datetime.now()
    if (intervention.fichier_source or "").endswith(".pdf"):
        intervention.pdf = intervention.fichier_source
