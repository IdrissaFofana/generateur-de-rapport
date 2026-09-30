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
def _analyser(db, texte):
    from .moteur.import_intervention import analyser
    from .modeles import Client, Utilisateur
    clients = [(c.id, c.nom, c.code_rapport, c.tenants_mdr, c.autres_noms or []) for c in db.scalars(select(Client))]
    return analyser(texte, clients, db.scalars(select(Utilisateur.nom)).all())


# Doublon probable : même client et contenu très proche. Fenêtre de dates : deux assistances mensuelles se ressemblent
# d'un mois sur l'autre sans être des doublons ; hors fenêtre, seul un texte quasi identique (réexport) est signalé.
FENETRE_DOUBLON_JOURS = 7
SEUIL_DOUBLON = 0.6        # dates proches (ou inconnues d'un côté)
SEUIL_DOUBLON_TEXTE = 0.85  # dates éloignées : texte quasi identique


def similarite(objet_a, resultat_a, texte_a, objet_b, resultat_b, texte_b):
    """Similarité de Jaccard (0 à 1) sur les mots significatifs : du contenu structuré (objet + actions) et, quand les
    deux textes intégraux existent (deux imports), du texte complet. On retient la plus forte."""
    from .service_technique import jaccard, mots_significatifs
    structure = jaccard(mots_significatifs(" ".join([objet_a or "", *(resultat_a or [])])),
                        mots_significatifs(" ".join([objet_b or "", *(resultat_b or [])])))
    texte = jaccard(mots_significatifs(texte_a), mots_significatifs(texte_b)) if texte_a and texte_b else 0.0
    return max(structure, texte)


def chercher_doublon(db, client_id, champs, texte):
    """Intervention existante du même client qui ressemble au document importé : (intervention, score) ou (None, 0)."""
    meilleur, score_max = None, 0.0
    for i in db.scalars(select(Intervention).where(Intervention.client_id == client_id)):
        score = similarite(champs["objet"], champs["resultat"], texte, i.objet, i.resultat, i.texte_source)
        proche = champs["date_debut"] is None or abs((i.date_debut - champs["date_debut"]).days) <= FENETRE_DOUBLON_JOURS
        if score >= (SEUIL_DOUBLON if proche else SEUIL_DOUBLON_TEXTE) and score > score_max:
            meilleur, score_max = i, score
    return meilleur, round(score_max, 2)


def importer(db, contenu, extension, nom_fichier_origine, utilisateur, client_force=None):
    """Importe un ancien rapport. Renvoie (intervention, champs manquants), ou (None, import en attente) quand le
    client n'est pas reconnu ou que le document ressemble à une intervention existante (doublon probable) : la
    décision revient alors à l'utilisateur. Lève ValueError pour un fichier identique déjà importé."""
    from .modeles import Client, ImportEnAttente
    from .moteur.import_intervention import extraire_texte
    from .stockage import empreinte, enregistrer
    h = empreinte(contenu)
    doublon = db.scalar(select(Intervention).where(Intervention.fichier_source.like(f"%{h}%")))
    if doublon is not None:
        raise ValueError(f"déjà importé ({doublon.numero})")
    if db.scalar(select(ImportEnAttente.id).where(ImportEnAttente.empreinte == h)):
        raise ValueError("déjà en attente (voir la liste ci-dessous)")
    texte = extraire_texte(contenu, extension)
    champs = _analyser(db, texte)
    client = db.get(Client, client_force or champs["client_id"]) if (client_force or champs["client_id"]) else None
    semblable, score = chercher_doublon(db, client.id, champs, texte) if client else (None, 0)
    if client is None or semblable is not None:
        chemin, _ = enregistrer(contenu, "imports", "attente", extension=extension)
        attente = ImportEnAttente(fichier=chemin, nom_fichier=nom_fichier_origine[:300], extension=extension, empreinte=h,
                                  texte=texte, nom_detecte=champs.get("client_nom"), cree_par_id=utilisateur.id,
                                  motif="doublon" if semblable else "client", client_id=client.id if client else None,
                                  doublon_id=semblable.id if semblable else None, similarite=score or None)
        db.add(attente)
        db.flush()
        return None, attente
    return _creer_import(db, contenu, extension, nom_fichier_origine, utilisateur, texte, champs, client)


def resoudre_attente(db, attente, client, utilisateur, forcer=False):
    """Rattache un import en attente à un client et crée l'intervention à vérifier. Sans « forcer », un doublon
    probable chez ce client laisse le document en attente (motif « doublon ») : renvoie alors (None, attente)."""
    from .stockage import absolu, supprimer
    champs = _analyser(db, attente.texte)
    if not forcer:
        semblable, score = chercher_doublon(db, client.id, champs, attente.texte)
        if semblable is not None:
            attente.motif, attente.client_id, attente.doublon_id, attente.similarite = "doublon", client.id, semblable.id, score
            db.flush()
            return None, attente
    with open(absolu(attente.fichier), "rb") as f:
        contenu = f.read()
    intervention, manquants = _creer_import(db, contenu, attente.extension, attente.nom_fichier, utilisateur,
                                            attente.texte, champs, client)
    fichier = attente.fichier
    db.delete(attente)
    db.flush()
    supprimer(fichier)
    return intervention, manquants


def reessayer_attentes(db, utilisateur):
    """Relance la reconnaissance des imports en attente de client (après création d'un client ou ajout d'un autre
    nom). Renvoie (interventions créées, imports devenus « doublon probable »)."""
    from .modeles import Client, ImportEnAttente
    crees, doublons = [], []
    for a in db.scalars(select(ImportEnAttente).where(ImportEnAttente.motif == "client").order_by(ImportEnAttente.id)).all():
        cid = _analyser(db, a.texte)["client_id"]
        if cid:
            i, _ = resoudre_attente(db, a, db.get(Client, cid), utilisateur)
            (crees if i else doublons).append(i or a)
    return crees, doublons


def _creer_import(db, contenu, extension, nom_fichier_origine, utilisateur, texte, champs, client):
    from .stockage import enregistrer
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
