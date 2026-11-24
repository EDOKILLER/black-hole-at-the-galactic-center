"""Il buco nero al centro della Galassia - immagini di contesto (versione 1.6).

DSS2 rosso da SkyView; dalla 1.6 il vicino infrarosso a colori (2MASS J, H, Ks) arriva
direttamente da IRSA (servizio SIA delle immagini Atlas 2MASS), perche' SkyView per 2MASS e
WISE attorno al centro galattico rispondeva sempre «Exception encountered».

Il centro della Galassia a 10': in luce visibile (DSS2 rosso) e' nascosto dalla polvere,
nel vicino infrarosso (2MASS K) si vede l'ammasso di stelle attorno a Sgr A*.
Lettore FITS minimo (solo immagine primaria), senza astropy.
(c) 2026 Edoardo Battistel
"""

import gzip
import json
import math
import time
import xml.etree.ElementTree as ET
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

import motore_bn as m

SGR_A = (266.416837, -29.007810)          # AR, Dec J2000 (gradi)
SKYVIEW = "https://skyview.gsfc.nasa.gov/cgi-bin/images"
# per ogni pannello, le survey in ordine di preferenza (la prima che risponde con un FITS)
IMMAGINI = [[("DSS2 Red", "Visible light (DSS2 red)")],
            [("2MASS-K", "Near infrared (2MASS K, 2.2 µm)"),
             ("2MASS-H", "Near infrared (2MASS H, 1.6 µm)"),
             ("WISE 3.4", "Infrared (WISE, 3.4 µm)")]]
CAMPO_GRADI = 10 / 60
SIA_2MASS = "https://irsa.ipac.caltech.edu/cgi-bin/2MASS/IM/nph-im_sia"
TITOLO_2MASS = "Near infrared colour (2MASS)\nKs = red, H = green, J = blue"
PIXEL = 600


def leggi_fits(dati):
    """(immagine float, intestazione) dall'HDU primario di un file FITS."""
    if not dati.startswith(b"SIMPLE"):
        raise ValueError("non e' un file FITS (forse SkyView ha risposto con una pagina di errore)")
    intest, pos = {}, 0
    while True:
        blocco = dati[pos:pos + 2880]
        if len(blocco) < 2880:
            raise ValueError("intestazione FITS troncata")
        pos += 2880
        fine = False
        for k in range(36):
            carta = blocco[80 * k: 80 * (k + 1)].decode("ascii", "replace")
            chiave = carta[:8].strip()
            if chiave == "END":
                fine = True
                break
            if carta[8:10] == "= ":
                v = carta[10:].split("/")[0].strip()
                if v.startswith("'"):
                    v = v.strip("'").strip()
                else:
                    try:
                        v = float(v) if any(c in v for c in ".EeDd") else int(v)
                    except ValueError:
                        pass
                intest[chiave] = v
        if fine:
            break
    bitpix = int(intest["BITPIX"])
    nx, ny = int(intest["NAXIS1"]), int(intest["NAXIS2"])
    tipo = {8: ">u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}[bitpix]
    n = nx * ny
    img = np.frombuffer(dati[pos:pos + n * abs(bitpix) // 8], dtype=tipo).astype(float)
    if img.size < n:
        raise ValueError("dati FITS troncati")
    img = img.reshape(ny, nx) * float(intest.get("BSCALE", 1.0)) + float(intest.get("BZERO", 0.0))
    return img, intest


def url_skyview(survey, campo=CAMPO_GRADI, pixel=PIXEL):
    q = {"Survey": survey, "Position": f"{SGR_A[0]:.6f},{SGR_A[1]:.6f}", "Size": f"{campo:.5f}",
         "Pixels": str(pixel), "Coordinates": "J2000", "Projection": "Tan", "Sampler": "LI",
         "Return": "FITS"}
    return SKYVIEW + "?" + urllib.parse.urlencode(q)


def _motivo(dati):
    """Il testo di una risposta che non e' un FITS (pagina HTML di SkyView), in breve."""
    import re
    t = re.sub(r"<[^>]+>", " ", dati[:4000].decode("utf-8", "replace"))
    return " ".join(t.split())[:160]


def scarica_immagini(log=print, forza=False, tentativi=3):
    """Le immagini di contesto (cache in ~/.cache/buco_nero). Restituisce [(titolo, immagine, survey)]."""
    out = []
    for n_pannello, scelte in enumerate(IMMAGINI):
        preso = None
        if n_pannello == 1:
            try:
                rgb = scarica_2mass(log=log, forza=forza)
                if np.isfinite(rgb).mean() > 0.5:
                    out.append((TITOLO_2MASS, rgb, "2MASS JHK (IRSA)"))
                    continue
                log("IRSA 2MASS: copertura insufficiente, provo SkyView")
            except Exception as e:  # noqa: BLE001
                log(f"IRSA 2MASS: {type(e).__name__} {str(e)[:200]}; provo SkyView")
        for survey, titolo in scelte:
            f = m.cartella_dati() / f"skyview_{survey.replace(' ', '_')}.fits"
            dati = f.read_bytes() if (f.exists() and not forza) else None
            attesa = 8
            for k in range(tentativi if dati is None else 0):
                try:
                    req = urllib.request.Request(url_skyview(survey), headers={"User-Agent": m.UA})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        dati = r.read()
                    if not dati.startswith(b"SIMPLE"):
                        motivo = _motivo(dati)
                        raise RuntimeError(("SkyView sovraccarico: " if "overload" in motivo.lower()
                                            or "Too Many" in motivo else "risposta non FITS: ") + motivo)
                    leggi_fits(dati)
                    f.write_bytes(dati)
                    log(f"SkyView {survey}: {len(dati) // 1024} kB")
                    break
                except Exception as e:  # noqa: BLE001
                    dati = None
                    if k < tentativi - 1:
                        log(f"SkyView {survey}: {type(e).__name__} {str(e)[:200]}; riprovo tra {attesa} s")
                        time.sleep(attesa)
                        attesa = min(60, attesa * 2)
                    else:
                        log(f"SkyView {survey}: {type(e).__name__} {str(e)[:200]}; provo la prossima survey")
            if dati is not None:
                img, _ = leggi_fits(dati)
                preso = (titolo, img, survey)
                break
        if preso:
            out.append(preso)
        else:
            log("SkyView: nessuna survey disponibile per " + scelte[0][1])
    return out


# ---------------------------------------------------------------- 2MASS da IRSA (1.6)
def _scarica(url, timeout, tentativi=3, log=print, nome=""):
    attesa = 8
    for k in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": m.UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dati = r.read()
            if dati[:2] == b"\x1f\x8b":
                dati = gzip.decompress(dati)
            return dati
        except Exception as e:  # noqa: BLE001
            if k == tentativi - 1:
                raise
            log(f"IRSA {nome}: {type(e).__name__} {str(e)[:150]}; riprovo tra {attesa} s")
            time.sleep(attesa)
            attesa = min(60, attesa * 2)


def leggi_votable(testo):
    """Righe di una VOTable (TABLEDATA) come dizionari {nome campo: testo}."""
    radice = ET.fromstring(testo)
    tolto = lambda t: t.split("}")[-1]  # noqa: E731
    campi = [el.get("name") for el in radice.iter() if tolto(el.tag) == "FIELD"]
    righe = []
    for tr in (el for el in radice.iter() if tolto(el.tag) == "TR"):
        celle = [(td.text or "").strip() for td in tr if tolto(td.tag) == "TD"]
        righe.append(dict(zip(campi, celle)))
    return righe


def _griglia(pixel=PIXEL, campo=CAMPO_GRADI):
    """AR, Dec (gradi) dei centri dei pixel della figura: colonna 0 a est (sinistra), riga 0 a sud."""
    passo = campo / pixel
    mezzo = campo / 2
    xi = np.radians(mezzo - (np.arange(pixel) + 0.5) * passo)          # verso est
    eta = np.radians(-mezzo + (np.arange(pixel) + 0.5) * passo)        # verso nord
    XI, ETA = np.meshgrid(xi, eta)
    a0, d0 = np.radians(SGR_A[0]), np.radians(SGR_A[1])
    den = math.cos(d0) - ETA * math.sin(d0)                            # inversa gnomonica
    ra = a0 + np.arctan2(XI, den)
    dec = np.arctan2(math.sin(d0) + ETA * math.cos(d0), np.hypot(XI, den))
    return np.degrees(ra), np.degrees(dec)


def pixel_sin(ra, dec, crval1, crval2, crpix1, crpix2, cdelt1, cdelt2, crota2=0.0):
    """Coordinate di pixel (base 0, float) in un'immagine con proiezione SIN (come le Atlas 2MASS)."""
    a, d = np.radians(ra), np.radians(dec)
    a0, d0 = math.radians(crval1), math.radians(crval2)
    x = np.degrees(np.cos(d) * np.sin(a - a0))
    y = np.degrees(np.sin(d) * math.cos(d0) - np.cos(d) * math.sin(d0) * np.cos(a - a0))
    r = math.radians(crota2)
    dx = x * math.cos(r) + y * math.sin(r)
    dy = -x * math.sin(r) + y * math.cos(r)
    return dx / cdelt1 + crpix1 - 1, dy / cdelt2 + crpix2 - 1


def _copertura(riga, ra, dec):
    """Maschera dei pixel della figura che cadono dentro una tessera (dai metadati SIA)."""
    nx, ny = (int(v) for v in riga["naxis"].split())
    c1, c2 = (float(v) for v in riga["crval"].split())
    p1, p2 = (float(v) for v in riga["crpix"].split())
    s1, s2 = (float(v) for v in riga["scale"].split())
    px, py = pixel_sin(ra, dec, c1, c2, p1, p2, s1, s2, float(riga.get("crota2") or 0))
    return (px > -0.5) & (px < nx - 0.5) & (py > -0.5) & (py < ny - 0.5)


def scegli_tessere(righe, ra, dec, banda, massimo=6):
    """Le tessere Atlas (All-Sky) di una banda che coprono la figura, scelte una alla volta
    finche' la copertura arriva al 99,5 % (al massimo `massimo`)."""
    cand = [r for r in righe if r.get("band") == banda and r.get("type") == "A"
            and r.get("dataset") == "asky" and r.get("download")]
    coperto = np.zeros(ra.shape, bool)
    scelte = []
    maschere = [(r, _copertura(r, ra, dec)) for r in cand]
    while maschere and len(scelte) < massimo and coperto.mean() < 0.995:
        r, mk = max(maschere, key=lambda t: int((t[1] & ~coperto).sum()))
        if not (mk & ~coperto).any():
            break
        scelte.append(r)
        coperto |= mk
        maschere = [t for t in maschere if t[0] is not r]
    return scelte, float(coperto.mean())


def mosaico(tessere, ra, dec):
    """Le tessere (immagine, intestazione) riportate sulla griglia della figura, vicino piu' vicino,
    fondo tolto e flusso riportato allo stesso punto zero (MAGZP 20); media dove si sovrappongono."""
    somma = np.zeros(ra.shape)
    peso = np.zeros(ra.shape)
    for img, h in tessere:
        px, py = pixel_sin(ra, dec, float(h["CRVAL1"]), float(h["CRVAL2"]), float(h["CRPIX1"]),
                           float(h["CRPIX2"]), float(h["CDELT1"]), float(h["CDELT2"]), float(h.get("CROTA2", 0)))
        ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
        ny, nx = img.shape
        dentro = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        v = np.full(ra.shape, np.nan)
        v[dentro] = img[iy[dentro], ix[dentro]]
        fin = np.isfinite(v)
        if not fin.any():
            continue
        fattore = 10 ** (-0.4 * (float(h.get("MAGZP", 20.0)) - 20.0))
        v = (v - np.nanmedian(img)) * fattore
        somma[fin] += v[fin]
        peso[fin] += 1
    out = np.full(ra.shape, np.nan)
    ok = peso > 0
    out[ok] = somma[ok] / peso[ok]
    return out


def scarica_2mass(log=print, forza=False):
    """Immagine a colori 2MASS (ny, nx, 3: Ks, H, J) del campo, oppure None. Cache in ~/.cache/buco_nero."""
    cache = m.cartella_dati()
    elenco_f = cache / "2mass_elenco.json"
    ra, dec = _griglia()
    elenco = None
    if elenco_f.exists() and not forza:
        try:
            elenco = json.loads(elenco_f.read_text())
        except ValueError:
            elenco = None
    if elenco is None:
        q = {"POS": f"{SGR_A[0]:.6f},{SGR_A[1]:.6f}", "SIZE": f"{CAMPO_GRADI * 1.5:.4f}", "FORMAT": "image/fits"}
        testo = _scarica(SIA_2MASS + "?" + urllib.parse.urlencode(q), 60, log=log, nome="elenco 2MASS")
        righe = leggi_votable(testo)
        elenco = {}
        for banda in "KHJ":
            scelte, cop = scegli_tessere(righe, ra, dec, banda)
            elenco[banda] = [{"nome": r["download"].split("name=")[-1], "url": r["download"]} for r in scelte]
            log(f"IRSA 2MASS {banda}: {len(scelte)} tessere, copertura {cop * 100:.1f} %")
        if not all(elenco.values()):
            raise RuntimeError("IRSA non ha restituito tessere 2MASS per tutte e tre le bande")
        elenco_f.write_text(json.dumps(elenco))
    canali = []
    for banda in "KHJ":
        tessere = []
        for t in elenco[banda]:
            f = cache / f"2mass_{t['nome']}"
            if f.exists() and not forza:
                dati = f.read_bytes()
            else:
                dati = _scarica(t["url"], 120, log=log, nome=t["nome"])
                leggi_fits(dati)
                f.write_bytes(dati)
                log(f"IRSA 2MASS {t['nome']}: {len(dati) // 1024} kB")
            tessere.append(leggi_fits(dati))
        canali.append(mosaico(tessere, ra, dec))
    return np.dstack(canali)


def scala_asinh(img, morbidezza=10.0):
    if img.ndim == 3:                     # a colori: ogni canale per conto suo
        return np.dstack([scala_asinh(img[..., k], morbidezza) for k in range(img.shape[2])])
    v = img[np.isfinite(img)]
    if v.size == 0:
        return np.zeros_like(img)
    fondo = np.median(v)
    s = np.std(v[v < np.percentile(v, 90)]) or 1.0
    nero = fondo + 0.5 * s
    bianco = np.percentile(v, 99.7)
    x = np.clip((img - nero) / max(bianco - nero, 1e-9), 0, 1)
    x = np.where(np.isfinite(x), x, 0.0)
    return np.arcsinh(morbidezza * x) / np.arcsinh(morbidezza)


def disegna_contesto(fig, immagini, fs=10):
    """Le immagini una accanto all'altra con Sgr A* al centro e la scala delle orbite."""
    from grafici_bn import INK, INK2, SURF, _firma
    fig.clear()
    fig.set_facecolor(SURF)
    if not immagini:
        fig.text(0.5, 0.5, "SkyView images not available (no network?)", ha="center", va="center",
                 fontsize=fs * 1.2, color=INK2)
        return
    n = len(immagini)
    mezzo = CAMPO_GRADI * 60 / 2
    for k, (titolo, img, _) in enumerate(immagini):
        ax = fig.add_subplot(1, n, k + 1)
        ax.imshow(scala_asinh(img), cmap=None if img.ndim == 3 else "gray", origin="lower", extent=(mezzo, -mezzo, -mezzo, mezzo))
        ax.plot([0], [0], marker="o", ms=14, mfc="none", mec="#f2c14e", mew=1.5)
        ax.annotate("Sgr A*", (0, 0), xytext=(14, 14), textcoords="offset points", color="#f2c14e",
                    fontsize=fs * 0.9)
        ax.set_title(titolo, fontsize=fs * 1.05, color=INK, loc="left")
        ax.set_xlabel("ΔRA (arcmin)", fontsize=fs * 0.9, color=INK)
        if k == 0:
            ax.set_ylabel("ΔDec (arcmin)", fontsize=fs * 0.9, color=INK)
        ax.tick_params(labelsize=fs * 0.8, colors=INK2)
    fonti = sorted({"IRSA" if "IRSA" in s else "SkyView" for _, _, s in immagini})
    fig.suptitle(f"The centre of the Milky Way, 10′ × 10′ ({' + '.join(fonti)})\n"
                 "The whole orbit of S2 (0.25″) is far smaller than the yellow circle", fontsize=fs * 0.9, color=INK2,
                 x=0.01, ha="left")
    _firma(fig, fs)
    fig.tight_layout(rect=(0, 0.05, 1, 0.86))
