"""Assemblage du rapport HTML et conversion en PDF (WeasyPrint)."""
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import date, datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from ..moteur.analyse import IMPACT_ANOMALIES, LIBELLES_ANOMALIES
from ..moteur.outils import fmt_date, fmt_mois, fmt_nb, fmt_pct, pluriel
from . import graphiques

ICI = os.path.dirname(os.path.abspath(__file__))
STATIQUE = os.path.normpath(os.path.join(ICI, "..", "static"))

DESCRIPTIONS_MENACES = {
    "Adware": "Logiciels ou scripts publicitaires, souvent issus de sites web ou d'extensions de navigateur",
    "Cheval de Troie": "Programme malveillant déguisé : vol de données, téléchargement d'autres malwares",
    "Phishing": "Sites frauduleux visant à dérober identifiants ou données",
    "Objet dangereux (cloud)": "Fichier jugé dangereux par l'analyse de réputation cloud de Kaspersky",
    "Backdoor": "Prise de contrôle à distance d'un système",
    "Ver": "Programme se propageant de lui-même sur le réseau",
    "Exploit": "Code exploitant une vulnérabilité logicielle",
    "Outil à risque": "Logiciel légitime pouvant être détourné",
    "Application indésirable": "Application potentiellement indésirable",
}
GLOSSAIRE = [
    ("MDR", "Managed Detection and Response : détection et réponse aux incidents opérées par des analystes 24h/24."),
    ("KSC", "Kaspersky Security Center : console d'administration de la protection des postes et serveurs."),
    ("KSN", "Kaspersky Security Network : service cloud de réputation des fichiers et sites web en temps réel."),
    ("Télémétrie", "Données d'activité (processus, réseau, fichiers) envoyées par les postes au service MDR."),
    ("Vulnérabilité", "Faille d'un logiciel pouvant être exploitée par un attaquant ; corrigée par une mise à jour."),
    ("Phishing", "Hameçonnage : site ou message frauduleux visant à dérober des identifiants."),
    ("Adware", "Logiciel publicitaire indésirable, souvent intégré à des sites ou extensions de navigateur."),
]


# --------------------------------------------------------------------------- #
# Filtres
# --------------------------------------------------------------------------- #
def _slug(texte):
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _gras(texte):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(texte)))


def md(texte):
    """Paragraphes (ligne vide) + **gras** ; le reste est échappé."""
    if not texte:
        return Markup("")
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", texte) if p.strip()]
    return Markup("".join(f"<p>{_gras(p).replace(chr(10), '<br>')}</p>" for p in paragraphes))


def md_ligne(texte):
    return Markup(_gras(texte or ""))


def statut(texte):
    return Markup(f'<span class="st st-{_slug(texte)}">{escape(texte)}</span>')


def fdate(iso):
    return fmt_date(date.fromisoformat(iso[:10])) if iso else "—"


def fdate_courte(iso):
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else "—"


def virgule(x, dec=1):
    return str(round(x, dec)).replace(".", ",")


def sans_heure(texte_ksc):
    """« septembre 23, 2026 14:02:00 » -> « septembre 23, 2026 »"""
    return re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", texte_ksc or "")


# --------------------------------------------------------------------------- #
# Plan du document : une seule source pour le sommaire, la numérotation et les sections
# --------------------------------------------------------------------------- #
def construire_plan(d, contenu=None):
    p, m, v, mdr = d["protection"], d["menaces"], d["vulnerabilites"], d["mdr"]
    suivi = (contenu or {}).get("suivi")
    plan = [("synthese", "Synthèse exécutive", [])]
    if d["avec_mdr"]:
        sous = [("mdr-couverture", "Couverture de la supervision")]
        if mdr and mdr["tenant_trouve"] and mdr["max"]:
            sous.append(("mdr-incidents", "Incidents de sécurité"))
        plan.append(("mdr", "Supervision MDR (Managed Detection and Response)", sous))
    sous = []
    if p:
        sous.append(("anomalies", "Anomalies relevées"))
        if p["serveurs"]:
            sous.append(("serveurs", "Serveurs"))
        if p["hors_ligne"]:
            sous.append(("deconnectes", "Appareils déconnectés"))
        if p["os_obsoletes"]:
            sous.append(("systemes", "Systèmes d'exploitation"))
        sous.append(("services", "Répartition par service"))
    plan.append(("protection", "État de la protection du parc", sous))
    sous = []
    if m and m["detections"]:
        sous = [("typologie", "Typologie des menaces"), ("chronologie", "Chronologie"),
                ("exposes", "Appareils les plus exposés")]
    plan.append(("menaces", "Analyse des menaces", sous))
    plan.append(("vulnerabilites", "Analyse des vulnérabilités", [("applications", "Applications concernées")] if v else []))
    plan.append(("actions", "Plan d'action recommandé",
                 [("actions-suivi", "Suivi des actions du mois précédent"), ("actions-mois", "Actions du mois")]
                 if suivi else []))
    plan.append(("conclusion", "Conclusion", []))

    numeros, sommaire = {}, []
    for i, (ident, titre, sous) in enumerate(plan, 1):
        numeros[ident] = f"{i}."
        sommaire.append({"id": ident, "titre": f"{i}. {titre}", "niveau": 1})
        for j, (sid, stitre) in enumerate(sous, 1):
            numeros[sid] = f"{i}.{j}"
            sommaire.append({"id": sid, "titre": f"{i}.{j} {stitre}", "niveau": 2})

    annexes = []
    if p:
        annexes.append(("annexe-appareils", "Appareils en anomalie"))
    annexes += [("annexe-sources", "Sources et périmètre des données"), ("annexe-glossaire", "Glossaire")]
    for lettre, (ident, titre) in zip("ABCDEFG", annexes):
        numeros[ident] = f"Annexe {lettre} —"
        sommaire.append({"id": ident, "titre": f"Annexe {lettre} — {titre}", "niveau": 1})
    titres = {ident: titre for ident, titre, _ in plan}
    titres.update({sid: st for _, _, sous in plan for sid, st in sous})
    titres.update(dict(annexes))
    return numeros, titres, sommaire


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #
def anomalies(cles):
    return ", ".join(LIBELLES_ANOMALIES[k].replace(" (cloud Kaspersky)", "") for k in cles)


def groupes_tries(groupes):
    return sorted(groupes.items(), key=lambda g: (-sum(g[1].values()), g[0]))


def appareils_tries(appareils):
    return sorted(appareils, key=lambda a: (a["etat"] != "Critique", a["groupe"], a["appareil"]))


def _cle_version(v):
    return [int(x) for x in re.findall(r"\d+", v)] or [0]


def versions(liste, maxi=4):
    if not liste:
        return "—"
    triees = sorted(liste, key=_cle_version)
    return ", ".join(triees[:maxi]) + ("…" if len(triees) > maxi else "")


_env = Environment(loader=FileSystemLoader(os.path.join(ICI, "gabarits")), extensions=["jinja2.ext.do"],
                   autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
_env.filters.update(md=md, md_ligne=md_ligne, statut=statut, fdate=fdate, fdate_courte=fdate_courte,
                    nb=fmt_nb, virgule=virgule, sans_heure=sans_heure, slug=_slug, anomalies=anomalies)
_env.globals.update(pct=fmt_pct, pluriel=pluriel, LIBELLES=LIBELLES_ANOMALIES, IMPACTS=IMPACT_ANOMALIES,
                    DESCRIPTIONS=DESCRIPTIONS_MENACES, GLOSSAIRE=GLOSSAIRE, groupes_tries=groupes_tries,
                    appareils_tries=appareils_tries, versions=versions)


def evolution(d, cle):
    if cle not in (d.get("evolution") or {}):
        return "—"
    delta = d["evolution"][cle]
    if isinstance(delta, float):
        delta = round(delta, 1)
    if delta == 0:
        return "= stable"
    return ("▲ +" if delta > 0 else "▼ ") + str(delta).replace(".", ",")


def statut_taux(part, total, seuils=(0, 0.1, 0.3)):
    if not total or part <= seuils[0]:
        return "Bon"
    taux = part / total
    return "Critique" if taux > seuils[2] else "Élevé" if taux > seuils[1] else "Modéré"


INDICATEURS_EVOLUTION = [
    ("appareils_critiques", "Appareils en état critique"),
    ("detections", "Menaces détectées"),
    ("vulnerabilites_critiques", "Vulnérabilités critiques"),
    ("postes_mdr_moyenne", "Postes supervisés MDR (moyenne)"),
]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def points_evolution(d, contenu):
    """Mois précédents validés (figés dans les données) + mois du rapport."""
    courant = {"libelle": f"{MOIS_COURTS[d['mois'] - 1]} {str(d['annee'])[2:]}", "niveau": contenu.get("niveau_risque"),
               "indicateurs": d.get("indicateurs") or {}}
    return (d.get("historique") or []) + [courant]


def html_rapport(d, contenu, prestataire, date_rapport=None, apercu=False):
    """d : données consolidées (JSON) · contenu : textes modifiables · prestataire : config charte."""
    numeros, titres, sommaire = construire_plan(d, contenu)
    g = graphiques.tous(d, "svg")
    points = points_evolution(d, contenu)
    g["evolution"] = graphiques.evolution(points, INDICATEURS_EVOLUTION, "svg")
    return _env.get_template("rapport.html").render(
        d=d, c=contenu, presta=prestataire, numeros=numeros, titres=titres, sommaire=sommaire,
        graphiques=g, points_evolution=points, evolution=lambda cle: evolution(d, cle),
        statut_taux=statut_taux, mois=fmt_mois(d["annee"], d["mois"]),
        date_rapport=(date_rapport or date.today()).isoformat(), apercu=apercu,
        css=open(os.path.join(ICI, "gabarits", "rapport.css"), encoding="utf-8").read(),
    )


def pdf_depuis_html(html):
    """HTML -> PDF (octets). Utilise la bibliothèque WeasyPrint, sinon l'exécutable indiqué
    par la variable d'environnement WEASYPRINT_EXE (poste de développement Windows)."""
    base = STATIQUE + os.sep
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        exe = os.environ.get("WEASYPRINT_EXE") or shutil.which("weasyprint")
        if not exe:
            raise RuntimeError("WeasyPrint introuvable : installez le paquet Python « weasyprint » "
                               "ou indiquez l'exécutable dans WEASYPRINT_EXE.")
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(STATIQUE, f"_rendu_{os.getpid()}.html")  # à côté des ressources (polices, logo)
            sortie = os.path.join(tmp, "rapport.pdf")
            try:
                with open(source, "w", encoding="utf-8") as f:
                    f.write(html)
                subprocess.run([exe, "-e", "utf-8", source, sortie], check=True, capture_output=True)
            finally:
                if os.path.exists(source):
                    os.remove(source)
            with open(sortie, "rb") as f:
                return f.read()
    return HTML(string=html, base_url=base).write_pdf()


# --------------------------------------------------------------------------- #
# Bilans trimestriels et semestriels
# --------------------------------------------------------------------------- #
def construire_plan_bilan(d):
    plan = [("synthese", "Synthèse de la période"), ("evolution", "Évolution des indicateurs")]
    if d["avec_mdr"]:
        plan.append(("mdr", "Supervision MDR"))
    if d["categories_menaces"]:
        plan.append(("menaces", "Menaces détectées"))
    if d["applications"]:
        plan.append(("vulnerabilites", "Vulnérabilités"))
    plan += [("actions", "Bilan des actions"), ("perspectives", "Perspectives et recommandations"), ("conclusion", "Conclusion")]
    numeros, titres, sommaire = {}, {}, []
    for i, (ident, titre) in enumerate(plan, 1):
        numeros[ident], titres[ident] = f"{i}.", titre
        sommaire.append({"id": ident, "titre": f"{i}. {titre}", "niveau": 1})
    for lettre, (ident, titre) in zip("AB", [("annexe-sources", "Rapports mensuels consolidés"), ("annexe-glossaire", "Glossaire")]):
        numeros[ident], titres[ident] = f"Annexe {lettre} —", titre
        sommaire.append({"id": ident, "titre": f"Annexe {lettre} — {titre}", "niveau": 1})
    return numeros, titres, sommaire


def html_bilan(d, contenu, prestataire, date_rapport=None, apercu=False):
    """Bilan trimestriel / semestriel : d = consolidation des mensuels validés (moteur/bilan.py)."""
    numeros, titres, sommaire = construire_plan_bilan(d)
    points = [{"libelle": m["court"], "indicateurs": m["indicateurs"]} for m in d["mois"] if m["present"]]
    return _env.get_template("bilan.html").render(
        d=d, c=contenu, presta=prestataire, numeros=numeros, titres=titres, sommaire=sommaire,
        graphique_evolution=graphiques.evolution(points, INDICATEURS_EVOLUTION, "svg"),
        date_rapport=(date_rapport or date.today()).isoformat(), apercu=apercu,
        css=open(os.path.join(ICI, "gabarits", "rapport.css"), encoding="utf-8").read(),
    )


# --------------------------------------------------------------------------- #
# Rapports d'intervention
# --------------------------------------------------------------------------- #
def html_intervention(intervention, prestataire):
    """Rapport d'intervention (titre selon le type), daté du jour de validation."""
    from ..modeles import MODES_INTERVENTION
    jour = (intervention.valide_le or datetime.now()).date()
    return _env.get_template("intervention.html").render(
        i=intervention, presta=prestataire, MODES=MODES_INTERVENTION, date_rapport=jour.isoformat(),
        css=open(os.path.join(ICI, "gabarits", "rapport.css"), encoding="utf-8").read(),
    )


# --------------------------------------------------------------------------- #
# Rapport d'activité du service technique
# --------------------------------------------------------------------------- #
def html_service(d, contenu, prestataire, date_rapport=None):
    g = {}
    if any(m["interventions"] for m in d["par_mois"]) and len(d["par_mois"]) > 1:
        g["mois"] = graphiques.barres_mensuelles([m["libelle"] for m in d["par_mois"]], [m["interventions"] for m in d["par_mois"]],
                                                 "Interventions")
    if d["par_type"]:
        g["types"] = graphiques.barres_horizontales(list(d["par_type"].items()))
    return _env.get_template("service.html").render(
        d=d, c=contenu, presta=prestataire, graphiques=g, date_rapport=(date_rapport or date.today()).isoformat(),
        css=open(os.path.join(ICI, "gabarits", "rapport.css"), encoding="utf-8").read(),
    )
