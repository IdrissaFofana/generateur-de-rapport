"""Supervision (axe R3) : métriques au format Prometheus et journalisation vers syslog / SIEM.

- /metrics : compteurs de requêtes et de durées par route, état métier (analyses, rapports, alertes, imports en
  attente) et intégrité du journal d'audit. Accès par jeton (METRIQUES_JETON) ; route absente si non configurée.
- syslog : chaque ligne du journal d'audit, **avec son empreinte**, est émise après validation de la transaction.
  Le collecteur externe détient ainsi une copie de la chaîne : une troncature de la fin du journal devient détectable.
- événements de sécurité (échecs de connexion, verrouillages) dans un format stable, exploitable par fail2ban.
"""
import hmac
import logging
import logging.handlers
import socket
import threading
import time
from collections import defaultdict

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session as SessionOrm

from . import config

journal_audit = logging.getLogger("rapports.journal")
journal_securite = logging.getLogger("rapports.securite")

# --------------------------------------------------------------------------- #
# Journalisation externe
# --------------------------------------------------------------------------- #
_configure = False


def configurer_journalisation():
    """Sortie standard toujours (journald / docker logs) ; syslog distant si SYSLOG_HOTE est défini."""
    global _configure
    if _configure:
        return
    _configure = True
    format_ = logging.Formatter("rapports-esay[%(process)d]: %(name)s %(message)s")
    for nom in ("rapports.journal", "rapports.securite"):
        logger = logging.getLogger(nom)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        logger.addHandler(console)
        if config.SYSLOG_HOTE:
            distant = logging.handlers.SysLogHandler(
                address=(config.SYSLOG_HOTE, config.SYSLOG_PORT),
                socktype=socket.SOCK_STREAM if config.SYSLOG_PROTOCOLE == "tcp" else socket.SOCK_DGRAM,
                facility=logging.handlers.SysLogHandler.LOG_AUTHPRIV if nom == "rapports.securite"
                else logging.handlers.SysLogHandler.LOG_LOCAL0)
            distant.setFormatter(format_)
            logger.addHandler(distant)


def _valeur(texte):
    """Valeur clé=valeur sans espace ni guillemet (format stable pour les filtres fail2ban / SIEM)."""
    return str(texte or "-").replace('"', "'").replace("\n", " ")


def evenement_securite(evenement, ip, compte="", detail=""):
    journal_securite.info(f'evenement={evenement} ip={_valeur(ip)} compte="{_valeur(compte)}" detail="{_valeur(detail)}"')


@event.listens_for(SessionOrm, "after_flush")
def _memoriser_lignes(session, _contexte):
    from .modeles import Journal
    for obj in session.new:
        if isinstance(obj, Journal):
            session.info.setdefault("journal_a_emettre", []).append(obj)


@event.listens_for(SessionOrm, "after_commit")
def _emettre_lignes(session):
    for l in session.info.pop("journal_a_emettre", []):
        journal_audit.info(f'id={l.id} acteur="{_valeur(l.acteur)}" action="{_valeur(l.action)}" '
                           f'detail="{_valeur(l.detail)[:500]}" empreinte={l.empreinte}')


@event.listens_for(SessionOrm, "after_rollback")
def _oublier_lignes(session):
    session.info.pop("journal_a_emettre", None)


# --------------------------------------------------------------------------- #
# Métriques
# --------------------------------------------------------------------------- #
SEUILS_DUREE = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
_verrou = threading.Lock()
_requetes = defaultdict(int)                       # (méthode, route, classe de statut) → nombre
_durees = defaultdict(lambda: [0.0, 0, [0] * len(SEUILS_DUREE)])  # (méthode, route) → [somme, nombre, cumul par seuil]
DEMARRAGE = time.time()


def enregistrer_requete(methode, route, statut, duree):
    classe = f"{statut // 100}xx"
    with _verrou:
        _requetes[(methode, route, classe)] += 1
        d = _durees[(methode, route)]
        d[0] += duree
        d[1] += 1
        for i, seuil in enumerate(SEUILS_DUREE):
            if duree <= seuil:
                d[2][i] += 1


class MiddlewareMetriques:
    """Middleware ASGI : durée et statut de chaque requête, regroupés par **modèle** de route (/rapports/{rid}),
    jamais par URL réelle (cardinalité bornée, pas d'identifiant dans les métriques)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        debut, statut = time.perf_counter(), {"code": 500}

        async def envoyer(message):
            if message["type"] == "http.response.start":
                statut["code"] = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, envoyer)
        finally:
            route = scope.get("route")
            chemin = getattr(route, "path", None) or ("/static" if scope["path"].startswith("/static") else "autre")
            if chemin != "/metrics":
                enregistrer_requete(scope["method"], chemin, statut["code"], time.perf_counter() - debut)


def _echapper(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def _ligne(nom, valeur, **etiquettes):
    if etiquettes:
        e = ",".join(f'{k}="{_echapper(v)}"' for k, v in etiquettes.items())
        return f"{nom}{{{e}}} {valeur}"
    return f"{nom} {valeur}"


def exposition(db):
    """Texte au format d'exposition Prometheus 0.0.4."""
    from . import integrite
    from .modeles import Alerte, ExportKsc, Hebdo, ImportEnAttente, Rapport
    lignes = []

    def entete(nom, type_, aide):
        lignes.extend([f"# HELP {nom} {aide}", f"# TYPE {nom} {type_}"])

    entete("rapports_esay_demarrage_secondes", "gauge", "Horodatage du démarrage du processus")
    lignes.append(_ligne("rapports_esay_demarrage_secondes", round(DEMARRAGE)))
    with _verrou:
        requetes, durees = dict(_requetes), {k: (v[0], v[1], list(v[2])) for k, v in _durees.items()}
    entete("rapports_esay_requetes_total", "counter", "Requêtes HTTP traitées")
    for (m, r, c), n in sorted(requetes.items()):
        lignes.append(_ligne("rapports_esay_requetes_total", n, methode=m, route=r, statut=c))
    entete("rapports_esay_requete_duree_secondes", "histogram", "Durée de traitement des requêtes")
    for (m, r), (somme, nombre, cumuls) in sorted(durees.items()):
        for seuil, n in zip(SEUILS_DUREE, cumuls):
            lignes.append(_ligne("rapports_esay_requete_duree_secondes_bucket", n, methode=m, route=r, le=seuil))
        lignes.append(_ligne("rapports_esay_requete_duree_secondes_bucket", nombre, methode=m, route=r, le="+Inf"))
        lignes.append(_ligne("rapports_esay_requete_duree_secondes_sum", round(somme, 6), methode=m, route=r))
        lignes.append(_ligne("rapports_esay_requete_duree_secondes_count", nombre, methode=m, route=r))

    entete("rapports_esay_analyses", "gauge", "Fichiers déposés par type et statut d'analyse")
    for modele, type_ in ((Hebdo, "hebdo_mdr"), (ExportKsc, "export_ksc")):
        for statut, n in db.execute(select(modele.statut, func.count()).group_by(modele.statut)):
            lignes.append(_ligne("rapports_esay_analyses", n, type=type_, statut=statut))
    entete("rapports_esay_rapports", "gauge", "Rapports par périodicité et statut")
    for per, statut, n in db.execute(select(Rapport.periodicite, Rapport.statut, func.count()).group_by(Rapport.periodicite, Rapport.statut)):
        lignes.append(_ligne("rapports_esay_rapports", n, periodicite=per, statut=statut))
    entete("rapports_esay_alertes_ouvertes", "gauge", "Alertes ouvertes par niveau")
    for niveau, n in db.execute(select(Alerte.niveau, func.count()).where(Alerte.traitee.is_(False)).group_by(Alerte.niveau)):
        lignes.append(_ligne("rapports_esay_alertes_ouvertes", n, niveau=niveau))
    entete("rapports_esay_imports_en_attente", "gauge", "Rapports importés en attente de décision")
    lignes.append(_ligne("rapports_esay_imports_en_attente", db.scalar(select(func.count()).select_from(ImportEnAttente))))
    v = integrite.verifier(db)
    entete("rapports_esay_journal_integre", "gauge", "1 si la chaîne d'empreintes du journal d'audit est intacte")
    lignes.append(_ligne("rapports_esay_journal_integre", int(v["ok"])))
    entete("rapports_esay_journal_lignes", "gauge", "Lignes du journal d'audit")
    lignes.append(_ligne("rapports_esay_journal_lignes", v["lignes"]))
    return "\n".join(lignes) + "\n"


def jeton_valide(entete_autorisation):
    attendu = config.METRIQUES_JETON
    if not attendu or not entete_autorisation or not entete_autorisation.startswith("Bearer "):
        return False
    return hmac.compare_digest(entete_autorisation[7:].strip(), attendu)
