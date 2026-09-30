"""Tests unitaires du service technique : import d'anciens rapports, problèmes récurrents, durées, périodes."""
import os
from datetime import date, time
from types import SimpleNamespace

import pytest

from app import rapport_service as rs
from app import service_technique as st
from app.moteur.import_intervention import analyser, extraire_texte

RI = os.path.join(os.path.dirname(__file__), "..", "..", "R-I UDSON 21-04-2026.pdf")


@pytest.mark.skipif(not os.path.exists(RI), reason="rapport réel absent (dépôt public : fichier conservé hors du dépôt)")
def test_import_du_modele_ri():
    with open(RI, "rb") as f:
        r = analyser(extraire_texte(f.read(), ".pdf"), [(1, "HUDSON", "HUD", ["HUDSON"]), (2, "ANARE", "ANA", [])], ["Fofana Tennan Idrissa"])
    assert r["client_id"] == 1 and r["type"] == "deploiement"
    assert (r["date_debut"], r["date_fin"]) == (date(2026, 4, 21), date(2026, 4, 22))
    assert (r["heure_debut"], r["heure_fin"]) == (time(10, 0), time(17, 30))
    assert len(r["resultat"]) == 8 and r["resultat"][5].endswith("planifiée chaque lundi")  # puce sur deux lignes recollée
    assert r["statut_global"] == "OK" and r["points_bloquants"][0]["probleme"] == "Port (135, 445, 139) fermé"
    assert r["manquants"] == []


def test_import_texte_minimal():
    texte = "Rapport de maintenance\nClient : ANARE\nDate : 03/09/2026\n1. Objet\nMise à jour de la console.\n2. Résultat global\n• Mise à jour KSC\n• Nettoyage"
    r = analyser(texte, [(2, "ANARE", "ANA", [])])
    assert r["client_id"] == 2 and r["type"] == "maintenance" and r["date_debut"] == date(2026, 9, 3)
    assert r["objet"] == "Mise à jour de la console." and r["resultat"] == ["Mise à jour KSC", "Nettoyage"]


def test_import_signale_les_champs_manquants():
    assert set(analyser("Un texte sans repère.", [])["manquants"]) >= {"client", "date", "objet"}


def test_regroupement_des_problemes():
    a, b = st.mots_significatifs("Port (135, 445, 139) fermé"), st.mots_significatifs("Ports 135 445 139 fermés")
    assert a == b and st.jaccard(a, b) == 1.0
    assert st.jaccard(st.mots_significatifs("KSN inaccessible"), st.mots_significatifs("Licence expirée")) == 0.0


def test_duree_heures():
    i = SimpleNamespace(heure_debut=time(10), heure_fin=time(17, 30), date_debut=date(2026, 4, 21), date_fin=date(2026, 4, 22))
    assert st.duree_heures(i) == 15.0  # 7 h 30 × 2 jours
    i.heure_fin = None
    assert st.duree_heures(i) is None


def test_etat_assistance():
    a = SimpleNamespace(annee=2026, mois=9, statut="planifiee", date_prevue=date(2026, 9, 29))
    assert st.etat(a, date(2026, 9, 28))[0] == "planifiee"
    assert st.etat(a, date(2026, 9, 30))[0] == "retard"
    a.statut = "reportee"
    assert st.etat(a, date(2026, 10, 5))[0] == "reportee"


def test_periodes_du_rapport_de_service():
    assert rs.bornes("mensuel", 2026, 9) == (date(2026, 9, 1), date(2026, 10, 1))
    assert rs.bornes("annuel", 2026, 1) == (date(2026, 1, 1), date(2027, 1, 1))
    assert rs.libelle("trimestriel", 2026, 3) == "3e trimestre 2026" and rs.libelle_court("semestriel", 2026, 2) == "S2 2026"
    assert rs.periode_par_defaut("trimestriel", date(2026, 9, 30)) == (2026, 3)
