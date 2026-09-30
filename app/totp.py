"""Double authentification par mot de passe à usage unique basé sur le temps (TOTP, RFC 6238 / HOTP RFC 4226).

Compatible avec les applications d'authentification courantes (Microsoft Authenticator, Google Authenticator,
FreeOTP…) : SHA-1, 6 chiffres, pas de 30 secondes. Aucun service externe n'est sollicité.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PAS = 30          # durée de validité d'un code (secondes)
CHIFFRES = 6
TOLERANCE = 1     # pas acceptés de part et d'autre (décalage d'horloge du téléphone)
EMETTEUR = "ESAY Rapports"


def generer_secret():
    """Secret aléatoire de 160 bits, encodé en base32 (format attendu par les applications)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _cle(secret):
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def hotp(secret, compteur, chiffres=CHIFFRES, algo=hashlib.sha1):
    """RFC 4226 : troncature dynamique du HMAC du compteur."""
    empreinte = hmac.new(_cle(secret), struct.pack(">Q", compteur), algo).digest()
    decalage = empreinte[-1] & 0x0F
    valeur = struct.unpack(">I", empreinte[decalage:decalage + 4])[0] & 0x7FFFFFFF
    return str(valeur % 10 ** chiffres).zfill(chiffres)


def pas_courant(instant=None):
    return int((time.time() if instant is None else instant) // PAS)


def code(secret, instant=None):
    return hotp(secret, pas_courant(instant))


def verifier(secret, saisi, dernier_pas=None, instant=None):
    """Renvoie le pas accepté (à mémoriser pour refuser un rejeu) ou None.

    Un code déjà utilisé (pas <= dernier_pas) est refusé même s'il est encore dans sa fenêtre de validité."""
    saisi = "".join(ch for ch in str(saisi or "") if ch.isdigit())
    if not secret or len(saisi) != CHIFFRES:
        return None
    courant = pas_courant(instant)
    for pas in range(courant - TOLERANCE, courant + TOLERANCE + 1):
        if dernier_pas is not None and pas <= dernier_pas:
            continue
        if hmac.compare_digest(hotp(secret, pas), saisi):
            return pas
    return None


def uri(secret, compte):
    """URI otpauth:// à encoder dans le QR code."""
    libelle = quote(f"{EMETTEUR}:{compte}")
    return f"otpauth://totp/{libelle}?secret={secret}&issuer={quote(EMETTEUR)}&algorithm=SHA1&digits={CHIFFRES}&period={PAS}"


def qr_svg(contenu):
    """QR code en SVG (en ligne dans la page, aucune ressource externe)."""
    import io

    import segno
    tampon = io.BytesIO()
    segno.make(contenu, error="m").save(tampon, kind="svg", scale=5, border=2, dark="#13212B", xmldecl=False,
                                         svgns=True, nl=False)
    return tampon.getvalue().decode()
