"""Tests unitaires des règles métier déjà en place (fonctions pures)."""
from datetime import date

from app.moteur import bilan as mbilan
from app.moteur import parc as mparc
from app.moteur.analyse import analyser_mdr, hebdo_disponible_le
from app.moteur.outils import mois_courant, mois_decale
from app.rendu import courbes


def test_hebdo_disponible_le_lundi_suivant_plus_delai():
    assert hebdo_disponible_le(date(2026, 9, 27)) == date(2026, 10, 1)   # dimanche → lundi 28 + 3
    assert hebdo_disponible_le(date(2026, 9, 28)) == date(2026, 10, 8)   # lundi → lundi suivant + 3


def test_jours_a_venir_puis_manquants():
    hebdo = {"postes": {"X": {date(2026, 9, j): 5 for j in range(1, 28)}}, "incidents": [],
             "debut": date(2026, 9, 21), "fin": date(2026, 9, 28), "fichier": "s"}
    bornes = (date(2026, 9, 1), date(2026, 10, 1))
    assert len(analyser_mdr([hebdo], {"X"}, *bornes, aujourd_hui=date(2026, 9, 29))["jours_a_venir"]) == 3
    assert analyser_mdr([hebdo], {"X"}, *bornes, aujourd_hui=date(2026, 10, 12))["jours_a_venir"] == []


def test_mois():
    assert mois_decale(2026, 1, -1) == (2025, 12) and mois_decale(2026, 12, 1) == (2027, 1)
    assert mois_courant(date(2026, 9, 24)) == (2026, 8) and mois_courant(date(2026, 9, 25)) == (2026, 9)
    assert mois_courant(date(2026, 1, 3)) == (2025, 12)


def test_periodes_des_bilans():
    assert mbilan.bornes_periode("trimestriel", 2026, 3) == (date(2026, 7, 1), date(2026, 10, 1))
    assert mbilan.bornes_periode("semestriel", 2026, 2) == (date(2026, 7, 1), date(2027, 1, 1))
    assert mbilan.libelle_court("trimestriel", 2026, 3) == "T3 2026"
    assert mbilan.periode_courante("trimestriel", date(2026, 9, 30)) == (2026, 3)
    assert mbilan.periode_courante("trimestriel", date(2026, 8, 10)) == (2026, 2)


def test_fins_de_support():
    assert mparc.fin_de_support("Microsoft Windows 8.1 Pro") == date(2023, 1, 10)   # 8.1 n'est pas confondu avec 8
    assert mparc.fin_de_support("Microsoft Windows 11") is None
    assert mparc.statut_support(date(2027, 1, 12), date(2026, 9, 30))[0] == "urgent"


def test_historique_appareils_series():
    p = lambda noms: {"appareils": [{"appareil": n, "etat": "Critique", "os": "Windows 11", "serveur": False} for n in noms]}
    h = mparc.historique_appareils([(2026, 7, p(["A", "B"])), (2026, 8, None), (2026, 9, p(["A"]))])
    fiches = {f["appareil"]: f for f in h["appareils"]}
    assert fiches["A"]["serie"] == 2 and fiches["A"]["recurrent"]   # le mois sans export ne casse pas la série
    assert not fiches["B"]["present"] and fiches["B"] in h["resolus"]


def test_courbes_echelle_et_variation():
    assert courbes._echelle_max(46) == 50 and courbes._echelle_max(1752) == 2000 and courbes._echelle_max(0) == 1
    points = [{"libelle": "a", "indicateurs": {"x": 10}}, {"libelle": "b", "indicateurs": {"x": None}},
              {"libelle": "c", "indicateurs": {"x": 7}}]
    assert courbes.variation(points, "x") == (-3, "−3")


def test_couverture_mdr():
    from app.moteur.analyse import couverture_mdr
    statut = lambda mx, total: couverture_mdr({"max": mx, "tenant_trouve": True}, {"total": total})["statut"]
    assert statut(27, 49) == "Élevé"          # 55 % : ce n'est pas « Normal »
    assert statut(47, 49) == "Normal" and statut(40, 49) == "À surveiller" and statut(20, 49) == "Critique"
    assert couverture_mdr({"max": 0, "tenant_trouve": True}, {"total": 49})["statut"] == "Critique"
    assert couverture_mdr({"max": 12, "tenant_trouve": True}, None)["statut"] == "Non mesurée"  # sans export KSC : pas de dénominateur
    assert couverture_mdr(None, {"total": 49}) is None


def test_lecture_des_raisons_ksc():
    from app.moteur.lecture_ksc import analyser_raison
    assert analyser_raison("L'appareil n'est plus administré. L'appareil ne s'est pas connecté au Serveur d'administration depuis longtemps .",
                           "N/A") == (["deconnecte", "non_administre"], [])
    assert analyser_raison("État de l'appareil défini par l'application .", "Serveurs de KSN indisponibles") == (["ksn"], [])
    assert analyser_raison("La licence a expiré. Des applications incompatibles sont installées.", "N/A")[0] == ["incompatible", "licence"]
    # une raison inconnue n'est pas perdue
    assert analyser_raison("Le disque est plein.", "") == (["autre"], ["Le disque est plein"])


def test_diagnostic_et_classement():
    from app.moteur.analyse import classement_etat_raison, diagnostic_par_raison
    app_ = lambda nom, etat, cles, serveur=False: {"appareil": nom, "etat": etat, "anomalies": cles, "serveur": serveur}
    parc = [app_("A", "Critique", ["ksn"], True), app_("B", "Critique", ["ksn"]), app_("C", "Critique", ["deconnecte", "non_administre"]),
            app_("D", "Avertissement", ["deconnecte"])]
    diag = diagnostic_par_raison(parc)
    assert [l["cle"] for l in diag] == ["non_administre", "deconnecte", "ksn"]  # impact « Très élevé » d'abord
    ksn = next(l for l in diag if l["cle"] == "ksn")
    assert ksn["appareils"] == 2 and ksn["serveurs"] == 1 and ksn["recommandation"]
    cl = classement_etat_raison(parc)
    assert [(g["etat"], g["appareils"]) for g in cl] == [("Critique", 2), ("Critique", 1), ("Avertissement", 1)]
    assert cl[1]["cles"] == ["non_administre", "deconnecte"]
