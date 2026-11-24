#!/usr/bin/env python3
"""Il buco nero al centro della Galassia - motore di calcolo (versione 1.8).

Pesa Sagittarius A* con l'orbita della stella S2:
  - dati: Gillessen et al. 2017, ApJ 837, 30 (VizieR J/ApJ/837/30, table5 = astrometria
    e velocita' radiali di 17 stelle S, table3 = orbite pubblicate), facoltativo
    Chu et al. 2018, ApJ 854, 12 (VizieR J/ApJ/854/12, velocita' radiali Keck di S0-2 = S2);
  - modello: orbita kepleriana attorno a una massa puntiforme, 13 parametri
    (massa M, distanza R0, e, i, Omega, omega, tp, P + posizione e moto del sistema
    di riferimento x0, y0, vx0, vy0, vz0), ritardo di Romer, facoltativo il redshift
    relativistico (gravitazionale + Doppler trasverso);
  - adattamento ai minimi quadrati (scipy), incertezze dalla matrice di covarianza,
    un giro di esclusione dei punti anomali.

Solo numpy, scipy e (per i grafici) matplotlib. Nessuna richiesta di rete senza tempo massimo.
(c) 2026 Edoardo Battistel
"""

import csv
import io
import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

VERSIONE = "1.8"
FIRMA = "© 2026 Edoardo Battistel"
UA = "BucoNero/1.8 (programma personale; Python urllib)"
TEMPO_MAX = 60

SPECCHI = ["https://vizier.cfa.harvard.edu/viz-bin/asu-tsv",     # raggiungibile da casa
           "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"]
TABELLE = {
    "gillessen2017_table5": "J/ApJ/837/30/table5",
    "gillessen2017_table3": "J/ApJ/837/30/table3",
    "chu2018": "J/ApJ/854/12",
    # 1.8: velocita' Keck delle stelle S (Chu+2023); per S0-2 = S2 le 115 di Do+2019, fino al 2018,7
    "chu2023_table4": "J/ApJ/948/94/table4",
}

# costanti
KMS_PER_MASYR_KPC = 4.740470446       # 1 mas/anno a 1 kpc = 4,74 km/s  (= 1 UA/anno)
C_KMS = 299792.458
UA_LUCE_ANNI = 499.004784 / (365.25 * 86400)   # tempo-luce di 1 UA in anni
GM_SOLE = 4 * math.pi ** 2            # UA^3/anno^2 per 1 massa solare
NACO_FATTORE = 1.42                   # Gillessen+ 2009/2017: errori NACO da moltiplicare
EPOCA_RIF = 2009.0                    # epoca di riferimento del moto del sistema

# Valori pubblicati per il confronto (M in milioni di masse solari, R0 in kpc).
# Fonte: GRAVITY Collaboration 2022, A&A 657, L12, Tabella B.1 (che riporta anche
# Gillessen+2017, Do+2019, GRAVITY 2020); GRAVITY 2019: A&A 625, L10.
LETTERATURA = [
    ("Gillessen+ 2017 (VLT, 17 stars)", 4.280, 0.100, 8.320, 0.070),
    ("GRAVITY 2019 (S2)", 4.152, 0.014, 8.178, 0.013),
    ("Do+ 2019 (Keck, S2)", 3.975, 0.058, 7.959, 0.059),
    ("GRAVITY 2020 (S2)", 4.261, 0.012, 8.247, 0.009),
    ("GRAVITY 2022 (4 stars)", 4.297, 0.012, 8.277, 0.009),
]

NOMI_PARAMETRI = ["M", "R0", "e", "i", "Omega", "omega", "tp", "P", "x0", "y0", "vx0", "vy0", "vz0"]
UNITA = {"fSP": "(1 = GR)", "M": "1e6 Msun", "R0": "kpc", "e": "", "i": "deg", "Omega": "deg", "omega": "deg",
         "tp": "yr", "P": "yr", "x0": "mas", "y0": "mas", "vx0": "mas/yr", "vy0": "mas/yr",
         "vz0": "km/s", "a": "arcsec", "rp": "AU", "vp": "km/s"}


def cartella_dati():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    p = Path(base) / "buco_nero"
    p.mkdir(parents=True, exist_ok=True)
    return p


# =============================================================================
# DATI
# =============================================================================
def leggi_tsv(testo):
    """Prima tabella di una risposta asu-tsv: (intestazione, righe come dizionari)."""
    intest, righe, fase = None, [], 0
    for r in testo.splitlines():
        if r.startswith("#"):
            if intest and righe:
                break
            continue
        if not r.strip():
            if intest and righe:
                break
            continue
        if intest is None:
            intest, fase = [c.strip() for c in r.split("\t")], 1
        elif fase in (1, 2) and set(r.replace("\t", "").strip()) <= set("-"):
            fase = 3
        elif fase == 1:
            fase = 2
        elif fase == 3:
            v = r.split("\t")
            righe.append({k: (v[i].strip() if i < len(v) else "") for i, k in enumerate(intest)})
    if not righe:
        raise ValueError("nessuna riga di dati nella tabella")
    return intest, righe


def scarica_tabella(nome, cartelle_extra=(), forza=False, log=print):
    """Testo TSV della tabella `nome`: cache -> rete (Harvard, poi CDS) -> copie incluse.
    Restituisce (testo, provenienza)."""
    cache = cartella_dati() / f"{nome}.tsv"
    if cache.exists() and not forza:
        return cache.read_text(encoding="utf-8"), "cached copy"
    errori = []
    q = {"-source": TABELLE[nome], "-out": "**", "-out.max": "unlimited", "-oc.form": "d"}
    for s in SPECCHI:
        url = s + "?" + urllib.parse.urlencode(q)
        try:
            t0 = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TEMPO_MAX) as r:
                testo = r.read().decode("utf-8", "replace")
            leggi_tsv(testo)
            cache.write_text(testo, encoding="utf-8")
            host = urllib.parse.urlparse(s).hostname
            log(f"{nome}: scaricata da {host} in {time.time() - t0:.1f} s")
            return testo, f"downloaded from {host}"
        except Exception as e:  # noqa: BLE001 - rete, certificato, tempo scaduto, risposta vuota
            errori.append(f"{urllib.parse.urlparse(s).hostname}: {type(e).__name__} {str(e)[:80]}")
    for c in list(cartelle_extra) + [Path(__file__).resolve().parent / "dati"]:
        p = Path(c) / f"{nome}.tsv"
        if p.exists():
            log(f"{nome}: rete non disponibile ({'; '.join(errori)}), uso la copia {p}")
            return p.read_text(encoding="utf-8"), "copy shipped with the program"
    raise RuntimeError(f"{nome}: impossibile scaricarla ({'; '.join(errori)}) e nessuna copia locale")


def _num(s):
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


@dataclass
class Dati:
    stella: str
    # astrometria
    ta: np.ndarray            # anni
    ra: np.ndarray            # mas (offset in AR verso est)
    dec: np.ndarray           # mas
    era: np.ndarray
    edec: np.ndarray
    strum_a: list
    # velocita' radiali
    tv: np.ndarray
    rv: np.ndarray            # km/s
    erv: np.ndarray
    strum_v: list
    fonti: list = field(default_factory=list)

    @property
    def n_a(self):
        return len(self.ta)

    @property
    def n_v(self):
        return len(self.tv)


def carica_dati(stella="S2", con_chu=False, scala_naco=True, cartelle_extra=(), forza=False, log=print,
                con_keck2018=False):
    testo, prov = scarica_tabella("gillessen2017_table5", cartelle_extra, forza, log)
    _, righe = leggi_tsv(testo)
    k = stella
    if f"oRA-{k}" not in righe[0]:
        raise ValueError(f"la stella {k} non e' nella tabella di Gillessen 2017")
    ta, ra, dec, era, edec, sa = [], [], [], [], [], []
    tv, rv, erv, sv = [], [], [], []
    for r in righe:
        t = _num(r.get("Date"))
        if t is None:
            continue
        x, y, ex, ey = (_num(r.get(c)) for c in (f"oRA-{k}", f"oDE-{k}", f"e_oRA-{k}", f"e_oDE-{k}"))
        strum = r.get("Inst", "")
        if None not in (x, y, ex, ey) and ex > 0 and ey > 0:
            f = NACO_FATTORE if (scala_naco and strum == "VLT") else 1.0
            ta.append(t); ra.append(x); dec.append(y); era.append(ex * f); edec.append(ey * f)
            sa.append({"VLT": "NACO/VLT", "NTT": "SHARP/NTT"}.get(strum, strum))
        v, ev = _num(r.get(f"RV-{k}")), _num(r.get(f"e_RV-{k}"))
        if v is not None and ev:
            tv.append(t); rv.append(v); erv.append(ev)
            sv.append({"VLT": "SINFONI/VLT", "Keck": "NIRC2/Keck"}.get(strum, strum))
    fonti = [f"Gillessen et al. 2017, ApJ 837, 30 (VizieR J/ApJ/837/30, {prov})"]
    if con_chu and stella == "S2":
        testo, prov = scarica_tabella("chu2018", cartelle_extra, forza, log)
        _, righe = leggi_tsv(testo)
        n0 = len(tv)
        for r in righe:
            t, v, ev = _num(r.get("Epoch")), _num(r.get("RVlsr")), _num(r.get("e_RVel"))
            if None in (t, v, ev) or ev <= 0:
                continue
            # le misure Keck gia' presenti in Gillessen 2017 (stessa data) non si contano due volte
            if any(abs(t - t2) < 0.004 and s2 == "NIRC2/Keck" for t2, s2 in zip(tv[:n0], sv[:n0])):
                continue
            tv.append(t); rv.append(v); erv.append(ev); sv.append("Keck (Chu+2018)")
        fonti.append(f"Chu et al. 2018, ApJ 854, 12 (VizieR J/ApJ/854/12, {prov})")
    if con_keck2018 and stella == "S2":
        # velocita' di Do+2019 (Keck, Gemini, Subaru) dalla tabella 4 di Chu+2023: si prendono solo quelle
        # con riferimento «Do19» (le «Gillessen17» sono le VLT gia' presenti); niente doppioni con Chu 2018
        testo, prov = scarica_tabella("chu2023_table4", cartelle_extra, forza, log)
        _, righe = leggi_tsv(testo)
        n0 = len(tv)
        for r in righe:
            if (r.get("Star") or "").strip() != "S0-2" or (r.get("r_RV") or "").strip() != "Do19":
                continue
            t, v, ev = _num(r.get("Year")), _num(r.get("RV")), _num(r.get("e_RV"))
            if None in (t, v, ev) or ev <= 0:
                continue
            if any(abs(t - t2) < 0.004 and ("Keck" in s2) for t2, s2 in zip(tv[:n0], sv[:n0])):
                continue
            tv.append(t); rv.append(v); erv.append(ev); sv.append("Keck (Do+2019)")
        fonti.append(f"Do et al. 2019, Science 365, 664, via Chu et al. 2023, ApJ 948, 94 "
                     f"(VizieR J/ApJ/948/94, {prov})")
    o = np.argsort(tv)
    A = lambda x: np.asarray(x, float)
    return Dati(stella, A(ta), A(ra), A(dec), A(era), A(edec), sa,
                A(tv)[o], A(rv)[o], A(erv)[o], [sv[j] for j in o], fonti)


def orbita_pubblicata(stella="S2", cartelle_extra=(), log=print):
    """Elementi di Gillessen 2017 (table3) per la stella, o None."""
    try:
        testo, _ = scarica_tabella("gillessen2017_table3", cartelle_extra, log=log)
        _, righe = leggi_tsv(testo)
    except Exception:  # noqa: BLE001
        return None
    for r in righe:
        if r.get("Star", "").strip() == stella:
            d = {c: _num(r.get(c)) for c in ("a", "e_a", "e", "e_e", "i", "e_i", "Omega", "e_Omega",
                                              "w", "e_w", "Tp", "e_Tp", "Per", "e_Per", "Kmag")}
            return d
    return None


# =============================================================================
# MODELLO
# =============================================================================
def anomalia_eccentrica(Mm, e):
    """Risolve M = E - e sin E (Newton), vettoriale."""
    Mm = np.mod(Mm + np.pi, 2 * np.pi) - np.pi
    E = Mm + np.sign(Mm) * 0.85 * e if e > 0.8 else Mm + e * np.sin(Mm)
    for _ in range(40):
        f = E - e * np.sin(E) - Mm
        d = f / (1 - e * np.cos(E))
        E = E - d
        if np.max(np.abs(d)) < 1e-13:
            break
    return E


def vettori_orbita(p):
    """Versori P e Q del piano dell'orbita nel sistema (nord, est, lontano dall'osservatore)."""
    i, O, w = np.radians(p["i"]), np.radians(p["Omega"]), np.radians(p["omega"])
    P = np.array([np.cos(w) * np.cos(O) - np.sin(w) * np.sin(O) * np.cos(i),
                  np.cos(w) * np.sin(O) + np.sin(w) * np.cos(O) * np.cos(i),
                  np.sin(w) * np.sin(i)])
    Q = np.array([-np.sin(w) * np.cos(O) - np.cos(w) * np.sin(O) * np.cos(i),
                  -np.sin(w) * np.sin(O) + np.cos(w) * np.cos(O) * np.cos(i),
                  np.cos(w) * np.sin(i)])
    return P, Q


def semiasse_ua(p):
    return (p["M"] * 1e6 * p["P"] ** 2) ** (1 / 3)


def stato(p, t):
    """Posizione [UA] e velocita' [UA/anno] della stella al tempo di emissione t:
    componenti (nord, est, z) con z verso la direzione opposta all'osservatore."""
    t = np.atleast_1d(np.asarray(t, float))
    a = semiasse_ua(p)
    e = p["e"]
    n = 2 * np.pi / p["P"]
    E = anomalia_eccentrica(n * (t - p["tp"]), e)
    cE, sE = np.cos(E), np.sin(E)
    q = np.sqrt(1 - e * e)
    X, Y = a * (cE - e), a * q * sE
    fatt = n * a / (1 - e * cE)
    VX, VY = -fatt * sE, fatt * q * cE
    f = p.get("fSP", 0.0) or 0.0
    if f == 0.0:
        P, Q = vettori_orbita(p)
        pos = np.outer(X, P) + np.outer(Y, Q)
        vel = np.outer(VX, P) + np.outer(VY, Q)
        return pos, vel
    # precessione di Schwarzschild (media, approssimazione lineare nel tempo):
    # omega cresce di f * 6 pi GM / (c^2 a (1 - e^2)) a ogni orbita
    dw = f * precessione_gr(p) * (t - p["tp"]) / p["P"]          # radianti
    i, O = np.radians(p["i"]), np.radians(p["Omega"])
    w = np.radians(p["omega"]) + dw
    cw, sw, cO, sO, ci, si = np.cos(w), np.sin(w), np.cos(O), np.sin(O), np.cos(i), np.sin(i)
    P = np.stack([cw * cO - sw * sO * ci, cw * sO + sw * cO * ci, sw * si], axis=1)
    Q = np.stack([-sw * cO - cw * sO * ci, -sw * sO + cw * cO * ci, cw * si], axis=1)
    pos = X[:, None] * P + Y[:, None] * Q
    vel = VX[:, None] * P + VY[:, None] * Q
    return pos, vel


def precessione_gr(p):
    """Avanzamento del pericentro per orbita previsto dalla relativita' generale [radianti]."""
    a = semiasse_ua(p)
    c_uaa = C_KMS / KMS_PER_MASYR_KPC
    return 6 * math.pi * GM_SOLE * p["M"] * 1e6 / (c_uaa ** 2 * a * (1 - p["e"] ** 2))


def tempo_emissione(p, t_oss, romer=True):
    """Ritardo di Romer: la luce che vediamo a t_oss e' partita a t_em = t_oss - z/c."""
    t_oss = np.atleast_1d(np.asarray(t_oss, float))
    if not romer:
        return t_oss
    t = t_oss.copy()
    for _ in range(3):
        pos, _ = stato(p, t)
        t = t_oss - pos[:, 2] * UA_LUCE_ANNI
    return t


def modello_astrometria(p, t, romer=True):
    """(AR, Dec) in mas rispetto a Sgr A* come le misura la tabella (moto del sistema incluso)."""
    pos, _ = stato(p, tempo_emissione(p, t, romer))
    s = 1.0 / p["R0"]             # UA -> mas a R0 kpc
    dt = np.atleast_1d(t) - EPOCA_RIF
    ra = pos[:, 1] * s + p["x0"] + p["vx0"] * dt
    dec = pos[:, 0] * s + p["y0"] + p["vy0"] * dt
    return ra, dec


def modello_velocita(p, t, romer=True, relativita=False):
    """Velocita' radiale [km/s] (positiva = si allontana)."""
    tem = tempo_emissione(p, t, romer)
    pos, vel = stato(p, tem)
    vz = vel[:, 2] * KMS_PER_MASYR_KPC
    if romer:
        # le date in arrivo sono compresse dal ritardo: v_oss = v / (1 + v/c) circa; trascurabile
        pass
    if relativita:
        # relativita' = True/1 (relativita' generale) oppure un numero: il fattore del redshift
        # (Upsilon di Do+2019, f di GRAVITY 2018; 0 = Newton) per il profilo di misura_redshift
        r = np.linalg.norm(pos, axis=1)
        v2 = np.sum(vel ** 2, axis=1) * KMS_PER_MASYR_KPC ** 2
        gm_r = GM_SOLE * p["M"] * 1e6 / r * KMS_PER_MASYR_KPC ** 2
        vz = vz + float(relativita) * (v2 / 2 + gm_r) / C_KMS
    return vz + p["vz0"]


def correzione_relativistica(p, t, romer=True):
    """Solo la parte relativistica (redshift gravitazionale + Doppler trasverso) in km/s."""
    pos, vel = stato(p, tempo_emissione(p, t, romer))
    r = np.linalg.norm(pos, axis=1)
    v2 = np.sum(vel ** 2, axis=1) * KMS_PER_MASYR_KPC ** 2
    return (v2 / 2 + GM_SOLE * p["M"] * 1e6 / r * KMS_PER_MASYR_KPC ** 2) / C_KMS


# =============================================================================
# ADATTAMENTO
# =============================================================================
@dataclass
class Opzioni:
    stella: str = "S2"
    con_chu: bool = False
    con_keck2018: bool = False    # 1.8: velocita' Keck di Do+2019 fino al 2018,7 (solo S2)
    scala_naco: bool = True
    romer: bool = True
    relativita: bool = False
    precessione: bool = False  # fattore di Schwarzschild f_SP libero (1 = relativita' generale)
    escludi_anomali: bool = True
    soglia_sigma: float = 4.0
    # priori deboli sul sistema di riferimento (scelta del programma, piu' larghi
    # delle incertezze di Gillessen+2017): posizione 0 +- 1 mas, moto 0 +- 0,1 mas/anno
    priore_pos: float = 1.0
    priore_vel: float = 0.1
    priore_vz: float = 0.0     # 0 = vz0 libero
    fissa_R0: float = 0.0      # > 0: distanza tenuta fissa (controllo della massa di una sola stella)
    stelle: tuple = ()         # piu' di una stella: adattamento insieme (adatta_multi)


@dataclass
class Risultato:
    stella: str
    p: dict
    err: dict
    cov: np.ndarray
    chi2: float
    dof: int
    n_a: int
    n_v: int
    esclusi_a: list
    esclusi_v: list
    opzioni: Opzioni
    dati: Dati
    pubblicata: dict = None
    derivati: dict = None
    corr_M_R0: float = 0.0

    @property
    def chi2_rid(self):
        return self.chi2 / max(self.dof, 1)


NOMI_CON_F = NOMI_PARAMETRI + ["fSP"]


def _da_vettore(x):
    return dict(zip(NOMI_CON_F, x))


def _limiti(n):
    if n == 13:
        return LIMITI
    return (LIMITI[0] + [-30.0], LIMITI[1] + [30.0])


def _residui(x, d, opz, ma, mv):
    p = _da_vettore(x)
    ra, dec = modello_astrometria(p, d.ta[ma], opz.romer)
    v = modello_velocita(p, d.tv[mv], opz.romer, opz.relativita)
    r = [(d.ra[ma] - ra) / d.era[ma], (d.dec[ma] - dec) / d.edec[ma], (d.rv[mv] - v) / d.erv[mv]]
    pri = []
    if opz.priore_pos > 0:
        pri += [p["x0"] / opz.priore_pos, p["y0"] / opz.priore_pos]
    if opz.priore_vel > 0:
        pri += [p["vx0"] / opz.priore_vel, p["vy0"] / opz.priore_vel]
    if opz.priore_vz > 0:
        pri += [p["vz0"] / opz.priore_vz]
    if opz.fissa_R0 > 0:
        pri += [(p["R0"] - opz.fissa_R0) / 1e-6]
    return np.concatenate(r + [np.array(pri)])


def partenza(pub, d):
    """Valori iniziali: orbita pubblicata (se c'e') con R0 = 8,3 kpc."""
    if pub and None not in (pub["a"], pub["e"], pub["i"], pub["Omega"], pub["w"], pub["Tp"], pub["Per"]):
        R0 = 8.3
        M = (pub["a"] * R0 * 1000) ** 3 / pub["Per"] ** 2 / 1e6
        return [M, R0, pub["e"], pub["i"], pub["Omega"], pub["w"], pub["Tp"], pub["Per"], 0, 0, 0, 0, 0]
    return [4.3, 8.3, 0.88, 134, 227, 66, 2002.3, 16.0, 0, 0, 0, 0, 0]


LIMITI = ([0.5, 3.0, 0.0, 0.0, -720, -720, 1900, 1.0, -50, -50, -5, -5, -500],
          [50, 20.0, 0.999, 180, 720, 720, 2100, 500, 50, 50, 5, 5, 500])


def adatta(d, opz, pub=None, x0=None, log=print):
    ma = np.ones(d.n_a, bool)
    mv = np.ones(d.n_v, bool)
    x = list(x0 if x0 is not None else partenza(pub, d))[:13]
    if opz.precessione:
        x.append(1.0)
    x = np.array(x, float)
    esclusi_a, esclusi_v = [], []
    for giro in range(2 if opz.escludi_anomali else 1):
        sol = least_squares(_residui, x, args=(d, opz, ma, mv), bounds=_limiti(len(x)), method="trf",
                            x_scale="jac", xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=4000)
        x = sol.x
        if not opz.escludi_anomali or giro == 1:
            break
        p = _da_vettore(x)
        ra, dec = modello_astrometria(p, d.ta, opz.romer)
        v = modello_velocita(p, d.tv, opz.romer, opz.relativita)
        ra_n = np.hypot((d.ra - ra) / d.era, (d.dec - dec) / d.edec) / math.sqrt(2)
        v_n = np.abs(d.rv - v) / d.erv
        nuovi_a = ra_n > opz.soglia_sigma
        nuovi_v = v_n > opz.soglia_sigma
        if not nuovi_a.any() and not nuovi_v.any():
            break
        ma &= ~nuovi_a
        mv &= ~nuovi_v
        esclusi_a = [(float(d.ta[j]), d.strum_a[j], float(ra_n[j])) for j in np.where(nuovi_a)[0]]
        esclusi_v = [(float(d.tv[j]), d.strum_v[j], float(v_n[j])) for j in np.where(nuovi_v)[0]]
        log(f"esclusi {len(esclusi_a)} punti astrometrici e {len(esclusi_v)} velocita' oltre "
            f"{opz.soglia_sigma:g} sigma; nuovo adattamento")
    r = sol.fun
    n_pri = len(r) - 2 * ma.sum() - mv.sum()
    chi2 = float(np.sum(r[: len(r) - n_pri] ** 2))
    dof = int(2 * ma.sum() + mv.sum() - len(x))
    J = sol.jac
    try:
        cov = np.linalg.inv(J.T @ J)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(J.T @ J)
    p = _da_vettore(x)
    p["Omega"] %= 360
    p["omega"] %= 360
    err = dict(zip(NOMI_CON_F, np.sqrt(np.clip(np.diag(cov), 0, None))))
    res = Risultato(d.stella, p, err, cov, chi2, dof, int(ma.sum()), int(mv.sum()),
                    esclusi_a, esclusi_v, opz, d, pub)
    res.mask_a, res.mask_v = ma, mv
    res.x = x.copy()
    res.cov_tutta = cov
    res.funzione = lambda v, d=d, opz=opz, ma=ma.copy(), mv=mv.copy(): _residui(v, d, opz, ma, mv)
    res.limiti = _limiti(len(x))
    iM, iR = NOMI_PARAMETRI.index("M"), NOMI_PARAMETRI.index("R0")
    res.corr_M_R0 = float(cov[iM, iR] / math.sqrt(cov[iM, iM] * cov[iR, iR]))
    res.derivati = derivati(p, cov)
    return res


def _propaga(f, x, cov, h=1e-6):
    g = np.zeros(len(x))
    for k in range(len(x)):
        dx = np.zeros(len(x))
        dx[k] = h * max(1.0, abs(x[k]))
        g[k] = (f(x + dx) - f(x - dx)) / (2 * dx[k])
    return float(np.sqrt(max(g @ cov @ g, 0)))


def derivati(p, cov):
    """Grandezze derivate con le incertezze propagate."""
    x = np.array([p.get(k, 1.0) for k in NOMI_CON_F[:len(cov)]])

    def a_sec(v):
        q = _da_vettore(v)
        return semiasse_ua(q) / q["R0"] / 1000

    def rp(v):
        q = _da_vettore(v)
        return semiasse_ua(q) * (1 - q["e"])

    def vp(v):
        q = _da_vettore(v)
        a = semiasse_ua(q)
        return math.sqrt(GM_SOLE * q["M"] * 1e6 / a * (1 + q["e"]) / (1 - q["e"])) * KMS_PER_MASYR_KPC

    def ra_ua(v):
        q = _da_vettore(v)
        return semiasse_ua(q) * (1 + q["e"])

    rs_ua = 2 * GM_SOLE * p["M"] * 1e6 / (C_KMS / KMS_PER_MASYR_KPC) ** 2   # raggio di Schwarzschild
    out = {
        "a": (a_sec(x), _propaga(a_sec, x, cov)),
        "rp": (rp(x), _propaga(rp, x, cov)),
        "ra": (ra_ua(x), _propaga(ra_ua, x, cov)),
        "vp": (vp(x), _propaga(vp, x, cov)),
        "rs_ua": rs_ua,
        "rp_rs": rp(x) / rs_ua,
    }
    # passaggi al pericentro dopo i dati
    out["peri"] = [p["tp"] + k * p["P"] for k in range(1, 3)]
    out["e_peri"] = [math.hypot(_err1(cov, "tp"), k * _err1(cov, "P")) for k in range(1, 3)]
    # precessione di Schwarzschild prevista dalla relativita' generale per un'orbita
    a = semiasse_ua(p)
    dphi = 6 * math.pi * GM_SOLE * p["M"] * 1e6 / ((C_KMS / KMS_PER_MASYR_KPC) ** 2 * a * (1 - p["e"] ** 2))
    out["precessione_arcmin"] = math.degrees(dphi) * 60
    return out


def _err1(cov, nome):
    k = NOMI_PARAMETRI.index(nome)
    return math.sqrt(max(cov[k, k], 0))


def previsione_pericentro(res, quale=0):
    """Velocita' radiale massima/minima e redshift relativistico al pericentro previsto."""
    p = res.p
    tp = res.derivati["peri"][quale]
    t = np.linspace(tp - 0.6, tp + 0.6, 4801)
    v = modello_velocita(p, t, res.opzioni.romer, False)
    g = correzione_relativistica(p, t, res.opzioni.romer)
    j = int(np.argmin(np.abs(t - tp)))
    return {"tp": tp, "v_max": float(v.max()), "t_vmax": float(t[np.argmax(v)]),
            "v_min": float(v.min()), "t_vmin": float(t[np.argmin(v)]),
            "redshift_gr": float(g.max()), "redshift_gr_tp": float(g[j])}


def anno_in_data(anno):
    import datetime as dt
    y = int(math.floor(anno))
    inizio = dt.datetime(y, 1, 1)
    fine = dt.datetime(y + 1, 1, 1)
    return (inizio + (fine - inizio) * (anno - y)).strftime("%Y-%m-%d")


# =============================================================================
# PIU' STELLE INSIEME
# =============================================================================
GLOBALI = ["M", "R0", "x0", "y0", "vx0", "vy0", "vz0"]
ELEMENTI = ["e", "i", "Omega", "omega", "tp", "P"]
# posizione nel vettore di una stella (ordine di NOMI_PARAMETRI) di ogni globale/elemento
_POS = {k: NOMI_PARAMETRI.index(k) for k in NOMI_PARAMETRI}


_POS["fSP"] = 13


def globali(opz):
    return GLOBALI + (["fSP"] if opz.precessione else [])


def _indici(n_stelle, glob=GLOBALI):
    """Per ogni stella, gli indici nel vettore comune dei suoi parametri (ordine NOMI_CON_F)."""
    out = []
    for k in range(n_stelle):
        idx = [0] * (13 + (1 if "fSP" in glob else 0))
        for j, g in enumerate(glob):
            idx[_POS[g]] = j
        for j, el in enumerate(ELEMENTI):
            idx[_POS[el]] = len(glob) + 6 * k + j
        out.append(idx)
    return out


def _residui_multi(x, lista, opz, maschere, indici):
    r = []
    for d, (ma, mv), idx in zip(lista, maschere, indici):
        p = _da_vettore(x[idx])
        ra, dec = modello_astrometria(p, d.ta[ma], opz.romer)
        v = modello_velocita(p, d.tv[mv], opz.romer, opz.relativita)
        r += [(d.ra[ma] - ra) / d.era[ma], (d.dec[ma] - dec) / d.edec[ma], (d.rv[mv] - v) / d.erv[mv]]
    g = dict(zip(GLOBALI, x[:len(GLOBALI)]))   # fSP (se c'e') viene dopo: nessun priore
    pri = []
    if opz.priore_pos > 0:
        pri += [g["x0"] / opz.priore_pos, g["y0"] / opz.priore_pos]
    if opz.priore_vel > 0:
        pri += [g["vx0"] / opz.priore_vel, g["vy0"] / opz.priore_vel]
    if opz.priore_vz > 0:
        pri += [g["vz0"] / opz.priore_vz]
    return np.concatenate(r + [np.array(pri)])


def adatta_multi(lista, opz, pubs, log=print):
    """Adatta insieme piu' stelle: M, R0 e sistema di riferimento in comune, 6 elementi per stella.
    Restituisce il Risultato della prima stella con .sub = {stella: Risultato} e .stelle."""
    n = len(lista)
    glob = globali(opz)
    indici = _indici(n, glob)
    lo1, hi1 = _limiti(14)
    start = []
    for k, (d, pub) in enumerate(zip(lista, pubs)):
        x = list(partenza(pub, d)) + [1.0]
        if k == 0:
            start += [x[_POS[g]] for g in glob]
        start += [x[_POS[el]] for el in ELEMENTI]
    lo = [lo1[_POS[g]] for g in glob] + [lo1[_POS[el]] for _ in range(n) for el in ELEMENTI]
    hi = [hi1[_POS[g]] for g in glob] + [hi1[_POS[el]] for _ in range(n) for el in ELEMENTI]
    x = np.clip(np.array(start, float), np.array(lo) + 1e-9, np.array(hi) - 1e-9)
    maschere = [(np.ones(d.n_a, bool), np.ones(d.n_v, bool)) for d in lista]
    esclusi = {d.stella: ([], []) for d in lista}
    for giro in range(2 if opz.escludi_anomali else 1):
        sol = least_squares(_residui_multi, x, args=(lista, opz, maschere, indici), bounds=(lo, hi),
                            method="trf", x_scale="jac", xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=8000)
        x = sol.x
        if not opz.escludi_anomali or giro == 1:
            break
        nuovi = False
        for k, (d, idx) in enumerate(zip(lista, indici)):
            p = _da_vettore(x[idx])
            ra, dec = modello_astrometria(p, d.ta, opz.romer)
            v = modello_velocita(p, d.tv, opz.romer, opz.relativita)
            ra_n = np.hypot((d.ra - ra) / d.era, (d.dec - dec) / d.edec) / math.sqrt(2)
            v_n = np.abs(d.rv - v) / d.erv
            na, nv = ra_n > opz.soglia_sigma, v_n > opz.soglia_sigma
            if na.any() or nv.any():
                nuovi = True
                maschere[k] = (maschere[k][0] & ~na, maschere[k][1] & ~nv)
                esclusi[d.stella] = ([(float(d.ta[j]), d.strum_a[j], float(ra_n[j])) for j in np.where(na)[0]],
                                     [(float(d.tv[j]), d.strum_v[j], float(v_n[j])) for j in np.where(nv)[0]])
        if not nuovi:
            break
        log("esclusi alcuni punti anomali; nuovo adattamento")
    r = sol.fun
    n_dati = sum(int(2 * ma.sum() + mv.sum()) for ma, mv in maschere)
    chi2 = float(np.sum(r[:n_dati] ** 2))
    dof = n_dati - len(x)
    J = sol.jac
    try:
        cov = np.linalg.inv(J.T @ J)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(J.T @ J)
    sub = {}
    for k, (d, pub, idx) in enumerate(zip(lista, pubs, indici)):
        p = _da_vettore(x[idx])
        p["Omega"] %= 360
        p["omega"] %= 360
        c = cov[np.ix_(idx, idx)]
        err = dict(zip(NOMI_CON_F, np.sqrt(np.clip(np.diag(c), 0, None))))
        ma, mv = maschere[k]
        # chi2 della sola stella
        ra, dec = modello_astrometria(p, d.ta[ma], opz.romer)
        v = modello_velocita(p, d.tv[mv], opz.romer, opz.relativita)
        c2 = float(np.sum(((d.ra[ma] - ra) / d.era[ma]) ** 2) + np.sum(((d.dec[ma] - dec) / d.edec[ma]) ** 2)
                   + np.sum(((d.rv[mv] - v) / d.erv[mv]) ** 2))
        rs = Risultato(d.stella, p, err, c, c2, int(2 * ma.sum() + mv.sum() - 6), int(ma.sum()), int(mv.sum()),
                       esclusi[d.stella][0], esclusi[d.stella][1], opz, d, pub)
        rs.mask_a, rs.mask_v = ma, mv
        rs.corr_M_R0 = float(c[0, 1] / math.sqrt(c[0, 0] * c[1, 1]))
        rs.derivati = derivati(p, c)
        sub[d.stella] = rs
    res = sub[lista[0].stella]
    capo = Risultato(res.stella, dict(res.p), dict(res.err), res.cov, chi2, dof,
                     sum(s.n_a for s in sub.values()), sum(s.n_v for s in sub.values()),
                     res.esclusi_a, res.esclusi_v, opz, res.dati, res.pubblicata)
    capo.mask_a, capo.mask_v = res.mask_a, res.mask_v
    capo.corr_M_R0, capo.derivati = res.corr_M_R0, res.derivati
    capo.sub = sub
    capo.stelle = [d.stella for d in lista]
    capo.cov_tutta = cov
    capo.x = x
    capo.funzione = lambda v: _residui_multi(v, lista, opz, [(a.copy(), b.copy()) for a, b in maschere], indici)
    capo.limiti = (lo, hi)
    capo.nomi_x = glob + [f"{el}_{d.stella}" for d in lista for el in ELEMENTI]
    return capo


def controllo_stelle(res, log=print):
    """Ogni stella da sola, con la distanza fissata a quella comune: la sua massa.
    Restituisce {stella: (M, errore)} e il chi2 della coerenza con la massa comune."""
    out = {}
    for s, rs in res.sub.items():
        opz = Opzioni(**{**res.opzioni.__dict__, "fissa_R0": res.p["R0"], "stelle": ()})
        try:
            x0 = [rs.p[k] for k in NOMI_PARAMETRI]
            r1 = adatta(rs.dati, opz, rs.pubblicata, x0=x0, log=lambda *a: None)
            out[s] = (r1.p["M"], r1.err["M"])
        except Exception as e:  # noqa: BLE001
            log(f"controllo di {s} non riuscito: {e}")
    M = res.p["M"]
    chi2 = sum(((m_ - M) / e_) ** 2 for m_, e_ in out.values() if e_ > 0)
    return out, chi2


def calcola(opz, cartelle_extra=(), forza=False, log=print):
    """Una stella (adatta) o piu' stelle insieme (adatta_multi), secondo opz.stelle."""
    stelle = list(opz.stelle) or [opz.stella]
    lista, pubs = [], []
    for s in stelle:
        lista.append(carica_dati(s, opz.con_chu and s == "S2", opz.scala_naco, cartelle_extra, forza, log,
                                 con_keck2018=opz.con_keck2018 and s == "S2"))
        pubs.append(orbita_pubblicata(s, cartelle_extra, log))
    if len(lista) == 1:
        r = adatta(lista[0], opz, pubs[0], log=log)
        r.sub = {r.stella: r}
        r.stelle = [r.stella]
        r.controllo = None
    else:
        r = adatta_multi(lista, opz, pubs, log)
        r.controllo = controllo_stelle(r, log)
    try:                                   # verifica con l'orbita 1PN integrata (1.6), meno di 1 s
        r.verifica_1pn = verifica_1pn(r)
    except Exception as e:  # noqa: BLE001
        r.verifica_1pn = None
        log(f"Verifica 1PN non riuscita: {type(e).__name__}: {e}")
    return r


# =============================================================================
# MISURA DEL REDSHIFT RELATIVISTICO (1.8)
# =============================================================================
GRIGLIA_REDSHIFT = [-0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]


def misura_redshift(opz, cartelle_extra=(), log=print, avanzamento=None, griglia=GRIGLIA_REDSHIFT):
    """Fattore del redshift relativistico (Upsilon: 1 = relativita' generale, 0 = Newton) dal profilo del chi2:
    si rifa' l'adattamento con il fattore fisso a ogni valore della griglia (tutti gli altri parametri liberi),
    poi una parabola attorno al minimo da' il valore migliore e l'errore (Delta chi2 = 1).
    Stessi dati e opzioni del calcolo; con una stella ~1 s per punto, con tre ~5 s."""
    stelle = list(opz.stelle) or [opz.stella]
    lista, pubs = [], []
    for s in stelle:
        lista.append(carica_dati(s, opz.con_chu and s == "S2", opz.scala_naco, cartelle_extra, False, log,
                                 con_keck2018=opz.con_keck2018 and s == "S2"))
        pubs.append(orbita_pubblicata(s, cartelle_extra, log))
    chi2 = []
    for k, u in enumerate(griglia):
        o = Opzioni(**{**opz.__dict__, "relativita": float(u)})
        r = adatta(lista[0], o, pubs[0], log=lambda *a: None) if len(lista) == 1 else \
            adatta_multi(lista, o, pubs, log=lambda *a: None)
        chi2.append(r.chi2)
        if avanzamento:
            avanzamento((k + 1) / len(griglia))
    U, C = np.array(griglia, float), np.array(chi2)
    k0 = int(np.argmin(C))
    vicini = np.abs(U - U[k0]) <= 0.76
    a, b, _ = np.polyfit(U[vicini], C[vicini], 2)
    if a <= 0:
        raise RuntimeError("profilo del redshift senza minimo")
    u0 = -b / (2 * a)
    err = 1 / math.sqrt(a)
    n_dopo = sum(int(np.sum(d.tv > 2016.6)) for d in lista)
    return {"upsilon": float(u0), "errore": float(err), "griglia": U.tolist(), "chi2": C.tolist(),
            "sigma_da_newton": float(u0 / err), "sigma_da_einstein": float((u0 - 1) / err),
            "n_rv_dopo_2016": n_dopo}


# =============================================================================
# VERIFICA CON L'ORBITA 1PN INTEGRATA (1.6)
# =============================================================================
def integra_1pn(p, t, fattore=1.0):
    """Posizioni e velocita' [UA, UA/anno] ai tempi t integrando le equazioni 1PN, partendo dallo
    stato kepleriano osculante al pericentro tp (fattore 0 = Newton, 1 = relativita' generale)."""
    from scipy.integrate import solve_ivp
    gm = GM_SOLE * p["M"] * 1e6
    c = C_KMS / KMS_PER_MASYR_KPC
    q = dict(p)
    q["fSP"] = 0.0
    x0, v0 = stato(q, [p["tp"]])
    y0 = np.concatenate([x0[0], v0[0]])

    def f(_, y):
        pos, vel = y[:3], y[3:]
        r = np.linalg.norm(pos)
        v2 = vel @ vel
        acc = -gm * pos / r ** 3 + fattore * gm / (c * c * r ** 3) * ((4 * gm / r - v2) * pos + 4 * (pos @ vel) * vel)
        return np.concatenate([vel, acc])

    t = np.atleast_1d(np.asarray(t, float))
    out = np.zeros((len(t), 6))
    for verso in (t >= p["tp"], t < p["tp"]):
        tt = t[verso]
        if not tt.size:
            continue
        ordine = np.argsort(tt) if tt[0] >= p["tp"] else np.argsort(-tt)
        fine = tt[ordine][-1]
        sol = solve_ivp(f, (p["tp"], fine), y0, method="DOP853", t_eval=tt[ordine], rtol=1e-11, atol=1e-9)
        if not sol.success:
            raise RuntimeError("integrazione 1PN non riuscita: " + sol.message)
        idx = np.nonzero(verso)[0][ordine]
        out[idx] = sol.y.T
    return out[:, :3], out[:, 3:]


def verifica_1pn(res):
    """Quanto la precessione media lineare (il modello del programma con f_SP = 1) si allontana da un'orbita
    1PN integrata davvero, nell'intervallo dei dati. Per ogni stella: si integra l'orbita 1PN dai parametri
    adattati e si riadattano a quella i 6 elementi del modello lineare (M e R0 fissi): il residuo e' l'errore
    dell'approssimazione. Si confronta con l'errore tipico delle misure e con l'effetto relativistico intero
    (differenza tra Newton e 1PN). Restituisce {stella: dizionario}."""
    from scipy.optimize import least_squares
    out = {}
    sub = getattr(res, "sub", None) or {res.stella: res}
    for nome, rs in sub.items():
        d = rs.dati
        p = dict(rs.p)
        t = np.unique(np.concatenate([d.ta, d.tv]))
        t = np.linspace(t.min(), t.max(), 4000) if t.size else t
        pos_pn, vel_pn = integra_1pn(p, t, 1.0)
        s = 1.0 / p["R0"]

        def scarto(f_sp):
            """Il modello del programma (precessione lineare f_SP) riadattato all'orbita 1PN: scarti massimi."""
            def residui(x):
                q = dict(p)
                q.update(zip(ELEMENTI, x))
                q["fSP"] = f_sp
                pos, vel = stato(q, t)
                dpos = (pos[:, :2] - pos_pn[:, :2]).ravel() * s                  # mas
                dvel = (vel[:, 2] - vel_pn[:, 2]) * KMS_PER_MASYR_KPC / 10.0       # 10 km/s ~ 1 mas
                return np.concatenate([dpos, dvel])
            x0 = np.array([p[k] for k in ELEMENTI], float)
            sol = least_squares(residui, x0, x_scale=np.maximum(np.abs(x0) * 1e-4, 1e-6), xtol=1e-12, ftol=1e-12)
            q = dict(p)
            q.update(zip(ELEMENTI, sol.x))
            q["fSP"] = f_sp
            pos, vel = stato(q, t)
            return (float(np.linalg.norm((pos[:, :2] - pos_pn[:, :2]) * s, axis=1).max()),
                    float((np.abs(vel[:, 2] - vel_pn[:, 2]) * KMS_PER_MASYR_KPC).max()))

        d_pos, d_vel = scarto(1.0)          # approssimazione del programma contro 1PN vera
        gr_pos, gr_vel = scarto(0.0)        # Newton (riadattato) contro 1PN: quanto conta la relativita'
        err_a = float(np.median(np.hypot(d.era, d.edec) / math.sqrt(2))) if d.n_a else float("nan")
        err_v = float(np.median(d.erv)) if d.n_v else float("nan")
        out[nome] = {"diff_pos_max_mas": d_pos, "diff_vel_max_kms": d_vel,
                     "gr_pos_max_mas": gr_pos, "gr_vel_max_kms": gr_vel,
                     "errore_pos_mas": err_a, "errore_vel_kms": err_v,
                     "t_min": float(t.min()), "t_max": float(t.max())}
    return out


# =============================================================================
# MCMC (Metropolis adattivo)
# =============================================================================
def mcmc(res, n_passi=30000, seme=1, avanzamento=None, ferma=None):
    """Campiona la probabilita' a posteriori attorno all'adattamento (stessi dati, stesse
    esclusioni, stessi priori). Proposta gaussiana con la covarianza dell'adattamento,
    adattata durante il riscaldamento (primo 25 %), poi fissa. Restituisce un dizionario
    con i campioni (dopo il riscaldamento, uno ogni 10) e i percentili 16/50/84."""
    rng = np.random.default_rng(seme)
    x = np.array(res.x, float)
    d = len(x)
    lo, hi = (np.array(v, float) for v in res.limiti)
    f = res.funzione

    def logp(v):
        if np.any(v <= lo) or np.any(v >= hi):
            return -np.inf
        r = f(v)
        return -0.5 * float(r @ r)

    C = np.array(res.cov_tutta, float)
    C = 0.5 * (C + C.T) + np.eye(d) * 1e-14
    scala = 2.38 ** 2 / d
    L = np.linalg.cholesky(C * scala)
    lp = logp(x)
    # riscaldamento = primo 40 %: ogni 500 passi la scala segue l'accettazione DEGLI ULTIMI 500 passi
    # (nella 1.2-1.4 si usava quella dall'inizio: reagiva tardi, con 3 stelle restava al 5 %)
    # e la covarianza si ricalcola dalla seconda meta' dei campioni del riscaldamento
    riscaldo = int(n_passi * 0.4)
    catena, risc, acc_fin, acc_fin_tot = [], [], 0, 0
    finestra = 0
    lp_max, x_max = lp, x.copy()
    for k in range(n_passi):
        y = x + L @ rng.standard_normal(d)
        ly = logp(y)
        if np.log(rng.random()) < ly - lp:
            x, lp = y, ly
            finestra += 1
            if k >= riscaldo:
                acc_fin += 1
            if lp > lp_max:
                lp_max, x_max = lp, x.copy()
        if k < riscaldo:
            risc.append(x.copy())
            if (k + 1) % 500 == 0:
                tasso = finestra / 500
                finestra = 0
                scala *= math.exp(1.5 * (tasso - 0.234))
                Cn = C
                if len(risc) > 20 * d:
                    Cn = np.cov(np.array(risc[len(risc) // 2:]).T) + np.eye(d) * 1e-14
                try:
                    L = np.linalg.cholesky(Cn * scala)
                except np.linalg.LinAlgError:
                    L = np.linalg.cholesky(C * scala)
        elif (k - riscaldo) % 10 == 0:
            catena.append(x.copy())
        if avanzamento and k % 500 == 0:
            avanzamento(k / n_passi)
        if ferma is not None and ferma.is_set():
            break
    S = np.array(catena)
    nomi = getattr(res, "nomi_x", None) or NOMI_CON_F[:d]
    perc = {}
    for j, nome in enumerate(nomi):
        q16, q50, q84 = np.percentile(S[:, j], [16, 50, 84])
        perc[nome] = (float(q50), float(q50 - q16), float(q84 - q50))
    # lunghezza di autocorrelazione grezza di M (per dire quanti campioni indipendenti ci sono)
    m_ = S[:, 0] - S[:, 0].mean()
    ac = np.correlate(m_, m_, "full")[len(m_) - 1:]
    ac = ac / ac[0] if ac[0] > 0 else ac
    tau = 1 + 2 * float(np.sum(ac[1:np.argmax(ac < 0.05) or 1]))
    # R-hat di Gelman-Rubin sulla catena divisa in 4 pezzi (1.6): vicino a 1 = convergenza
    rhat = {}
    q = len(S) // 4
    if q >= 10:
        pezzi = S[:4 * q].reshape(4, q, -1)
        W = pezzi.var(axis=1, ddof=1).mean(axis=0)
        B = q * pezzi.mean(axis=1).var(axis=0, ddof=1)
        V = (q - 1) / q * W + B / q
        for j, nome in enumerate(nomi):
            rhat[nome] = float(np.sqrt(V[j] / W[j])) if W[j] > 0 else float("nan")
    if avanzamento:
        avanzamento(1.0)
    return {"campioni": S, "nomi": nomi, "percentili": perc, "rhat": rhat,
            "rhat_max": max(rhat.values()) if rhat else float("nan"),
            "rhat_peggiore": max(rhat, key=rhat.get) if rhat else "",
            "rhat_principali": max([rhat[k] for k in ("M", "R0", "fSP") if k in rhat] or [float("nan")]),
            "accettazione": acc_fin / max(1, n_passi - riscaldo), "n_passi": n_passi,
            "n_campioni": len(S), "indipendenti": len(S) / max(1.0, tau),
            "x_migliore": x_max, "chi2_migliore": -2 * lp_max}


# =============================================================================
# USCITE (CSV, JSON)
# =============================================================================
def tabella_risultati(res):
    righe = []
    for k in NOMI_CON_F:
        if k in res.p:
            righe.append((k, res.p[k], res.err.get(k, 0.0), UNITA.get(k, "")))
    for k in ("a", "rp", "ra", "vp"):
        v, e = res.derivati[k]
        righe.append((k, v, e, {"ra": "AU"}.get(k, UNITA.get(k, ""))))
    return righe


def salva_csv(res, cartella):
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    sub = getattr(res, "sub", None) or {res.stella: res}
    base = "_".join(sub)
    f = cartella / f"{base}_orbit_fit.csv"
    with open(f, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["star", "parameter", "value", "uncertainty_1sigma", "unit"])
        for s, rs in sub.items():
            for r in tabella_risultati(rs):
                w.writerow([s, r[0], f"{r[1]:.6g}", f"{r[2]:.3g}", r[3]])
        w.writerow([])
        w.writerow(["all", "chi2", f"{res.chi2:.2f}", "dof", res.dof])
        w.writerow(["all", "corr(M,R0)", f"{res.corr_M_R0:.3f}"])
        ctl = getattr(res, "controllo", None)
        if ctl:
            for s, (M, eM) in ctl[0].items():
                w.writerow([s, "M_alone_at_common_R0", f"{M:.6g}", f"{eM:.3g}", "1e6 Msun"])
    g = cartella / f"{base}_residuals.csv"
    with open(g, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["star", "type", "epoch_yr", "instrument", "obs1", "err1", "model1", "obs2", "err2", "model2", "used"])
        for s, rs in sub.items():
            p, d = rs.p, rs.dati
            ra, dec = modello_astrometria(p, d.ta, rs.opzioni.romer)
            v = modello_velocita(p, d.tv, rs.opzioni.romer, rs.opzioni.relativita)
            for j in range(d.n_a):
                w.writerow([s, "astrometry (RA, Dec mas)", f"{d.ta[j]:.3f}", d.strum_a[j], d.ra[j], f"{d.era[j]:.2f}",
                            f"{ra[j]:.2f}", d.dec[j], f"{d.edec[j]:.2f}", f"{dec[j]:.2f}", int(rs.mask_a[j])])
            for j in range(d.n_v):
                w.writerow([s, "radial velocity (km/s)", f"{d.tv[j]:.3f}", d.strum_v[j], d.rv[j], d.erv[j],
                            f"{v[j]:.1f}", "", "", "", int(rs.mask_v[j])])
    return [f, g]


def riassunto_json(res):
    sub = getattr(res, "sub", None) or {res.stella: res}
    o = {"version": VERSIONE, "star": res.stella, "stars": list(sub),
         "per_star": {s: {k: [rs.p[k], rs.err[k]] for k in ELEMENTI} for s, rs in sub.items()},
         "check_mass_at_common_R0": ({s: list(v) for s, v in res.controllo[0].items()}
                                     if getattr(res, "controllo", None) else None),
         "parameters": {k: [res.p[k], res.err.get(k, 0.0)] for k in NOMI_CON_F if k in res.p},
         "derived": {k: list(res.derivati[k]) for k in ("a", "rp", "ra", "vp")},
         "chi2": res.chi2, "dof": res.dof, "corr_M_R0": res.corr_M_R0,
         "n_astrometry": res.n_a, "n_rv": res.n_v,
         "excluded_astrometry": res.esclusi_a, "excluded_rv": res.esclusi_v,
         "options": {k: (list(v) if isinstance(v, tuple) else v) for k, v in res.opzioni.__dict__.items()},
         "check_1PN_integrated_orbit": getattr(res, "verifica_1pn", None),
         "redshift_factor_profile": getattr(res, "redshift", None),
         "mcmc_rhat": (getattr(res, "mcmc", None) or {}).get("rhat"),
         "sources": res.dati.fonti}
    return json.dumps(o, indent=1)


# =============================================================================
# RIGA DI COMANDO
# =============================================================================
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Massa e distanza di Sgr A* dall'orbita di una stella S")
    ap.add_argument("--stella", default="S2")
    ap.add_argument("--chu", action="store_true", help="aggiungi le velocita' Keck di Chu+2018 (solo S2)")
    ap.add_argument("--relativita", action="store_true", help="includi il redshift relativistico")
    ap.add_argument("--uscita", default="risultati_buco_nero")
    ap.add_argument("--dati", default=None, help="cartella con copie dei TSV")
    ap.add_argument("--riscarica", action="store_true")
    a = ap.parse_args(argv)
    extra = [a.dati] if a.dati else []
    d = carica_dati(a.stella, a.chu, cartelle_extra=extra, forza=a.riscarica)
    print(f"{d.stella}: {d.n_a} posizioni, {d.n_v} velocita' radiali")
    pub = orbita_pubblicata(a.stella, extra)
    opz = Opzioni(stella=a.stella, con_chu=a.chu, relativita=a.relativita)
    res = adatta(d, opz, pub)
    for k, v, e, u in tabella_risultati(res):
        print(f"  {k:6s} = {v:12.6g} +- {e:.3g} {u}")
    print(f"  chi2 = {res.chi2:.1f} per {res.dof} gradi di liberta' (ridotto {res.chi2_rid:.2f}); "
          f"corr(M,R0) = {res.corr_M_R0:.2f}")
    try:
        import grafici_bn
        file = grafici_bn.scheda(res, a.uscita)
        print("Scheda:", ", ".join(str(f) for f in file))
    except ImportError:
        pass
    print("CSV:", ", ".join(str(f) for f in salva_csv(res, a.uscita)))


if __name__ == "__main__":
    main()
