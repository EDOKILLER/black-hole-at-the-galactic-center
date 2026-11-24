"""Il buco nero al centro della Galassia - grafici e scheda (in inglese).

Ogni funzione disegna su una Figure di matplotlib passata dall'esterno (cosi' la
finestra Tk e la scheda PDF usano gli stessi grafici).
(c) 2026 Edoardo Battistel
"""

import math
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse

import motore_bn as m

# colori (palette di riferimento, modo chiaro)
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e4e3df"
SURF = "#fcfcfb"
COL = {"NACO/VLT": "#2a78d6", "SHARP/NTT": "#eb6834", "GEMINI": "#6250d6",
       "SINFONI/VLT": "#2a78d6", "NIRC2/Keck": "#1baf7a", "Keck (Chu+2018)": "#1baf7a",
       "Keck (Do+2019)": "#1baf7a"}
COL_MODEL = INK2
COL_PRED = "#e34948"


COL_STELLE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def multi(res):
    return len(getattr(res, "stelle", []) or []) > 1


def colore_stella(res, s):
    return COL_STELLE[res.stelle.index(s) % len(COL_STELLE)]


def _stile(ax, fs):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=INK2, labelsize=fs * 0.85)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def _firma(fig, fs):
    fig.text(0.995, 0.005, m.FIRMA, ha="right", va="bottom", fontsize=fs * 0.7, color=MUTED)


def disegna_orbita(fig, res, fs=10):
    """Orbita sul cielo: misure, orbita adattata, posizione di Sgr A*."""
    if multi(res):
        return disegna_orbita_multi(fig, res, fs)
    fig.clear()
    fig.set_facecolor(SURF)
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    p, d = res.p, res.dati
    t = np.linspace(p["tp"] - p["P"] / 2, p["tp"] + p["P"] / 2, 3000)
    # orbita senza il moto del sistema: disegno nel sistema di Sgr A* all'epoca di riferimento
    ra, dec = m.modello_astrometria(p, t, res.opzioni.romer)
    corr_ra = p["vx0"] * (t - m.EPOCA_RIF)
    corr_dec = p["vy0"] * (t - m.EPOCA_RIF)
    ax.plot(ra - corr_ra, dec - corr_dec, color=COL_MODEL, lw=1.5, label="best-fit Keplerian orbit", zorder=2)
    dra = p["vx0"] * (d.ta - m.EPOCA_RIF)
    ddec = p["vy0"] * (d.ta - m.EPOCA_RIF)
    for s in sorted(set(d.strum_a), key=lambda x: -d.strum_a.count(x)):
        j = np.array([q == s for q in d.strum_a])
        usati = j & res.mask_a
        ax.errorbar(d.ra[usati] - dra[usati], d.dec[usati] - ddec[usati], xerr=d.era[usati], yerr=d.edec[usati],
                    fmt="o", ms=3.2, color=COL.get(s, INK2), ecolor=COL.get(s, INK2), elinewidth=0.6,
                    mec=SURF, mew=0.6, alpha=0.9, label=f"{s} ({usati.sum()})", zorder=3)
        esc = j & ~res.mask_a
        if esc.any():
            ax.plot(d.ra[esc] - dra[esc], d.dec[esc] - ddec[esc], "o", ms=5, mfc="none",
                    mec=COL.get(s, INK2), mew=1.0, label=f"{s} excluded ({esc.sum()})", zorder=3)
    ax.plot([p["x0"]], [p["y0"]], marker="+", ms=12, mew=2, color=INK, ls="none",
            label="Sgr A* (fitted position)", zorder=4)
    # pericentro e apocentro
    for tt, nome in ((p["tp"], "pericentre"), (p["tp"] + p["P"] / 2, "apocentre")):
        x, y = m.modello_astrometria(p, [tt], res.opzioni.romer)
        x = x - p["vx0"] * (tt - m.EPOCA_RIF)
        y = y - p["vy0"] * (tt - m.EPOCA_RIF)
        ax.annotate(nome, (x[0], y[0]), xytext=(10, -16) if nome == "pericentre" else (8, 4),
                    textcoords="offset points", fontsize=fs * 0.8, color=INK2)
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_xaxis()      # est a sinistra, come sul cielo
    ax.set_xlabel("ΔRA (mas, east ←)", fontsize=fs, color=INK)
    ax.set_ylabel("ΔDec (mas)", fontsize=fs, color=INK)
    ax.set_title(f"Orbit of {res.stella} around Sgr A* on the sky", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.75, frameon=False, loc="best")
    _firma(fig, fs)
    fig.tight_layout()


def disegna_velocita(fig, res, fs=10, fino_a=2036.0):
    """Velocita' radiale: misure, modello, previsione dei pericentri 2018 e ~2034."""
    if multi(res):
        return disegna_velocita_multi(fig, res, fs)
    fig.clear()
    fig.set_facecolor(SURF)
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    p, d = res.p, res.dati
    t0 = min(d.tv.min(), d.ta.min()) - 0.5
    t = np.linspace(t0, fino_a, 20000)
    v = m.modello_velocita(p, t, res.opzioni.romer, res.opzioni.relativita)
    ultimo = max(d.ta.max(), d.tv.max())
    ax.plot(t[t <= ultimo], v[t <= ultimo], color=COL_MODEL, lw=1.5, label="best-fit model", zorder=2)
    ax.plot(t[t >= ultimo], v[t >= ultimo], color=COL_PRED, lw=1.5, ls="--",
            label="prediction (no data used)", zorder=2)
    for s in sorted(set(d.strum_v)):
        j = np.array([q == s for q in d.strum_v])
        u = j & res.mask_v
        ax.errorbar(d.tv[u], d.rv[u], yerr=d.erv[u], fmt="o", ms=3.5, color=COL.get(s, INK2),
                    ecolor=COL.get(s, INK2), elinewidth=0.7, mec=SURF, mew=0.6, label=f"{s} ({u.sum()})", zorder=3)
        e = j & ~res.mask_v
        if e.any():
            ax.plot(d.tv[e], d.rv[e], "o", ms=5.5, mfc="none", mec=COL.get(s, INK2), label=f"{s} excluded")
    for k, tp in enumerate(res.derivati["peri"]):
        if tp <= fino_a:
            ax.axvline(tp, color=MUTED, lw=0.8, ls=":")
            ax.annotate(f"pericentre {tp:.2f}\n({m.anno_in_data(tp)})", (tp, 0.97), xycoords=("data", "axes fraction"),
                        xytext=(5, 0), textcoords="offset points", va="top", fontsize=fs * 0.75, color=INK2)
    ax.axvline(p["tp"], color=MUTED, lw=0.8, ls=":")
    ax.annotate(f"pericentre {p['tp']:.2f}", (p["tp"], 0.97), xycoords=("data", "axes fraction"),
                xytext=(5, 0), textcoords="offset points", va="top", fontsize=fs * 0.75, color=INK2)
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_xlabel("year", fontsize=fs, color=INK)
    ax.set_ylabel("radial velocity (km/s, LSR)", fontsize=fs, color=INK)
    ax.set_title(f"Radial velocity of {res.stella}", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.75, frameon=False, loc="lower left")
    _firma(fig, fs)
    fig.tight_layout()


def disegna_massa_distanza(fig, res, fs=10):
    """Piano massa-distanza: ellissi 1 e 2 sigma del risultato e valori pubblicati."""
    if multi(res):
        return disegna_massa_distanza_multi(fig, res, fs)
    fig.clear()
    fig.set_facecolor(SURF)
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    iM, iR = m.NOMI_PARAMETRI.index("M"), m.NOMI_PARAMETRI.index("R0")
    C = res.cov[np.ix_([iR, iM], [iR, iM])]
    w, V = np.linalg.eigh(C)
    ang = math.degrees(math.atan2(V[1, 1], V[0, 1]))
    for k, a in ((2.0, 0.18), (1.0, 0.35)):     # 1 e 2 sigma (regione bidimensionale: 39 % e 86 %)
        e = Ellipse((res.p["R0"], res.p["M"]), 2 * k * math.sqrt(w[1]), 2 * k * math.sqrt(w[0]), angle=ang,
                    facecolor="#2a78d6", alpha=a, edgecolor="#2a78d6", lw=1)
        ax.add_patch(e)
    ax.plot([res.p["R0"]], [res.p["M"]], "o", color="#2a78d6", ms=7, mec=SURF, mew=1.2,
            label=f"this fit ({res.stella}), 1\u03c3 and 2\u03c3 regions", zorder=4)
    marker = ["s", "D", "^", "v", "P"]
    for k, (nome, M, eM, R, eR) in enumerate(m.LETTERATURA):
        ax.errorbar([R], [M], xerr=[eR], yerr=[eM], fmt=marker[k % 5], color=INK2, ms=6, mfc=SURF,
                    elinewidth=0.8, zorder=3, label=nome)
    ax.set_xlabel("distance to the Galactic Centre R₀ (kpc)", fontsize=fs, color=INK)
    ax.set_ylabel("mass of Sgr A* (million M☉)", fontsize=fs, color=INK)
    ax.set_title(f"Mass and distance (correlation {res.corr_M_R0:.2f})", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.75, frameon=False, loc="upper left")
    ax.autoscale_view()
    _firma(fig, fs)
    fig.tight_layout()


def disegna_residui(fig, res, fs=10):
    if multi(res):
        return disegna_residui_multi(fig, res, fs)
    fig.clear()
    fig.set_facecolor(SURF)
    axs = fig.subplots(3, 1, sharex=True)
    p, d = res.p, res.dati
    ra, dec = m.modello_astrometria(p, d.ta, res.opzioni.romer)
    v = m.modello_velocita(p, d.tv, res.opzioni.romer, res.opzioni.relativita)
    serie = [(d.ta, d.ra - ra, d.era, d.strum_a, res.mask_a, "ΔRA residual (mas)"),
             (d.ta, d.dec - dec, d.edec, d.strum_a, res.mask_a, "ΔDec residual (mas)"),
             (d.tv, d.rv - v, d.erv, d.strum_v, res.mask_v, "RV residual (km/s)")]
    for ax, (t, r, e, st, mk, nome) in zip(axs, serie):
        _stile(ax, fs)
        for s in sorted(set(st)):
            j = np.array([q == s for q in st])
            ax.errorbar(t[j & mk], r[j & mk], yerr=e[j & mk], fmt="o", ms=2.8, color=COL.get(s, INK2),
                        elinewidth=0.5, mec=SURF, mew=0.5, label=s)
            if (j & ~mk).any():
                ax.plot(t[j & ~mk], r[j & ~mk], "o", ms=5, mfc="none", mec=COL.get(s, INK2))
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylabel(nome, fontsize=fs * 0.85, color=INK)
    axs[0].legend(fontsize=fs * 0.7, frameon=False, ncol=4, loc="upper left")
    axs[2].legend(fontsize=fs * 0.7, frameon=False, ncol=4, loc="upper left")
    axs[0].set_title("Residuals (data − model)", fontsize=fs * 1.15, color=INK, loc="left")
    axs[-1].set_xlabel("year", fontsize=fs, color=INK)
    _firma(fig, fs)
    fig.tight_layout()


def _fmt(v, e):
    if e <= 0 or not math.isfinite(e):
        return f"{v:.5g}"
    cifre = max(0, -int(math.floor(math.log10(e))) + 1)
    return f"{v:.{cifre}f} ± {e:.{cifre}f}"


def pendenza_M_R0(res):
    """Esponente k di M \u221d R0^k lungo la direzione di massima correlazione."""
    iM, iR = m.NOMI_PARAMETRI.index("M"), m.NOMI_PARAMETRI.index("R0")
    return res.cov[iM, iR] / res.cov[iR, iR] * res.p["R0"] / res.p["M"]


def testo_risultati(res):
    """Righe di testo (inglese) per la scheda."""
    if multi(res):
        return testo_risultati_multi(res)
    p, e, dv = res.p, res.err, res.derivati
    pub = res.pubblicata or {}
    pr = m.previsione_pericentro(res, 0)
    righe = [
        ("Mass of Sgr A*", f"{_fmt(p['M'], e['M'])} million solar masses"),
        ("Distance R₀", f"{_fmt(p['R0'], e['R0'])} kpc"),
        ("M–R₀ correlation", f"{res.corr_M_R0:.2f}  (along the error valley M ∝ R₀^{pendenza_M_R0(res):.1f})"),
        ("Period", f"{_fmt(p['P'], e['P'])} yr"),
        ("Semi-major axis", f"{_fmt(dv['a'][0] * 1000, dv['a'][1] * 1000)} mas = {dv['a'][0] * p['R0'] * 1000:.0f} AU"),
        ("Eccentricity", _fmt(p["e"], e["e"])),
        ("Inclination / Ω / ω", f"{_fmt(p['i'], e['i'])}° / {_fmt(p['Omega'], e['Omega'])}° / "
                                          f"{_fmt(p['omega'], e['omega'])}°"),
        ("Pericentre passage", f"{_fmt(p['tp'], e['tp'])} ({m.anno_in_data(p['tp'])})"),
        ("Pericentre distance", f"{_fmt(*dv['rp'])} AU = {dv['rp_rs']:.0f} Schwarzschild radii"),
        ("Speed at pericentre", f"{_fmt(*dv['vp'])} km/s = {dv['vp'][0] / m.C_KMS * 100:.2f} % of c"),
        ("Next pericentres (predicted)", f"{dv['peri'][0]:.2f} ± {dv['e_peri'][0]:.2f} ({m.anno_in_data(dv['peri'][0])}),"
                                         f" {dv['peri'][1]:.2f} ± {dv['e_peri'][1]:.2f}"),
        ("GR redshift at pericentre", f"{pr['redshift_gr']:.0f} km/s (gravitational + transverse Doppler, predicted)"),
        ("GR (Schwarzschild) precession", f"{dv['precessione_arcmin']:.1f}′ per orbit (predicted)"),
        ("Fit quality", f"χ² = {res.chi2:.1f} for {res.dof} degrees of freedom (reduced {res.chi2_rid:.2f})"),
        ("Data used", f"{res.n_a} positions, {res.n_v} radial velocities"
                      + (f"; excluded {len(res.esclusi_a)} + {len(res.esclusi_v)} outliers > {res.opzioni.soglia_sigma:g}σ"
                         if res.esclusi_a or res.esclusi_v else "; no outliers excluded")),
    ]
    righe += righe_extra(res)
    if pub.get("a"):
        righe.append(("Published orbit (Gillessen+ 2017)",
                      f"a = {pub['a'] * 1000:.1f} mas, e = {pub['e']:.4f}, i = {pub['i']:.2f}°, "
                      f"P = {pub['Per']:.2f} yr, tp = {pub['Tp']:.2f}"))
    return righe


def disegna_pagina_riassunto(fig, res, fs=9):
    fig.clear()
    fig.set_facecolor("white")
    chi = f"stars {', '.join(res.stelle)}" if multi(res) else f"star {res.stella}"
    fig.text(0.05, 0.965, "Weighing the black hole at the centre of the Milky Way",
             fontsize=fs * 1.7, color=INK, weight="bold", va="top")
    fig.text(0.05, 0.93, f"{chi[0].upper() + chi[1:]}: Keplerian orbit fit to published astrometry and spectroscopy "
             "(black hole = point mass)",
             fontsize=fs * 1.05, color=INK2, va="top")
    y = 0.885
    for nome, val in testo_risultati(res):
        fig.text(0.05, y, nome, fontsize=fs, color=INK2, va="top")
        fig.text(0.37, y, val, fontsize=fs, color=INK, va="top", wrap=True)
        y -= 0.027
    y -= 0.01
    fig.text(0.05, y, "Comparison with published values", fontsize=fs * 1.15, color=INK, weight="bold", va="top")
    y -= 0.03
    for nome, M, eM, R, eR in m.LETTERATURA:
        dM = (res.p["M"] - M) / math.hypot(res.err["M"], eM)
        fig.text(0.05, y, nome, fontsize=fs, color=INK2, va="top")
        fig.text(0.37, y, f"M = {M:.3f} ± {eM:.3f},  R₀ = {R:.3f} ± {eR:.3f}   "
                          f"(difference in M: {dM:+.1f}σ)", fontsize=fs, color=INK, va="top")
        y -= 0.025
    y -= 0.01
    note = [
        (f"Method: joint fit with {7 + 6 * len(res.stelle)} parameters (common M, R₀ and reference frame, six orbital "
         "elements per star)" if multi(res) else
         "Method: 13-parameter fit (M, R₀, six orbital elements, position and velocity of the astrometric reference"),
        ("with SciPy least squares; uncertainties from the covariance matrix (1σ, statistical only)." if multi(res) else
         "frame) with SciPy least squares; uncertainties from the covariance matrix (1σ, statistical only)."),
        f"NACO errors multiplied by {m.NACO_FATTORE} as in Gillessen+ 2009/2017; Rømer delay "
        + ("included" if res.opzioni.romer else "not included")
        + "; relativistic redshift " + ("included in the fit." if res.opzioni.relativita else "not fitted (shown as a prediction)."),
        f"Weak priors on the reference frame: position 0 ± {res.opzioni.priore_pos:g} mas, "
        f"velocity 0 ± {res.opzioni.priore_vel:g} mas/yr.",
        ("Positions end in 2016.5; Keck radial velocities (Do+ 2019) run to 2018.7, through the 2018 pericentre."
         if res.dati.tv.size and res.dati.tv.max() > 2017 else
         "The data end in 2016.5: the 2018 pericentre and everything after is a prediction, to compare with GRAVITY."),
        "Literature values from GRAVITY Collaboration 2022, A&A 657, L12, Table B.1, and GRAVITY 2019, A&A 625, L10.",
        "Data: " + "; ".join(res.dati.fonti),
    ]
    for r in note:
        fig.text(0.05, y, r, fontsize=fs * 0.8, color=INK2, va="top", wrap=True)
        y -= 0.021
    fig.text(0.05, 0.02, f"Il buco nero al centro della Galassia {m.VERSIONE} — {m.FIRMA}",
             fontsize=fs * 0.8, color=MUTED)


def scheda(res, cartella):
    """Scheda PDF (4 pagine) + PNG dei grafici. Restituisce la lista dei file."""
    from matplotlib.backends.backend_pdf import PdfPages
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    file = []
    base = "_".join(res.stelle) if multi(res) else res.stella
    pdf_path = cartella / f"{base}_black_hole_report.pdf"
    pagine = [("summary", disegna_pagina_riassunto, (8.27, 11.69)),
              ("orbit", disegna_orbita, (8.27, 8.0)),
              ("radial_velocity", disegna_velocita, (11.0, 6.0)),
              ("mass_distance", disegna_massa_distanza, (8.27, 6.5)),
              ("residuals", disegna_residui, (11.0, 7.5))]
    if getattr(res, "mcmc", None):
        pagine.append(("mcmc", disegna_mcmc, (11.0, 7.5)))
    if getattr(res, "contesto", None):
        import contesto_bn
        pagine.append(("galactic_centre", lambda f, r, fs: contesto_bn.disegna_contesto(f, r.contesto, fs),
                       (11.0, 6.0)))
    with PdfPages(pdf_path) as pdf:
        for nome, f, size in pagine:
            fig = Figure(figsize=size)
            f(fig, res, 9 if nome == "summary" else 11)
            pdf.savefig(fig)
            if nome != "summary":
                png = cartella / f"{base}_{nome}.png"
                fig.savefig(png, dpi=150)
                file.append(png)
        d = pdf.infodict()
        d["Title"] = f"Sgr A* mass from the orbit of {base.replace('_', ', ')}"
        d["Author"] = "Edoardo Battistel"
    file.insert(0, pdf_path)
    (cartella / f"{base}_summary.json").write_text(m.riassunto_json(res), encoding="utf-8")
    return file


# =============================================================================
# PIU' STELLE INSIEME
# =============================================================================
def _orbita_cielo(p, t):
    """Posizione (AR, Dec) in mas nel sistema di Sgr A* (senza moto del sistema)."""
    pos, _ = m.stato(p, t)
    return pos[:, 1] / p["R0"], pos[:, 0] / p["R0"]


def disegna_orbita_multi(fig, res, fs=10):
    fig.clear()
    fig.set_facecolor(SURF)
    fig.set_layout_engine("constrained")       # legenda fuori a destra, titolo corto (1.5 del 21/11)
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    for s, rs in res.sub.items():
        c = colore_stella(res, s)
        p, d = rs.p, rs.dati
        t = np.linspace(p["tp"] - p["P"] / 2, p["tp"] + p["P"] / 2, 3000)
        x, y = _orbita_cielo(p, t)
        ax.plot(x + p["x0"], y + p["y0"], color=c, lw=1.5, zorder=2)
        dra = p["vx0"] * (d.ta - m.EPOCA_RIF)
        ddec = p["vy0"] * (d.ta - m.EPOCA_RIF)
        u = rs.mask_a
        ax.errorbar(d.ra[u] - dra[u], d.dec[u] - ddec[u], xerr=d.era[u], yerr=d.edec[u], fmt="o", ms=3,
                    color=c, ecolor=c, elinewidth=0.5, mec=SURF, mew=0.5, alpha=0.9, zorder=3,
                    label=f"{s}: P = {p['P']:.1f} yr ({u.sum()} positions)")
        if (~u).any():
            ax.plot(d.ra[~u] - dra[~u], d.dec[~u] - ddec[~u], "o", ms=5, mfc="none", mec=c, zorder=3)
    p = res.p
    ax.plot([p["x0"]], [p["y0"]], marker="+", ms=12, mew=2, color=INK, ls="none", label="Sgr A*", zorder=4)
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_xaxis()
    ax.set_xlabel("ΔRA (mas, east ←)", fontsize=fs, color=INK)
    ax.set_ylabel("ΔDec (mas)", fontsize=fs, color=INK)
    ax.set_title("Orbits around Sgr A* (joint fit)", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.75, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    _firma(fig, fs)


def disegna_velocita_multi(fig, res, fs=10, fino_a=2036.0):
    fig.clear()
    fig.set_facecolor(SURF)
    fig.set_layout_engine("constrained")
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    for s, rs in res.sub.items():
        c = colore_stella(res, s)
        p, d = rs.p, rs.dati
        ultimo = max(d.ta.max(), d.tv.max() if d.n_v else d.ta.max())
        t = np.linspace(1995.0, fino_a, 16000)
        v = m.modello_velocita(p, t, res.opzioni.romer, res.opzioni.relativita)
        ax.plot(t[t <= ultimo], v[t <= ultimo], color=c, lw=1.4, zorder=2,
                label=None if d.n_v else f"{s} (no RV)")
        ax.plot(t[t >= ultimo], v[t >= ultimo], color=c, lw=1.2, ls="--", zorder=2)
        u = rs.mask_v
        if d.n_v:
            ax.errorbar(d.tv[u], d.rv[u], yerr=d.erv[u], fmt="o", ms=3.5, color=c, ecolor=c, elinewidth=0.7,
                        mec=SURF, mew=0.6, zorder=3, label=f"{s} ({u.sum()} RV)")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_xlabel("year (dashed = prediction)", fontsize=fs, color=INK)
    ax.set_ylabel("radial velocity (km/s, LSR)", fontsize=fs, color=INK)
    ax.set_title("Radial velocities (joint fit)", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.7, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    _firma(fig, fs)


def disegna_massa_distanza_multi(fig, res, fs=10):
    fig.clear()
    fig.set_facecolor(SURF)
    fig.set_layout_engine("constrained")
    ax = fig.add_subplot(111)
    _stile(ax, fs)
    C = res.cov[np.ix_([1, 0], [1, 0])]
    w, V = np.linalg.eigh(C)
    ang = math.degrees(math.atan2(V[1, 1], V[0, 1]))
    for k, a in ((2.0, 0.18), (1.0, 0.35)):
        ax.add_patch(Ellipse((res.p["R0"], res.p["M"]), 2 * k * math.sqrt(w[1]), 2 * k * math.sqrt(w[0]),
                             angle=ang, facecolor=INK2, alpha=a * 0.6, edgecolor=INK2, lw=1))
    ax.plot([res.p["R0"]], [res.p["M"]], "o", color=INK, ms=7, mec=SURF, mew=1.2,
            label="joint fit, 1σ and 2σ regions", zorder=5)
    controllo = (getattr(res, "controllo", None) or ({}, 0))[0]
    n = max(1, len(controllo))
    larg = 0.6 * math.sqrt(w[1]) if w[1] > 0 else 0.02
    for k, (s, (M, eM)) in enumerate(controllo.items()):
        R = res.p["R0"] + (k - (n - 1) / 2) * larg / max(1, n - 1) * 0.6
        ax.errorbar([R], [M], yerr=[eM], fmt="o", color=colore_stella(res, s), ms=6, mec=SURF, elinewidth=1.2,
                    capsize=3, zorder=4, label=f"{s} alone at the common R₀: {M:.2f} ± {eM:.2f}")
    marker = ["s", "D", "^", "v", "P"]
    for k, (nome, M, eM, R, eR) in enumerate(m.LETTERATURA):
        ax.errorbar([R], [M], xerr=[eR], yerr=[eM], fmt=marker[k % 5], color=MUTED, ms=5, mfc=SURF,
                    elinewidth=0.8, zorder=3, label=nome)
    ax.set_xlabel("distance to the Galactic Centre R₀ (kpc)", fontsize=fs, color=INK)
    ax.set_ylabel("mass of Sgr A* (million M☉)", fontsize=fs, color=INK)
    ax.set_title(f"Mass and distance from {len(res.stelle)} stars", fontsize=fs * 1.15, color=INK, loc="left")
    ax.legend(fontsize=fs * 0.65, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              title="single-star points drawn side by side", title_fontsize=fs * 0.6)
    ax.autoscale_view()
    _firma(fig, fs)


def disegna_residui_multi(fig, res, fs=10):
    fig.clear()
    fig.set_facecolor(SURF)
    fig.set_layout_engine("constrained")
    axs = fig.subplots(3, 1, sharex=True)
    for s, rs in res.sub.items():
        c = colore_stella(res, s)
        p, d = rs.p, rs.dati
        ra, dec = m.modello_astrometria(p, d.ta, res.opzioni.romer)
        v = m.modello_velocita(p, d.tv, res.opzioni.romer, res.opzioni.relativita)
        for ax, (t, r, e, mk) in zip(axs, ((d.ta, d.ra - ra, d.era, rs.mask_a), (d.ta, d.dec - dec, d.edec, rs.mask_a),
                                           (d.tv, d.rv - v, d.erv, rs.mask_v))):
            if len(t):
                ax.errorbar(t[mk], r[mk], yerr=e[mk], fmt="o", ms=2.8, color=c, elinewidth=0.5, mec=SURF,
                            mew=0.5, label=s)
    for ax, nome in zip(axs, ("ΔRA (mas)", "ΔDec (mas)", "RV (km/s)")):
        _stile(ax, fs)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylabel(nome, fontsize=fs * 0.85, color=INK)
    axs[0].legend(fontsize=fs * 0.7, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    axs[0].set_title("Residuals (data − model), joint fit", fontsize=fs * 1.15, color=INK, loc="left")
    axs[-1].set_xlabel("year", fontsize=fs, color=INK)
    _firma(fig, fs)



def righe_extra(res):
    out = []
    if "fSP" in res.p:
        out.append(("Schwarzschild factor f_SP (fitted)",
                    f"{_fmt(res.p['fSP'], res.err.get('fSP', 0))}  (1 = general relativity, 0 = Newton; "
                    "data to 2016.5 cannot tell yet)"))
    mc = getattr(res, "mcmc", None)
    if mc:
        for k, nome in (("M", "M (MCMC, median and 68 %)"), ("R0", "R\u2080 (MCMC, median and 68 %)"),
                        ("fSP", "f_SP (MCMC)")):
            if k in mc["percentili"]:
                c, lo, hi = mc["percentili"][k]
                out.append((nome, f"{c:.3f} \u2212{lo:.3f} / +{hi:.3f}"))
        rh = mc.get("rhat_max")
        if rh is not None and rh == rh:
            out.append(("MCMC convergence", f"split R\u0302 for M, R\u2080: {mc.get('rhat_principali', rh):.3f}; "
                                            f"worst {mc.get('rhat_peggiore', '')} {rh:.2f} ({mc['n_passi']} steps, "
                                            f"~{mc['indipendenti']:.0f} indep. samples)"))
    rsh = getattr(res, "redshift", None)
    if rsh:
        out.append(("Relativistic redshift factor",
                    f"{rsh['upsilon']:.2f} \u00b1 {rsh['errore']:.2f}  (\u03c7\u00b2 profile; 1 = GR, 0 = Newton; "
                    f"{rsh['n_rv_dopo_2016']} RVs after 2016.6; GRAVITY 2019: 1.04 \u00b1 0.05)"))
    v = getattr(res, "verifica_1pn", None)
    if v:
        for s, x in v.items():
            out.append((f"1PN check, {s}",
                        f"model vs integrated 1PN orbit \u2264 {x['diff_pos_max_mas']:.2f} mas, "
                        f"{x['diff_vel_max_kms']:.1f} km/s (errors {x['errore_pos_mas']:.2f} mas, "
                        f"{x['errore_vel_kms']:.0f} km/s; whole GR effect {x['gr_pos_max_mas']:.2f} mas)"))
    return out


def testo_risultati_multi(res):
    p, e = res.p, res.err
    righe = [("Stars fitted together", ", ".join(res.stelle) + " (common mass, distance and reference frame)"),
             ("Mass of Sgr A*", f"{_fmt(p['M'], e['M'])} million solar masses"),
             ("Distance R₀", f"{_fmt(p['R0'], e['R0'])} kpc"),
             ("M–R₀ correlation", f"{res.corr_M_R0:.2f}"),
             ("Fit quality", f"χ² = {res.chi2:.1f} for {res.dof} degrees of freedom "
                             f"(reduced {res.chi2_rid:.2f})")]
    for s, rs in res.sub.items():
        q, qe = rs.p, rs.err
        righe.append((f"{s} orbit ({rs.n_a} pos., {rs.n_v} RV)",
                      f"P = {_fmt(q['P'], qe['P'])} yr, e = {_fmt(q['e'], qe['e'])}, tp = {q['tp']:.2f}"))
    ctl = getattr(res, "controllo", None)
    if ctl:
        for s, (M, eM) in ctl[0].items():
            righe.append((f"{s} alone (R₀ fixed)", f"M = {_fmt(M, eM)} million solar masses"))
        righe.append(("Consistency of the masses", f"χ² = {ctl[1]:.1f} for {len(ctl[0])} stars "
                      + ("(consistent)" if ctl[1] < 2 * len(ctl[0]) + 3 else "(tension)")))
    return righe + righe_extra(res)


# =============================================================================
# ANIMAZIONE
# =============================================================================
def trova_ffmpeg():
    import shutil
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


def animazione(res, cartella, da=1995.0, a=2035.0, passo=0.04, fps=30, lato_px=1080, avanzamento=None):
    """Animazione delle orbite (modello) con la scia: MP4 con ffmpeg, se no GIF animata (Pillow).
    Restituisce il percorso del file."""
    import matplotlib.animation as anim
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    stelle = list(getattr(res, "stelle", None) or [res.stella])
    sub = getattr(res, "sub", None) or {res.stella: res}
    dpi = 120
    fig = Figure(figsize=(lato_px / dpi, lato_px / dpi), dpi=dpi)
    FigureCanvasAgg(fig)
    fig.set_facecolor("#0b0b16")
    ax = fig.add_axes([0.06, 0.06, 0.9, 0.86])
    ax.set_facecolor("#0b0b16")
    for sp in ax.spines.values():
        sp.set_color("#3a3a55")
    ax.tick_params(colors="#9a9ab5", labelsize=9)
    tempi = np.arange(da, a + 1e-9, passo)
    tracce, punti, scie = {}, {}, {}
    tutte_x, tutte_y = [0.0], [0.0]
    for k, s in enumerate(stelle):
        p = sub[s].p
        t_orb = np.linspace(p["tp"] - p["P"] / 2, p["tp"] + p["P"] / 2, 2000)
        x, y = _orbita_cielo(p, t_orb)
        c = COL_STELLE[k % len(COL_STELLE)]
        ax.plot(x, y, color=c, lw=0.8, alpha=0.35)
        tracce[s] = _orbita_cielo(p, tempi)
        tutte_x += list(x)
        tutte_y += list(y)
        scie[s], = ax.plot([], [], color=c, lw=2.0, alpha=0.9)
        punti[s], = ax.plot([], [], "o", color=c, ms=8, mec="white", mew=0.8, label=s)
    ax.plot([0], [0], "o", color="black", ms=11, mec="#ffb347", mew=2.2, zorder=5)
    ax.annotate("Sgr A*", (0, 0), xytext=(10, -14), textcoords="offset points", color="#ffb347", fontsize=10)
    marg = 0.08 * (max(tutte_x) - min(tutte_x) + 1)
    ax.set_xlim(max(tutte_x) + marg, min(tutte_x) - marg)
    ax.set_ylim(min(tutte_y) - marg, max(tutte_y) + marg)
    ax.set_aspect("equal")
    ax.set_xlabel("ΔRA (mas, east ←)", color="#c8c8dd", fontsize=10)
    ax.set_ylabel("ΔDec (mas)", color="#c8c8dd", fontsize=10)
    ax.legend(loc="upper right", frameon=False, labelcolor="#e0e0f0", fontsize=10)
    fig.text(0.06, 0.955, "Stars orbiting the black hole at the centre of the Milky Way",
             color="#f0f0ff", fontsize=13, weight="bold")
    fig.text(0.06, 0.93, f"Keplerian model: M = {res.p['M']:.2f} million M☉, R₀ = {res.p['R0']:.2f} kpc "
             f"(data: Gillessen+ 2017)", color="#a0a0c0", fontsize=9)
    anno = fig.text(0.95, 0.955, "", color="#f2c14e", fontsize=16, ha="right", weight="bold")
    fig.text(0.95, 0.012, m.FIRMA, color="#6a6a88", fontsize=8, ha="right")
    n_scia = int(1.5 / passo)

    def frame(j):
        for s in stelle:
            x, y = tracce[s]
            punti[s].set_data([x[j]], [y[j]])
            scie[s].set_data(x[max(0, j - n_scia): j + 1], y[max(0, j - n_scia): j + 1])
        anno.set_text(f"{tempi[j]:.1f}")
        if avanzamento and j % 25 == 0:
            avanzamento(j / len(tempi))
        return []

    ff = trova_ffmpeg()
    nome = "_".join(stelle) + "_orbits"
    if ff:
        import matplotlib
        matplotlib.rcParams["animation.ffmpeg_path"] = ff
        f = cartella / f"{nome}.mp4"
        scrittore = anim.FFMpegWriter(fps=fps, codec="libx264", bitrate=-1,
                                      extra_args=["-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "23"])
    else:
        f = cartella / f"{nome}.gif"
        fps = min(fps, 20)
        scrittore = anim.PillowWriter(fps=fps)
    a_ = anim.FuncAnimation(fig, frame, frames=len(tempi), blit=False)
    import os
    import sys
    vecchio = os.environ.get("LD_LIBRARY_PATH")
    if getattr(sys, "frozen", False):          # eseguibile PyInstaller: ffmpeg con le librerie di sistema
        if "LD_LIBRARY_PATH_ORIG" in os.environ:
            os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
        else:
            os.environ.pop("LD_LIBRARY_PATH", None)
    try:
        a_.save(str(f), writer=scrittore, dpi=dpi if ff else 60)
    finally:
        if getattr(sys, "frozen", False):
            if vecchio is None:
                os.environ.pop("LD_LIBRARY_PATH", None)
            else:
                os.environ["LD_LIBRARY_PATH"] = vecchio
    if avanzamento:
        avanzamento(1.0)
    return f


# =============================================================================
# MCMC
# =============================================================================
def disegna_mcmc(fig, res, fs=10):
    """Nuvola dei campioni MCMC nel piano M-R0 con le distribuzioni ai lati (e f_SP se libero).
    Titolo su due righe in alto, titoli dei pannelli corti e margini con constrained_layout:
    con il testo grande della finestra le scritte non si sovrappongono (1.5 del 21/11)."""
    fig.clear()
    fig.set_facecolor(SURF)
    mc = getattr(res, "mcmc", None)
    if not mc:
        fig.text(0.5, 0.5, "No MCMC run yet: press \u00abIncertezze con MCMC\u00bb", ha="center", va="center",
                 fontsize=fs * 1.2, color=INK2)
        return
    fig.set_layout_engine("constrained", h_pad=0.04, w_pad=0.04)
    S, nomi = mc["campioni"], mc["nomi"]
    iM, iR = nomi.index("M"), nomi.index("R0")
    con_f = "fSP" in nomi
    pM, pR = mc["percentili"]["M"], mc["percentili"]["R0"]
    fig.suptitle(f"MCMC: M = {pM[0]:.2f} \u2212{pM[1]:.2f}/+{pM[2]:.2f} million M\u2609\n"
                 f"R\u2080 = {pR[0]:.2f} \u2212{pR[1]:.2f}/+{pR[2]:.2f} kpc\n"
                 f"{mc['n_passi']} steps, acceptance {mc['accettazione'] * 100:.0f} %, "
                 f"~{mc['indipendenti']:.0f} independent samples  \u00b7  {m.FIRMA}",
                 fontsize=fs * 0.9, color=INK, x=0.02, ha="left", linespacing=1.3)
    gs = fig.add_gridspec(2, 3 if con_f else 2, width_ratios=[4, 1.3] + ([2.6] if con_f else []),
                          height_ratios=[1.3, 4])
    ax = fig.add_subplot(gs[1, 0])
    axx = fig.add_subplot(gs[0, 0], sharex=ax)
    axy = fig.add_subplot(gs[1, 1], sharey=ax)
    for a_ in (ax, axx, axy):
        _stile(a_, fs)
    ax.hist2d(S[:, iR], S[:, iM], bins=45, cmap="Blues", cmin=1)
    ax.plot([res.p["R0"]], [res.p["M"]], "+", color=INK, ms=12, mew=2, label="least squares")
    for k, (nome, M, eM, R, eR) in enumerate(m.LETTERATURA):
        ax.plot([R], [M], "s", color=MUTED, ms=5, mfc=SURF, label="published" if k == 0 else None)
    axx.hist(S[:, iR], bins=50, color="#2a78d6", alpha=0.75)
    axy.hist(S[:, iM], bins=50, color="#2a78d6", alpha=0.75, orientation="horizontal")
    axx.tick_params(labelbottom=False, labelleft=False)
    axy.tick_params(labelleft=False, labelbottom=False)
    ax.set_xlabel("R\u2080 (kpc)", fontsize=fs, color=INK)
    ax.set_ylabel("M (million M\u2609)", fontsize=fs, color=INK)
    ax.legend(fontsize=fs * 0.7, frameon=False, loc="upper left")
    if con_f:
        af = fig.add_subplot(gs[:, 2])
        _stile(af, fs)
        jf = nomi.index("fSP")
        af.hist(S[:, jf], bins=50, color="#eb6834", alpha=0.8)
        af.axvline(1, color=INK, lw=1.2, ls="--", label="Einstein (1)")
        af.axvline(0, color=MUTED, lw=1, ls=":", label="Newton (0)")
        af.tick_params(labelleft=False)
        pf = mc["percentili"]["fSP"]
        af.set_title(f"f_SP = {pf[0]:.1f} \u2212{pf[1]:.1f}/+{pf[2]:.1f}", fontsize=fs * 0.9, color=INK, loc="left")
        af.set_xlabel("f_SP", fontsize=fs, color=INK)
        af.legend(fontsize=fs * 0.6, frameon=True, facecolor=SURF, edgecolor="none", framealpha=0.9,
                  loc="upper right")
