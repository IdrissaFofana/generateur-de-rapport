"""Analyse des fichiers déposés en arrière-plan.

La lecture d'un gros export KSC prend plusieurs minutes : elle est confiée à des
processus séparés (PyMuPDF ne supporte pas les analyses simultanées dans un même
processus, et le serveur web reste ainsi réactif). L'état est suivi dans la base
(en_attente → en_cours → ok | erreur) ; les analyses interrompues sont relancées au démarrage.
"""
import logging
import multiprocessing
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

from sqlalchemy import select, update

from . import alertes
from .db import Session
from .modeles import ANALYSE_OK, EN_ATTENTE, EN_COURS, ERREUR, ExportKsc, Hebdo
from .moteur.lecture_hebdo import lire_hebdo, vers_json
from .moteur.lecture_ksc import lire_export
from .stockage import absolu

journal = logging.getLogger("rapports.analyses")
_pool = None


def _executeur():
    # « spawn » : chaque processus d'analyse ouvre ses propres connexions (pas de connexion héritée)
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"))
    return _pool


def _analyser_hebdo(hid):
    with Session() as db:
        h = db.get(Hebdo, hid)
        if h is None:
            return
        h.statut, h.erreur = EN_COURS, None
        db.commit()
        try:
            lu = lire_hebdo(absolu(h.chemin))
            lu["fichier"] = h.fichier
            h.debut, h.fin, h.donnees = lu["debut"], lu["fin"], vers_json(lu)
            h.statut = ANALYSE_OK
        except Exception as e:  # le fichier reste listé avec son erreur
            journal.warning("Analyse hebdo %s : %s", hid, traceback.format_exc())
            h.statut, h.erreur = ERREUR, f"Fichier non reconnu comme rapport hebdomadaire MDR ({e})."
        db.commit()
        _alertes(db)


def _analyser_export(eid):
    with Session() as db:
        e = db.get(ExportKsc, eid)
        if e is None:
            return
        e.statut, e.erreur = EN_COURS, None
        db.commit()
        try:
            donnees = lire_export(absolu(e.chemin), nom_fichier=e.fichier, cache=False)
            e.type, e.donnees, e.statut = donnees["type"], donnees, ANALYSE_OK
            e.genere_le = datetime.fromisoformat(donnees["genere_le"]) if donnees.get("genere_le") else None
            # Le dernier export déposé d'un type remplace les précédents du même mois
            db.execute(update(ExportKsc)
                       .where(ExportKsc.client_id == e.client_id, ExportKsc.annee == e.annee,
                              ExportKsc.mois == e.mois, ExportKsc.type == e.type, ExportKsc.id != e.id,
                              ExportKsc.depose_le <= e.depose_le)
                       .values(remplace=True))
            plus_recent = db.scalar(select(ExportKsc.id).where(
                ExportKsc.client_id == e.client_id, ExportKsc.annee == e.annee, ExportKsc.mois == e.mois,
                ExportKsc.type == e.type, ExportKsc.depose_le > e.depose_le, ExportKsc.statut == ANALYSE_OK))
            e.remplace = plus_recent is not None
        except ValueError as ex:  # fichier non reconnu : cas attendu, message explicite
            journal.info("Export %s refusé : %s", eid, ex)
            e.statut, e.erreur = ERREUR, str(ex)
        except Exception as ex:
            journal.warning("Analyse export %s : %s", eid, traceback.format_exc())
            e.statut, e.erreur = ERREUR, f"Lecture impossible ({ex})."
        db.commit()
        _alertes(db)


def _alertes(db):
    """Nouvelles données (incident MDR, serveur critique…) : alertes évaluées dans le processus d'analyse."""
    try:
        alertes.evaluer_et_notifier(db, en_arriere_plan=False)
    except Exception:  # une alerte ne doit jamais faire échouer l'analyse
        journal.warning("Évaluation des alertes : %s", traceback.format_exc())


def planifier_hebdo(hid):
    _executeur().submit(_analyser_hebdo, hid)


def planifier_export(eid):
    _executeur().submit(_analyser_export, eid)


def arreter():
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)


def reprendre_analyses():
    """Au démarrage : relance ce qui était en attente ou interrompu."""
    with Session() as db:
        hebdos = db.scalars(select(Hebdo.id).where(Hebdo.statut.in_((EN_ATTENTE, EN_COURS)))).all()
        exports = db.scalars(select(ExportKsc.id).where(ExportKsc.statut.in_((EN_ATTENTE, EN_COURS)))).all()
    for hid in hebdos:
        planifier_hebdo(hid)
    for eid in exports:
        planifier_export(eid)
