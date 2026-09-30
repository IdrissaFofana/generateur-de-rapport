"""Tests unitaires de la phase 1 : double authentification, journal chaîné, protection contre la force brute."""
import base64
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import config, integrite, totp
from app.securite import LimiteurTentatives, compte_verrouille, enregistrer_echec, hacher, verifier

# Secret de la RFC 6238 (annexe B) : « 12345678901234567890 » en ASCII
SECRET_RFC = base64.b32encode(b"12345678901234567890").decode()


# --------------------------------------------------------------------------- #
# TOTP
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("instant, attendu8", [
    (59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130"),
])
def test_totp_vecteurs_rfc6238(instant, attendu8):
    """Vecteurs officiels (SHA-1, 8 chiffres) ; l'application utilise les 6 derniers chiffres."""
    assert totp.hotp(SECRET_RFC, totp.pas_courant(instant), chiffres=8) == attendu8
    assert totp.code(SECRET_RFC, instant) == attendu8[-6:]


def test_totp_accepte_le_code_courant_et_tolere_un_pas_de_decalage():
    secret, t = totp.generer_secret(), 1_700_000_000
    assert totp.verifier(secret, totp.code(secret, t), instant=t) == totp.pas_courant(t)
    assert totp.verifier(secret, totp.code(secret, t - 30), instant=t) is not None   # horloge en retard
    assert totp.verifier(secret, totp.code(secret, t - 90), instant=t) is None       # trop ancien


def test_totp_refuse_le_rejeu():
    secret, t = totp.generer_secret(), 1_700_000_000
    pas = totp.verifier(secret, totp.code(secret, t), instant=t)
    assert totp.verifier(secret, totp.code(secret, t), dernier_pas=pas, instant=t) is None


def test_totp_refuse_les_saisies_invalides():
    secret = totp.generer_secret()
    for saisie in ("", "12345", "abcdef", None, "1234567"):
        assert totp.verifier(secret, saisie) is None
    assert totp.verifier(None, "123456") is None


def test_totp_secret_et_uri():
    secret = totp.generer_secret()
    assert len(base64.b32decode(secret + "=" * (-len(secret) % 8))) == 20  # 160 bits
    uri = totp.uri(secret, "a.b@esay.ci")
    assert uri.startswith("otpauth://totp/") and f"secret={secret}" in uri and "period=30" in uri
    assert totp.qr_svg(uri).lstrip().startswith("<svg")


# --------------------------------------------------------------------------- #
# Journal chaîné
# --------------------------------------------------------------------------- #
def _chaine(n=5):
    lignes, precedente = [], integrite.ORIGINE
    for i in range(1, n + 1):
        l = SimpleNamespace(id=i, quand=datetime(2026, 9, 30, 10, 0, i), acteur="a@esay.ci", action=f"action {i}",
                            detail=f"détail {i}", empreinte_precedente=precedente)
        l.empreinte = integrite.empreinte(precedente, l.id, l.quand, l.acteur, l.action, l.detail)
        lignes.append(l)
        precedente = l.empreinte
    return lignes


def test_journal_chaine_intacte():
    r = integrite.verifier_lignes(_chaine())
    assert r["ok"] and r["lignes"] == 5 and r["ancre"] == _chaine()[-1].empreinte


def test_journal_detecte_une_modification():
    lignes = _chaine()
    lignes[2].detail = "détail falsifié"
    r = integrite.verifier_lignes(lignes)
    assert not r["ok"] and r["rupture"] == {"id": 3, "raison": "contenu modifié"}


def test_journal_detecte_une_suppression():
    lignes = _chaine()
    del lignes[1]
    r = integrite.verifier_lignes(lignes)
    assert not r["ok"] and r["rupture"]["id"] == 3 and "supprimée" in r["rupture"]["raison"]


def test_journal_detecte_un_reordonnancement():
    lignes = _chaine()
    lignes[1], lignes[2] = lignes[2], lignes[1]
    assert not integrite.verifier_lignes(lignes)["ok"]


def test_journal_empreinte_sensible_a_chaque_champ():
    base = ("0" * 64, 1, datetime(2026, 1, 1), "a", "b", "c")
    reference = integrite.empreinte(*base)
    for i, autre in enumerate(("1" * 64, 2, datetime(2026, 1, 2), "x", "y", "z")):
        variante = list(base)
        variante[i] = autre
        assert integrite.empreinte(*variante) != reference


# --------------------------------------------------------------------------- #
# Force brute
# --------------------------------------------------------------------------- #
def test_limiteur_fenetre_glissante():
    horloge = [0.0]
    lim = LimiteurTentatives(3, 60, horloge=lambda: horloge[0])
    for _ in range(3):
        assert not lim.bloque("1.2.3.4")
        lim.echec("1.2.3.4")
    assert lim.bloque("1.2.3.4") and not lim.bloque("5.6.7.8")
    horloge[0] = 61
    assert not lim.bloque("1.2.3.4")  # les échecs sont sortis de la fenêtre


def test_verrouillage_apres_echecs_consecutifs():
    u = SimpleNamespace(echecs_connexion=0, bloque_jusqua=None)
    t = datetime(2026, 9, 30, 12, 0)
    for i in range(config.VERROUILLAGE_ECHECS - 1):
        assert enregistrer_echec(u, t) is False
    assert enregistrer_echec(u, t) is True
    assert compte_verrouille(u, t) and u.echecs_connexion == 0
    assert not compte_verrouille(u, t + timedelta(minutes=config.VERROUILLAGE_MINUTES, seconds=1))


def test_mot_de_passe_scrypt():
    h = hacher("Motdepasse2026")
    assert h.startswith("scrypt$") and verifier("Motdepasse2026", h) and not verifier("autre", h)
    assert hacher("Motdepasse2026") != h  # sel aléatoire
