"""Alertes : détection, notification (e-mail, Teams) et résumé hebdomadaire.

Règles (évaluées après chaque validation, analyse de fichier, modification de contrat, et chaque jour) :
  - un client passe au niveau de risque critique (rapport mensuel validé) ;
  - hausse des détections de menaces d'au moins SEUIL_HAUSSE_DETECTIONS % d'un mois validé au suivant ;
  - incident MDR signalé dans un rapport hebdomadaire ;
  - serveur en état critique deux mois de suite (exports « État de la protection ») ;
  - licences dépassées, contrat arrivant à échéance ou expiré.
Chaque alerte a une clé unique : une même situation n'est signalée (et notifiée) qu'une fois.
Sans configuration SMTP ni Teams, les alertes restent visibles dans la plateforme.
"""
import json
import logging
import smtplib
import threading
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import escape

from sqlalchemy import func, select

from . import config, parc, services
from .modeles import ANALYSE_OK, Alerte, Client, Envoi, Hebdo
from .moteur import parc as mparc
from .moteur.outils import fmt_mois, mois_courant

journal = logging.getLogger("rapports.alertes")
MOIS_SURVEILLES = 3  # seules les situations récentes déclenchent une alerte (pas tout l'historique)
TYPES = {
    "risque_critique": "Niveau critique", "hausse_detections": "Hausse des détections", "incident_mdr": "Incident MDR",
    "serveur_critique": "Serveur critique 2 mois", "licences": "Licences", "echeance": "Échéance de contrat",
    "assistance": "Assistance mensuelle", "certification": "Certification",
}
JOUR_RAPPEL_ASSISTANCE = 20  # à partir de ce jour du mois, une assistance non planifiée est signalée


# --------------------------------------------------------------------------- #
# Règles
# --------------------------------------------------------------------------- #
def _candidat(cle, client, type_, niveau, titre, detail="", lien=""):
    return {"cle": cle, "client_id": client.id if client else None, "type": type_, "niveau": niveau,
            "titre": titre, "detail": detail, "lien": lien}


def _regles_rapports(db, client, reference):
    """Niveau critique et hausse des détections, d'après les rapports mensuels validés."""
    annee, mois = reference
    points = services.historique(db, client.id, annee, mois, nb_mois=MOIS_SURVEILLES + 1)
    rang = lambda p: p["annee"] * 12 + p["mois"]
    candidats = []
    for i, p in enumerate(points):
        if rang(p) <= annee * 12 + mois - MOIS_SURVEILLES:
            continue  # le mois le plus ancien ne sert que de comparaison
        prec = points[i - 1] if i and rang(points[i - 1]) == rang(p) - 1 else None
        libelle = fmt_mois(p["annee"], p["mois"])
        lien = f"/rapports/{p['rapport_id']}"
        if p["niveau"] == "Critique" and (prec is None or prec["niveau"] != "Critique"):
            candidats.append(_candidat(f"risque-critique:{client.id}:{p['annee']}-{p['mois']:02d}", client, "risque_critique",
                                       "critique", f"{client.nom} passe au niveau de risque critique ({libelle})",
                                       f"Niveau précédent : {prec['niveau'] if prec else 'aucun rapport validé'}.", lien))
        avant = (prec or {}).get("indicateurs", {}).get("detections")
        apres = p["indicateurs"].get("detections")
        if avant and apres is not None and apres - avant >= 10 \
                and apres >= avant * (1 + config.SEUIL_HAUSSE_DETECTIONS / 100):
            candidats.append(_candidat(f"hausse-detections:{client.id}:{p['annee']}-{p['mois']:02d}", client,
                                       "hausse_detections", "avertissement",
                                       f"{client.nom} : détections de menaces +{round(100 * (apres - avant) / avant)} % ({libelle})",
                                       f"{avant} détections le mois précédent, {apres} en {libelle.lower()}.", lien))
    return candidats


def _regles_serveurs(db, client, reference):
    annee, mois = reference
    mois_exports = parc.exports_protection(db, client.id, annee, mois, nb_mois=MOIS_SURVEILLES + 1)
    candidats = []
    for (a1, m1, p1), (a2, m2, p2) in zip(mois_exports, mois_exports[1:]):
        serveurs = mparc.serveurs_critiques_consecutifs(p1, p2)
        if serveurs:
            candidats.append(_candidat(
                f"serveurs-critiques:{client.id}:{a2}-{m2:02d}", client, "serveur_critique", "critique",
                f"{client.nom} : {len(serveurs)} serveur(s) en état critique deux mois de suite",
                f"{', '.join(serveurs)} — critiques en {fmt_mois(a1, m1).lower()} et en {fmt_mois(a2, m2).lower()}.",
                f"/clients/{client.id}/parc?annee={a2}&mois={m2}"))
    return candidats


def _regles_incidents(db, clients):
    """Incidents MDR des hebdos récents, rattachés aux clients par leurs tenants."""
    par_tenant = {t: c for c in clients if c.avec_mdr for t in (c.tenants_mdr or [])}
    depuis = date.today() - timedelta(days=31 * MOIS_SURVEILLES)
    candidats = []
    for donnees in db.scalars(select(Hebdo.donnees).where(Hebdo.statut == ANALYSE_OK, Hebdo.debut >= depuis)):
        for inc in (donnees or {}).get("incidents", []):
            client = par_tenant.get(inc.get("tenant"))
            if client is None:
                continue
            grave = str(inc.get("priorite", "")).lower() in ("critique", "critical", "haute", "high", "élevée")
            candidats.append(_candidat(
                f"incident-mdr:{client.id}:{inc['numero']}", client, "incident_mdr", "critique" if grave else "avertissement",
                f"{client.nom} : incident MDR n° {inc['numero']} — {inc.get('nom', '')}".strip(" —"),
                f"Priorité : {inc.get('priorite', '—')} · Statut : {inc.get('statut', '—')} · Créé le {inc.get('cree', '—')}.",
                f"/clients/{client.id}/{donnees['debut'][:4]}/{int(donnees['debut'][5:7])}"))
    return candidats


def _regles_contrats(db, clients, reference):
    annee, mois = reference
    candidats = []
    for contrat, etat in parc.contrats_avec_etat(db, clients, config.SEUIL_SOUS_UTILISATION):
        c = contrat.client
        lien = "/contrats"
        if etat["statut"] == "depassement":
            candidats.append(_candidat(
                f"licences-depassees:{contrat.id}:{annee}-{mois:02d}", c, "licences", "avertissement",
                f"{c.nom} : {etat['utilise']} {'appareils' if contrat.produit == 'KSC' else 'postes'} pour {contrat.licences} licences {contrat.produit}",
                f"Contrat {contrat.reference or contrat.produit} : dépassement de {etat['utilise'] - contrat.licences}.", lien))
        cle_ech, _ = etat["echeance"]
        if cle_ech in ("expire", "proche", "a-prevoir"):
            niveau = {"expire": "critique", "proche": "avertissement", "a-prevoir": "info"}[cle_ech]
            titre = (f"{c.nom} : contrat {contrat.produit} expiré le {contrat.echeance:%d/%m/%Y}" if cle_ech == "expire"
                     else f"{c.nom} : contrat {contrat.produit} à renouveler avant le {contrat.echeance:%d/%m/%Y}")
            candidats.append(_candidat(f"echeance:{contrat.id}:{contrat.echeance.isoformat()}:{cle_ech}", c, "echeance",
                                       niveau, titre, f"{contrat.licences} licences · réf. {contrat.reference or '—'}.", lien))
    return candidats


def _regles_service(db, aujourd_hui=None):
    """Assistance mensuelle manquée (mois écoulé) ou non réalisée en fin de mois ; certification bientôt expirée."""
    from . import service_technique as st
    from .modeles import AssistancePlanifiee, Certification, Utilisateur
    aujourd_hui = aujourd_hui or date.today()
    candidats = []
    precedent = (aujourd_hui.year - 1, 12) if aujourd_hui.month == 1 else (aujourd_hui.year, aujourd_hui.month - 1)
    for annee, mois in (precedent, (aujourd_hui.year, aujourd_hui.month)):
        st.assurer_planning(db, annee, mois)
        courant = (annee, mois) == (aujourd_hui.year, aujourd_hui.month)
        if courant and aujourd_hui.day < JOUR_RAPPEL_ASSISTANCE:
            continue
        for a in db.scalars(select(AssistancePlanifiee).where(AssistancePlanifiee.annee == annee, AssistancePlanifiee.mois == mois,
                                                              AssistancePlanifiee.statut.in_(("a_planifier", "planifiee")))):
            libelle = fmt_mois(annee, mois).lower()
            if courant:
                cle, niveau = f"assistance-rappel:{a.client_id}:{annee}-{mois:02d}", "avertissement"
                titre = f"{a.client.nom} : assistance de {libelle} pas encore réalisée"
            else:
                cle, niveau = f"assistance-manquee:{a.client_id}:{annee}-{mois:02d}", "critique"
                titre = f"{a.client.nom} : assistance mensuelle de {libelle} non réalisée"
            candidats.append(_candidat(cle, a.client, "assistance", niveau, titre,
                                       "Planifiée le " + a.date_prevue.strftime("%d/%m/%Y") if a.date_prevue else "Aucune date planifiée.",
                                       f"/assistances?annee={annee}&mois={mois}"))
    for c in db.scalars(select(Certification).join(Utilisateur).where(
            Utilisateur.actif.is_(True), Certification.expire_le.is_not(None),
            Certification.expire_le <= aujourd_hui + timedelta(days=60))):
        expiree = c.expire_le < aujourd_hui
        candidats.append(_candidat(
            f"certification:{c.id}:{c.expire_le.isoformat()}:{'expiree' if expiree else 'bientot'}", None, "certification",
            "avertissement" if not expiree else "critique",
            f"{c.utilisateur.nom} : certification « {c.intitule} » " + ("expirée" if expiree else f"expire le {c.expire_le:%d/%m/%Y}"),
            f"{c.editeur} · à renouveler.", f"/techniciens/{c.utilisateur_id}#certifications"))
    return candidats


def evaluer(db, reference=None):
    """Crée les alertes nouvelles (clé encore inconnue) ; renvoie la liste des alertes créées."""
    reference = reference or mois_courant()
    clients = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    candidats = _regles_incidents(db, clients) + _regles_contrats(db, clients, reference) + _regles_service(db)
    for c in clients:
        candidats += _regles_rapports(db, c, reference) + _regles_serveurs(db, c, reference)
    connues = set(db.scalars(select(Alerte.cle).where(Alerte.cle.in_([x["cle"] for x in candidats]))))
    nouvelles = []
    for x in candidats:
        if x["cle"] not in connues:
            connues.add(x["cle"])
            nouvelles.append(Alerte(**x))
    db.add_all(nouvelles)
    db.flush()
    return nouvelles


def evaluer_et_notifier(db, reference=None, en_arriere_plan=True):
    """Évalue, enregistre et notifie. Les erreurs de notification n'empêchent jamais l'enregistrement."""
    nouvelles = evaluer(db, reference)
    db.commit()
    if nouvelles and notifications_configurees():
        ids = [a.id for a in nouvelles]
        if en_arriere_plan:
            threading.Thread(target=_notifier_ids, args=(ids,), daemon=True).start()
        else:
            _notifier_ids(ids)
    return nouvelles


# --------------------------------------------------------------------------- #
# Canaux de notification
# --------------------------------------------------------------------------- #
def email_configure():
    return bool(config.SMTP["hote"] and config.SMTP["expediteur"])


def notifications_configurees():
    return (email_configure() and bool(config.ALERTES_EMAILS)) or bool(config.TEAMS_WEBHOOK)


def envoyer_email(destinataires, sujet, texte, html=None, pieces_jointes=()):
    """pieces_jointes : [(nom de fichier, octets PDF)]."""
    s = config.SMTP
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = sujet, s["expediteur"], ", ".join(destinataires)
    message.set_content(texte)
    if html:
        message.add_alternative(html, subtype="html")
    for nom, contenu in pieces_jointes:
        message.add_attachment(contenu, maintype="application", subtype="pdf", filename=nom)
    classe = smtplib.SMTP_SSL if s["securite"] == "ssl" else smtplib.SMTP
    with classe(s["hote"], s["port"], timeout=20) as serveur:
        if s["securite"] == "starttls":
            serveur.starttls()
        if s["utilisateur"]:
            serveur.login(s["utilisateur"], s["mot_de_passe"])
        serveur.send_message(message)


def envoyer_teams(titre, lignes, lien=None):
    """Carte adaptative postée sur un workflow Teams « Lorsqu'une requête webhook est reçue »."""
    corps = [{"type": "TextBlock", "text": titre, "weight": "Bolder", "size": "Medium", "wrap": True}]
    corps += [{"type": "TextBlock", "text": l, "wrap": True, "spacing": "Small"} for l in lignes]
    carte = {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.4",
             "body": corps}
    if lien:
        carte["actions"] = [{"type": "Action.OpenUrl", "title": "Ouvrir la plateforme", "url": lien}]
    charge = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": carte}]}
    requete = urllib.request.Request(config.TEAMS_WEBHOOK, data=json.dumps(charge).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(requete, timeout=20) as reponse:
        if reponse.status >= 300:
            raise RuntimeError(f"Teams a répondu {reponse.status}")


COULEURS = {"critique": "#B3261E", "avertissement": "#A75A06", "info": "#00809C"}


def _html_alertes(alertes):
    lignes = "".join(
        f'<tr><td style="padding:8px 10px;border-top:1px solid #E2E7EA;color:{COULEURS.get(a.niveau, "#13212B")};'
        f'font-weight:bold;white-space:nowrap">{escape(a.niveau.capitalize())}</td>'
        f'<td style="padding:8px 10px;border-top:1px solid #E2E7EA"><a href="{config.URL_PLATEFORME}{escape(a.lien or "/alertes")}" '
        f'style="color:#00507A;font-weight:bold;text-decoration:none">{escape(a.titre)}</a>'
        f'<div style="color:#475660;font-size:13px">{escape(a.detail)}</div></td></tr>' for a in alertes)
    return f'<table style="border-collapse:collapse;width:100%;font-family:Segoe UI,Arial,sans-serif;font-size:14px">{lignes}</table>'


def _gabarit_email(titre, corps_html):
    return (f'<div style="font-family:Segoe UI,Arial,sans-serif;color:#13212B;max-width:720px">'
            f'<div style="border-bottom:3px solid #8DC21F;padding-bottom:8px;margin-bottom:16px">'
            f'<div style="font-size:12px;letter-spacing:2px;color:#0099BA;text-transform:uppercase">ESAY · Rapports de sécurité</div>'
            f'<div style="font-size:20px;font-weight:bold;color:#00507A">{escape(titre)}</div></div>{corps_html}'
            f'<p style="color:#7A8891;font-size:12px;margin-top:20px">Message automatique — '
            f'<a href="{config.URL_PLATEFORME}/alertes" style="color:#00507A">voir toutes les alertes</a></p></div>')


def _notifier_ids(ids):
    from .db import Session  # import local : appelé depuis un fil ou un processus d'analyse
    with Session() as db:
        alertes = db.scalars(select(Alerte).where(Alerte.id.in_(ids)).order_by(Alerte.niveau, Alerte.id)).all()
        erreurs = notifier(alertes)
        for a in alertes:
            a.notifiee_le = datetime.now() if not erreurs else None
            a.erreur_notification = "; ".join(erreurs) or None
        db.commit()


def notifier(alertes):
    """Envoie les alertes sur les canaux configurés ; renvoie la liste des erreurs (vide si tout est passé)."""
    erreurs = []
    titre = f"{len(alertes)} nouvelle(s) alerte(s) de sécurité"
    if email_configure() and config.ALERTES_EMAILS:
        try:
            texte = "\n".join(f"[{a.niveau}] {a.titre} — {a.detail}" for a in alertes)
            envoyer_email(config.ALERTES_EMAILS, f"[Alertes sécurité] {alertes[0].titre}" if len(alertes) == 1 else f"[Alertes sécurité] {titre}",
                          texte, _gabarit_email(titre, _html_alertes(alertes)))
        except Exception as e:  # noqa: BLE001  (serveur injoignable, authentification…)
            journal.warning("Envoi e-mail des alertes : %s", e)
            erreurs.append(f"e-mail : {e}")
    if config.TEAMS_WEBHOOK:
        try:
            envoyer_teams(titre, [f"**{a.niveau.capitalize()}** — {a.titre}" for a in alertes[:15]], f"{config.URL_PLATEFORME}/alertes")
        except Exception as e:  # noqa: BLE001
            journal.warning("Envoi Teams des alertes : %s", e)
            erreurs.append(f"Teams : {e}")
    return erreurs


# --------------------------------------------------------------------------- #
# Résumé hebdomadaire (direction)
# --------------------------------------------------------------------------- #
def periode_semaine(jour=None):
    a, s, _ = (jour or date.today()).isocalendar()
    return f"{a}-S{s:02d}"


def contenu_resume(db, jour=None):
    """Données du résumé : alertes de la semaine, production du mois, clients à risque, contrats."""
    jour = jour or date.today()
    annee, mois = mois_courant(jour)
    clients = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    hebdos = services.hebdos_du_mois(db, annee, mois)
    etats = [services.etat_client(db, c, annee, mois, hebdos) for c in clients]
    production = {}
    for e in etats:
        production[e["etat"]] = production.get(e["etat"], 0) + 1
    semaine = db.scalars(select(Alerte).where(Alerte.cree_le >= datetime.combine(jour - timedelta(days=7), datetime.min.time()))
                         .order_by(Alerte.cree_le.desc())).all()
    nb_ouvertes = db.scalar(select(func.count()).select_from(Alerte).where(Alerte.traitee.is_(False)))
    risques = []
    for c in clients:
        points = services.historique(db, c.id, annee, mois, nb_mois=2)
        if points:
            risques.append((c, points[-1]))
    ordre = {"Critique": 0, "Élevé": 1, "Modéré": 2, "Faible": 3}
    risques.sort(key=lambda x: (ordre.get(x[1]["niveau"], 9), -(x[1]["indicateurs"].get("appareils_critiques") or 0)))
    contrats = [(k, e) for k, e in parc.contrats_avec_etat(db, clients, config.SEUIL_SOUS_UTILISATION)
                if e["echeance"][0] in ("expire", "proche", "a-prevoir") or e["statut"] == "depassement"]
    return {"jour": jour, "semaine": periode_semaine(jour), "mois": fmt_mois(annee, mois), "production": production,
            "nb_clients": len(clients), "alertes": semaine, "nb_ouvertes": nb_ouvertes, "risques": risques[:5],
            "contrats": contrats}


def html_resume(r):
    def bloc(titre, contenu):
        return (f'<h3 style="font-size:15px;color:#00507A;margin:22px 0 8px;border-bottom:1px solid #E2E7EA;padding-bottom:4px">'
                f'{escape(titre)}</h3>{contenu}')
    prod = " · ".join(f"<strong>{n}</strong> {escape(etat.lower())}" for etat, n in sorted(r["production"].items()))
    corps = (f'<p>Semaine {escape(r["semaine"])} — {r["nb_clients"]} clients suivis. '
             f'<strong>{r["nb_ouvertes"]}</strong> alerte(s) ouverte(s) au total.</p>')
    corps += bloc(f"Production de {r['mois']}", f"<p>{prod or 'Aucun client actif.'}</p>")
    corps += bloc(f"Alertes des 7 derniers jours ({len(r['alertes'])})",
                  _html_alertes(r["alertes"]) if r["alertes"] else "<p>Aucune nouvelle alerte.</p>")
    if r["risques"]:
        lignes = "".join(f'<tr><td style="padding:6px 10px;border-top:1px solid #E2E7EA"><strong>{escape(c.nom)}</strong></td>'
                         f'<td style="padding:6px 10px;border-top:1px solid #E2E7EA">{escape(p["niveau"] or "—")} ({escape(p["libelle"])})</td>'
                         f'<td style="padding:6px 10px;border-top:1px solid #E2E7EA">{p["indicateurs"].get("appareils_critiques", "—")} appareils critiques</td></tr>'
                         for c, p in r["risques"])
        corps += bloc("Clients les plus exposés (dernier rapport validé)",
                      f'<table style="border-collapse:collapse;width:100%;font-size:14px">{lignes}</table>')
    if r["contrats"]:
        lignes = "".join(f'<li><strong>{escape(k.client.nom)}</strong> — {escape(k.produit)} {k.licences} licences : '
                         f'{escape(e["echeance"][1] if e["echeance"][0] != "aucune" else "")}'
                         f'{" · " + escape(e["libelle"]) if e["statut"] == "depassement" else ""}</li>' for k, e in r["contrats"])
        corps += bloc("Contrats à surveiller", f"<ul>{lignes}</ul>")
    return _gabarit_email(f"Résumé hebdomadaire — semaine {r['semaine']}", corps)


def texte_resume(r):
    lignes = [f"Résumé hebdomadaire {r['semaine']} — {r['nb_clients']} clients, {r['nb_ouvertes']} alerte(s) ouverte(s)."]
    lignes += [f"- [{a.niveau}] {a.titre}" for a in r["alertes"]] or ["Aucune nouvelle alerte cette semaine."]
    return "\n".join(lignes)


def envoyer_resume(db, forcer=False, jour=None):
    """Envoie le résumé de la semaine (une seule fois par semaine, sauf forcer). Renvoie (envoyé, message)."""
    if not ((email_configure() and config.RESUME_EMAILS) or config.TEAMS_WEBHOOK):
        return False, "Aucun canal configuré (SMTP + RESUME_EMAILS, ou TEAMS_WEBHOOK)."
    r = contenu_resume(db, jour)
    deja = db.scalar(select(Envoi).where(Envoi.type == "resume_hebdo", Envoi.periode == r["semaine"]))
    if deja and not forcer:
        return False, f"Résumé de la semaine {r['semaine']} déjà envoyé le {deja.envoye_le:%d/%m/%Y %H:%M}."
    erreurs = []
    if email_configure() and config.RESUME_EMAILS:
        try:
            envoyer_email(config.RESUME_EMAILS, f"[Sécurité] Résumé hebdomadaire — semaine {r['semaine']}", texte_resume(r), html_resume(r))
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"e-mail : {e}")
    if config.TEAMS_WEBHOOK:
        try:
            envoyer_teams(f"Résumé hebdomadaire — semaine {r['semaine']}",
                          [texte_resume(r).split("\n")[0]] + [f"• {a.titre}" for a in r["alertes"][:10]],
                          f"{config.URL_PLATEFORME}/")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"Teams : {e}")
    if erreurs:
        return False, "Échec de l'envoi : " + "; ".join(erreurs)
    if deja:
        deja.envoye_le = datetime.now()
    else:
        db.add(Envoi(type="resume_hebdo", periode=r["semaine"], detail=f"{len(r['alertes'])} alerte(s)"))
    db.commit()
    return True, f"Résumé de la semaine {r['semaine']} envoyé."
