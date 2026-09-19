#!/usr/bin/env python3
"""Passkeys (WebAuthn) with nothing but the standard library.

A passkey replaces password and code in one step. The private half never
leaves the device; the server stores only the public half and checks a
signature. That check is the whole of this file.

WHY IT IS WRITTEN OUT HERE. Every other tool in this repository runs in a
foreign CI without installing anything, and this one has to as well. The
usual route — a WebAuthn library on top of a cryptography library on top
of OpenSSL bindings — would break that for a job that comes down to two
signature checks. Both are integer arithmetic, and Python has arbitrary
precision integers, so they fit in a page each.

WHAT IS CHECKED, in the order the specification asks for it:

    clientDataJSON  type, challenge and origin — the challenge is one the
                    server handed out, once, and has since forgotten
    rpIdHash        the SHA-256 of our own host, so a signature made for
                    another site is worthless here
    flags           user present, and for registration: a key is attached
    signature       over authenticatorData || SHA-256(clientDataJSON)
    signCount       a counter that only ever goes up; a repeat means a
                    copy of the key exists somewhere

WHAT IS NOT CHECKED: the attestation statement. It says which make and
model of security key was used, and verifying it means keeping a list of
manufacturer certificates up to date. This portal has one operator and
their own devices; it asks for attestation "none" and looks only at the
public key inside. A shop that must prove which brand of key an employee
used needs more than this file — and a different kind of organisation.

ALGORITHMS: ES256 (ECDSA on NIST P-256) and RS256 (RSA PKCS#1 v1.5), and
only those, because those two are all the registration asks the browser
for. An authenticator cannot answer with something this file cannot read.

German on the page, English in the code, like every other tool here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json


class PasskeyError(Exception):
    """Refused. The message is shown to the person, so it says what to do."""


# --------------------------------------------------------------------------
# base64url, as WebAuthn uses it everywhere
# --------------------------------------------------------------------------
def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    if not isinstance(text, str):
        raise PasskeyError("Der Browser hat etwas anderes als Text geschickt.")
    padded = text.strip() + "=" * (-len(text.strip()) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise PasskeyError("Die Antwort des Browsers ist unlesbar.") from exc


# --------------------------------------------------------------------------
# CBOR, the part of it that WebAuthn uses
#
# Only what an attestation object and a COSE key contain: unsigned and
# negative integers, byte strings, text strings, arrays, maps and the three
# simple values. Indefinite lengths, tags and floats do not occur there, and
# refusing them is safer than guessing at them.
# --------------------------------------------------------------------------
def _cbor_item(data: bytes, i: int):
    if i >= len(data):
        raise PasskeyError("Die Antwort des Browsers bricht mitten im Datensatz ab.")
    first = data[i]
    major, info = first >> 5, first & 0x1F
    i += 1
    if info < 24:
        wert = info
    elif info == 24:
        wert, i = data[i], i + 1
    elif info == 25:
        wert, i = int.from_bytes(data[i:i + 2], "big"), i + 2
    elif info == 26:
        wert, i = int.from_bytes(data[i:i + 4], "big"), i + 4
    elif info == 27:
        wert, i = int.from_bytes(data[i:i + 8], "big"), i + 8
    else:
        raise PasskeyError("Der Datensatz benutzt eine Form, die hier nicht gilt.")

    if major == 0:
        return wert, i
    if major == 1:
        return -1 - wert, i
    if major in (2, 3):
        ende = i + wert
        if ende > len(data):
            raise PasskeyError("Der Datensatz ist kürzer als angekündigt.")
        roh = data[i:ende]
        return (roh if major == 2 else roh.decode("utf-8", "replace")), ende
    if major == 4:
        liste = []
        for _ in range(wert):
            eintrag, i = _cbor_item(data, i)
            liste.append(eintrag)
        return liste, i
    if major == 5:
        tabelle = {}
        for _ in range(wert):
            schluessel, i = _cbor_item(data, i)
            inhalt, i = _cbor_item(data, i)
            tabelle[schluessel] = inhalt
        return tabelle, i
    if major == 7:
        if info in (20, 21, 22):
            return {20: False, 21: True, 22: None}[info], i
        raise PasskeyError("Der Datensatz enthält einen Wert, den dieser Server "
                           "nicht liest.")
    raise PasskeyError("Der Datensatz ist nicht lesbar.")


def cbor_decode(data: bytes):
    wert, _ = _cbor_item(data, 0)
    return wert


# --------------------------------------------------------------------------
# ECDSA on NIST P-256 (COSE algorithm -7, ES256)
# --------------------------------------------------------------------------
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5


def _punkt_addieren(punkt_a, punkt_b):
    """Two points of the curve, added. None stands for the point at infinity."""
    if punkt_a is None:
        return punkt_b
    if punkt_b is None:
        return punkt_a
    x1, y1 = punkt_a
    x2, y2 = punkt_b
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if punkt_a == punkt_b:
        # a is -3 on this curve, so the tangent is (3x² - 3) / 2y.
        steigung = (3 * (x1 * x1 - 1) * pow(2 * y1, -1, _P)) % _P
    else:
        steigung = ((y2 - y1) * pow(x2 - x1, -1, _P)) % _P
    x3 = (steigung * steigung - x1 - x2) % _P
    return x3, (steigung * (x1 - x3) - y1) % _P


def _punkt_malnehmen(faktor: int, punkt):
    ergebnis = None
    while faktor:
        if faktor & 1:
            ergebnis = _punkt_addieren(ergebnis, punkt)
        punkt = _punkt_addieren(punkt, punkt)
        faktor >>= 1
    return ergebnis


def _auf_der_kurve(x: int, y: int) -> bool:
    return (y * y - (x * x * x - 3 * x + _B)) % _P == 0


def _der_signatur(signatur: bytes) -> tuple[int, int]:
    """SEQUENCE { INTEGER r, INTEGER s }, no more and no less."""
    def lese_integer(i: int) -> tuple[int, int]:
        if signatur[i] != 0x02:
            raise PasskeyError("Die Signatur hat nicht die erwartete Form.")
        laenge = signatur[i + 1]
        if laenge & 0x80:
            raise PasskeyError("Die Signatur hat nicht die erwartete Form.")
        roh = signatur[i + 2:i + 2 + laenge]
        if len(roh) != laenge:
            raise PasskeyError("Die Signatur ist kürzer als angekündigt.")
        return int.from_bytes(roh, "big"), i + 2 + laenge

    if len(signatur) < 8 or signatur[0] != 0x30:
        raise PasskeyError("Die Signatur hat nicht die erwartete Form.")
    laenge = signatur[1]
    if laenge & 0x80:  # lange Form: ein Laengenbyte sagt, wie viele folgen
        anzahl = laenge & 0x7F
        if anzahl != 1:
            raise PasskeyError("Die Signatur hat nicht die erwartete Form.")
        laenge, anfang = signatur[2], 3
    else:
        anfang = 2
    if anfang + laenge != len(signatur):
        raise PasskeyError("An die Signatur ist etwas angehängt.")
    r, weiter = lese_integer(anfang)
    s, ende = lese_integer(weiter)
    if ende != len(signatur):
        raise PasskeyError("An die Signatur ist etwas angehängt.")
    return r, s


def _es256_pruefen(x: int, y: int, nachricht: bytes, signatur: bytes) -> bool:
    if not _auf_der_kurve(x, y):
        return False
    r, s = _der_signatur(signatur)
    if not (0 < r < _N and 0 < s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(nachricht).digest(), "big")
    w = pow(s, -1, _N)
    punkt = _punkt_addieren(_punkt_malnehmen((e * w) % _N, (_GX, _GY)),
                            _punkt_malnehmen((r * w) % _N, (x, y)))
    if punkt is None:
        return False
    return punkt[0] % _N == r


# --------------------------------------------------------------------------
# RSA PKCS#1 v1.5 with SHA-256 (COSE algorithm -257, RS256)
# --------------------------------------------------------------------------
# DigestInfo of SHA-256, as RFC 8017 prints it.
_SHA256_KOPF = bytes.fromhex("3031300d060960864801650304020105000420")


def _rs256_pruefen(modulus: int, exponent: int, nachricht: bytes,
                   signatur: bytes) -> bool:
    laenge = (modulus.bit_length() + 7) // 8
    if len(signatur) != laenge or laenge < len(_SHA256_KOPF) + 43:
        return False
    zahl = int.from_bytes(signatur, "big")
    if zahl >= modulus:
        return False
    klartext = pow(zahl, exponent, modulus).to_bytes(laenge, "big")
    # EM = 0x00 || 0x01 || PS || 0x00 || DigestInfo || H, und PS fuellt den
    # Rest: k - 3 - 19 - 32 Byte 0xff. Ein Byte zu viel oder zu wenig, und
    # jede gueltige Signatur faellt durch — gemessen gegen OpenSSL.
    fuellung = laenge - 3 - len(_SHA256_KOPF) - 32
    if fuellung < 8:
        return False
    erwartet = (b"\x00\x01" + b"\xff" * fuellung + b"\x00" + _SHA256_KOPF
                + hashlib.sha256(nachricht).digest())
    return hmac.compare_digest(klartext, erwartet)


# --------------------------------------------------------------------------
# COSE keys
# --------------------------------------------------------------------------
ES256 = -7
RS256 = -257
ERLAUBTE_ALGORITHMEN = (ES256, RS256)


def _cose_pruefen(cose: dict, nachricht: bytes, signatur: bytes) -> bool:
    algorithmus = cose.get(3)
    if algorithmus == ES256:
        if cose.get(1) != 2 or cose.get(-1) != 1:
            raise PasskeyError("Der Schlüssel liegt nicht auf der erwarteten Kurve.")
        x, y = cose.get(-2), cose.get(-3)
        if not isinstance(x, bytes) or not isinstance(y, bytes):
            raise PasskeyError("Der Schlüssel ist unvollständig.")
        return _es256_pruefen(int.from_bytes(x, "big"), int.from_bytes(y, "big"),
                              nachricht, signatur)
    if algorithmus == RS256:
        if cose.get(1) != 3:
            raise PasskeyError("Der Schlüssel passt nicht zum Verfahren.")
        modulus, exponent = cose.get(-1), cose.get(-2)
        if not isinstance(modulus, bytes) or not isinstance(exponent, bytes):
            raise PasskeyError("Der Schlüssel ist unvollständig.")
        return _rs256_pruefen(int.from_bytes(modulus, "big"),
                              int.from_bytes(exponent, "big"), nachricht, signatur)
    raise PasskeyError("Dieses Gerät benutzt ein Verfahren, das der Server nicht "
                       "angefordert hat.")


def cose_speichern(cose: dict) -> str:
    """The public key as text, so it survives a trip through SQLite."""
    if cose.get(3) == ES256:
        return json.dumps({"alg": ES256, "x": b64url_encode(cose[-2]),
                           "y": b64url_encode(cose[-3])})
    if cose.get(3) == RS256:
        return json.dumps({"alg": RS256, "n": b64url_encode(cose[-1]),
                           "e": b64url_encode(cose[-2])})
    raise PasskeyError("Dieser Schlüsseltyp lässt sich hier nicht speichern.")


def cose_laden(gespeichert: str) -> dict:
    daten = json.loads(gespeichert)
    if daten["alg"] == ES256:
        return {1: 2, 3: ES256, -1: 1,
                -2: b64url_decode(daten["x"]), -3: b64url_decode(daten["y"])}
    return {1: 3, 3: RS256,
            -1: b64url_decode(daten["n"]), -2: b64url_decode(daten["e"])}


# --------------------------------------------------------------------------
# authenticatorData
# --------------------------------------------------------------------------
FLAG_BENUTZER_DA = 0x01      # user present: jemand hat das Geraet beruehrt
FLAG_BENUTZER_GEPRUEFT = 0x04  # user verified: PIN, Finger oder Gesicht
FLAG_SCHLUESSEL_DABEI = 0x40   # attested credential data folgt


class Authentikator:
    """The fixed part of authenticatorData, plus the key if one is attached."""

    def __init__(self, roh: bytes):
        if len(roh) < 37:
            raise PasskeyError("Die Antwort des Geräts ist zu kurz.")
        self.roh = roh
        self.rp_id_hash = roh[:32]
        self.flags = roh[32]
        self.sign_count = int.from_bytes(roh[33:37], "big")
        self.credential_id = b""
        self.cose = None
        if self.flags & FLAG_SCHLUESSEL_DABEI:
            if len(roh) < 55:
                raise PasskeyError("Die Antwort des Geräts ist zu kurz.")
            laenge = int.from_bytes(roh[53:55], "big")
            self.credential_id = roh[55:55 + laenge]
            if len(self.credential_id) != laenge:
                raise PasskeyError("Die Kennung des Schlüssels ist unvollständig.")
            self.cose, _ = _cbor_item(roh, 55 + laenge)

    @property
    def benutzer_da(self) -> bool:
        return bool(self.flags & FLAG_BENUTZER_DA)


# --------------------------------------------------------------------------
# clientDataJSON
# --------------------------------------------------------------------------
def _client_daten_pruefen(roh: bytes, art: str, challenge: str,
                          herkunft: str) -> None:
    try:
        daten = json.loads(roh.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PasskeyError("Der Browser hat unlesbare Daten geschickt.") from exc
    if daten.get("type") != art:
        raise PasskeyError("Die Antwort gehört zu einem anderen Vorgang.")
    # Der Vergleich laeuft ueber die Rohbytes: base64url ohne Polster ist
    # eindeutig, und ein Zeichenvergleich ohne Zeitgleichheit reicht hier
    # nicht, weil die Challenge ein Geheimnis auf Zeit ist.
    if not hmac.compare_digest(str(daten.get("challenge", "")), challenge):
        raise PasskeyError("Die Anfrage ist abgelaufen. Bitte noch einmal.")
    if daten.get("origin") != herkunft:
        raise PasskeyError(f"Die Antwort wurde für {daten.get('origin')} "
                           f"unterschrieben, nicht für {herkunft}.")


# --------------------------------------------------------------------------
# Die beiden Vorgaenge
# --------------------------------------------------------------------------
def registrierung_pruefen(*, client_daten: bytes, zeugnis: bytes, challenge: str,
                          herkunft: str, rp_id: str) -> tuple[str, str, int]:
    """A new passkey. Returns credential id, public key and counter."""
    _client_daten_pruefen(client_daten, "webauthn.create", challenge, herkunft)
    objekt = cbor_decode(zeugnis)
    if not isinstance(objekt, dict) or not isinstance(objekt.get("authData"), bytes):
        raise PasskeyError("Das Gerät hat keinen Schlüssel mitgeschickt.")
    daten = Authentikator(objekt["authData"])
    if not hmac.compare_digest(daten.rp_id_hash, hashlib.sha256(
            rp_id.encode("utf-8")).digest()):
        raise PasskeyError(f"Der Schlüssel wurde für einen anderen Server "
                           f"angelegt, nicht für {rp_id}.")
    if not daten.benutzer_da:
        raise PasskeyError("Das Gerät meldet, dass niemand bestätigt hat.")
    if not daten.credential_id or daten.cose is None:
        raise PasskeyError("Das Gerät hat keinen Schlüssel mitgeschickt.")
    if daten.cose.get(3) not in ERLAUBTE_ALGORITHMEN:
        raise PasskeyError("Dieses Gerät benutzt ein Verfahren, das der Server "
                           "nicht angefordert hat.")
    return (b64url_encode(daten.credential_id), cose_speichern(daten.cose),
            daten.sign_count)


def anmeldung_pruefen(*, client_daten: bytes, authenticator: bytes, signatur: bytes,
                      gespeicherter_schluessel: str, challenge: str, herkunft: str,
                      rp_id: str, zaehler: int) -> int:
    """An existing passkey. Returns the new counter, or refuses."""
    _client_daten_pruefen(client_daten, "webauthn.get", challenge, herkunft)
    daten = Authentikator(authenticator)
    if not hmac.compare_digest(daten.rp_id_hash, hashlib.sha256(
            rp_id.encode("utf-8")).digest()):
        raise PasskeyError(f"Die Unterschrift gilt für einen anderen Server, "
                           f"nicht für {rp_id}.")
    if not daten.benutzer_da:
        raise PasskeyError("Das Gerät meldet, dass niemand bestätigt hat.")
    nachricht = authenticator + hashlib.sha256(client_daten).digest()
    if not _cose_pruefen(cose_laden(gespeicherter_schluessel), nachricht, signatur):
        raise PasskeyError("Die Unterschrift stimmt nicht.")
    # Ein Zaehler, der nicht weitergelaufen ist, heisst: dieser Schluessel
    # existiert zweimal. Geraete, die gar nicht zaehlen, melden immer 0 —
    # das ist erlaubt und kein Befund.
    if daten.sign_count and daten.sign_count <= zaehler:
        raise PasskeyError("Dieser Passkey wurde offenbar kopiert. Er ist gesperrt, "
                           "bis er im Konto entfernt und neu angelegt wird.")
    return daten.sign_count


# --------------------------------------------------------------------------
# Was der Browser zum Anfangen braucht
# --------------------------------------------------------------------------
def registrierung_beginnen(*, challenge: str, rp_id: str, marke: str,
                           benutzer_kennung: str, benutzername: str,
                           vorhandene=()) -> dict:
    return {
        "challenge": challenge,
        "rp": {"id": rp_id, "name": marke},
        "user": {"id": b64url_encode(benutzer_kennung.encode("utf-8")),
                 "name": benutzername, "displayName": benutzername},
        "pubKeyCredParams": [{"type": "public-key", "alg": alg}
                             for alg in ERLAUBTE_ALGORITHMEN],
        "timeout": 120000,
        "attestation": "none",
        "authenticatorSelection": {"residentKey": "preferred",
                                   "userVerification": "preferred"},
        "excludeCredentials": [{"type": "public-key", "id": kennung}
                               for kennung in vorhandene],
    }


def anmeldung_beginnen(*, challenge: str, rp_id: str, erlaubte=()) -> dict:
    return {
        "challenge": challenge,
        "rpId": rp_id,
        "timeout": 120000,
        "userVerification": "preferred",
        "allowCredentials": [{"type": "public-key", "id": kennung}
                             for kennung in erlaubte],
    }
