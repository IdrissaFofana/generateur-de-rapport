"""Essai du rendu PDF sur les données réelles (hors plateforme).

    python -m outils_dev.essai_rendu <dossier_sortie>      (depuis le dossier « plateforme »)
"""
import json
import os
import sys
import time

from app.moteur.analyse import consolider
from app.moteur.lecture_hebdo import lire_tous_hebdos
from app.moteur.lecture_ksc import exports_client, lire_export
from app.moteur.redaction import contenu_par_defaut
from app.rendu.pdf import html_rapport, pdf_depuis_html

RACINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PRESTA = {"nom": "ESAY", "nom_complet": "ESAY Corporation", "signataire": "Équipe technique ESAY"}

CAS = [
    ({"nom": "HUDSON", "tenants_mdr": ["HUDSON"], "mdr": True}, "HUDSON"),
    ({"nom": "ANARE", "tenants_mdr": ["root tenant"], "mdr": True}, None),
    ({"nom": "CLIENT KSC SEUL", "mdr": False, "suggerer_mdr": True}, "HUDSON"),
]


def main(sortie):
    os.makedirs(sortie, exist_ok=True)
    hebdos = lire_tous_hebdos(os.path.join(RACINE, "HEBDO"))
    for client, dossier in CAS:
        exports = {}
        if dossier:
            exports = {t: lire_export(c) for t, c in exports_client(os.path.join(RACINE, dossier)).items()}
        d = consolider(client, 2026, 9, hebdos, exports)
        contenu = contenu_par_defaut(d, PRESTA["nom"])
        t0 = time.time()
        html = html_rapport(d, contenu, PRESTA)
        nom = client["nom"].replace(" ", "_")
        with open(os.path.join(sortie, nom + ".html"), "w", encoding="utf-8") as f:
            f.write(html)
        with open(os.path.join(sortie, nom + ".pdf"), "wb") as f:
            f.write(pdf_depuis_html(html))
        with open(os.path.join(sortie, nom + ".json"), "w", encoding="utf-8") as f:
            json.dump({"donnees": d, "contenu": contenu}, f, ensure_ascii=False, indent=1)
        print(f"{client['nom']}: risque {d['risque']['niveau']}, {len(d['actions'])} actions, "
              f"PDF en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1])
