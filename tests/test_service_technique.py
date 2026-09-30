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


@pytest.mark.parametrize("nom, texte, attendu", [
    ("HUDSON", "chez Hudson ce jour", True), ("HUDSON", "CHEZ HUDSON", True), ("Société Générale", "SOCIETE GENERALE", True),
    ("PAC CI", "rapport PAC-CI", True), ("PAC CI", "rapport PACCI", True), ("PAC CI", "Pac.CI", True),
    ("HUDSON", "hudsonville", False), ("CI", "ci", None),
])
def test_reconnaissance_du_nom(nom, texte, attendu):
    from app.moteur.import_intervention import _plat, motif_nom
    motif = motif_nom(nom)
    assert (motif is None) if attendu is None else bool(motif.search(_plat(texte))) is attendu


def test_client_reconnu_par_un_autre_nom_et_nom_ecrit():
    texte = "Rapport de migration\nClient : BSIC\nDate : 17/07/2026"
    assert analyser(texte, [(9, "Banque Sahélo", "BSA", [], ["BSIC"])])["client_id"] == 9
    r = analyser(texte, [(1, "HUDSON", "HUD", [])])
    assert r["client_id"] is None and r["client_nom"] == "BSIC"
    assert analyser("Nom du Client : ......................", [])["client_nom"] is None  # modèle vierge


BSIC_DOCX = os.path.join(os.path.dirname(__file__), "..", "..", "Rapport_Intervention_Migration_KSC_Web_BSIC.docx")
BSIC_PDF = os.path.join(os.path.dirname(__file__), "..", "..", "RI-Migration_KSC_Web-BSIC.pdf")


@pytest.mark.skipif(not all(map(os.path.exists, (RI, BSIC_DOCX, BSIC_PDF))), reason="rapports réels absents")
def test_similarite_doublons_sur_documents_reels():
    from app.interventions import similarite
    textes = {"docx": extraire_texte(open(BSIC_DOCX, "rb").read(), ".docx"), "pdf": extraire_texte(open(BSIC_PDF, "rb").read(), ".pdf"),
              "ri": extraire_texte(open(RI, "rb").read(), ".pdf")}
    c = {k: analyser(t, [(1, "BSIC", "BSI", [])]) for k, t in textes.items()}
    s = lambda a, b: similarite(c[a]["objet"], c[a]["resultat"], textes[a], c[b]["objet"], c[b]["resultat"], textes[b])
    assert s("docx", "pdf") >= 0.85   # même rapport, Word et PDF : doublon
    assert s("docx", "ri") < 0.3      # deux rapports différents


def test_similarite_saisie_et_assistances():
    from app.interventions import SEUIL_DOUBLON_TEXTE, similarite
    assert similarite("Déploiement KES", ["Installation agent"], None, "Déploiement KES", ["Installation agent"], "texte") == 1.0
    # deux assistances mensuelles de mois différents : semblables, mais sous le seuil appliqué aux dates éloignées
    assert similarite("Assistance mensuelle de septembre 2026.", ["Vérification des tâches"], None,
                      "Assistance mensuelle d'octobre 2026.", ["Vérification des tâches"], None) < SEUIL_DOUBLON_TEXTE


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
