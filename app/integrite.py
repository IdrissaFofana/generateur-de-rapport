"""Journal d'audit infalsifiable : chaînage des lignes par empreinte SHA-256.

Chaque ligne contient l'empreinte de la ligne précédente et sa propre empreinte, calculée sur son contenu et
sur l'empreinte précédente. Modifier, supprimer ou réordonner une ligne rompt la chaîne à partir de cet endroit.
Limite : la suppression des dernières lignes n'est détectable qu'en comparant avec une empreinte « ancre »
conservée ailleurs (voir `ancre()` : à reporter dans un système externe, ex. syslog / SIEM).
"""
import hashlib

from sqlalchemy import select, text

ORIGINE = "0" * 64
VERROU = 7340021  # verrou consultatif PostgreSQL : sérialise l'écriture de la chaîne


def empreinte(precedente, identifiant, quand, acteur, action, detail):
    """Empreinte d'une ligne ; les champs sont séparés par un caractère absent des données (unité 0x1F)."""
    contenu = "\x1f".join((precedente, str(identifiant), quand.isoformat(timespec="microseconds"),
                           acteur or "", action or "", detail or ""))
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def chainer(db, ligne):
    """Complète une ligne de journal déjà ajoutée à la session : identifiant, empreinte précédente, empreinte.

    Le verrou transactionnel garantit qu'aucune autre transaction n'écrit dans la chaîne avant notre validation."""
    from .modeles import Journal
    db.execute(text("SELECT pg_advisory_xact_lock(:cle)"), {"cle": VERROU})
    precedente = db.scalar(select(Journal.empreinte).where(Journal.empreinte.is_not(None))
                           .order_by(Journal.id.desc()).limit(1)) or ORIGINE
    db.flush()  # attribue l'identifiant
    ligne.empreinte_precedente = precedente
    ligne.empreinte = empreinte(precedente, ligne.id, ligne.quand, ligne.acteur, ligne.action, ligne.detail)


def verifier(db):
    """Parcourt toute la chaîne en base, dans l'ordre des identifiants."""
    from .modeles import Journal
    return verifier_lignes(db.execute(select(Journal.id, Journal.quand, Journal.acteur, Journal.action, Journal.detail,
                                             Journal.empreinte, Journal.empreinte_precedente).order_by(Journal.id)).yield_per(1000))


def verifier_lignes(lignes):
    """lignes : objets (id, quand, acteur, action, detail, empreinte, empreinte_precedente) dans l'ordre.
    Renvoie {"ok", "lignes", "rupture": {id, raison} | None, "ancre"}."""
    precedente, n = ORIGINE, 0
    for l in lignes:
        n += 1
        if l.empreinte_precedente != precedente:
            return {"ok": False, "lignes": n, "rupture": {"id": l.id, "raison": "maillon manquant ou réordonné (ligne supprimée ou insérée)"},
                    "ancre": precedente}
        attendue = empreinte(precedente, l.id, l.quand, l.acteur, l.action, l.detail)
        if l.empreinte != attendue:
            return {"ok": False, "lignes": n, "rupture": {"id": l.id, "raison": "contenu modifié"}, "ancre": precedente}
        precedente = l.empreinte
    return {"ok": True, "lignes": n, "rupture": None, "ancre": precedente}
