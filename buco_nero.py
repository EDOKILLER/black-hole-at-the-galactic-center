#!/usr/bin/env python3
"""Il buco nero al centro della Galassia - finestra (versione 1.8).

Interfaccia in italiano, risultati (grafici, scheda PDF, CSV) in inglese.
Uso:  python3 buco_nero.py            finestra
      python3 buco_nero.py --autotest  prova completa (dati, calcolo, scheda, finestra) e uscita
(c) 2026 Edoardo Battistel
"""

import datetime as dt
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, font as tkfont, filedialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

QUI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(QUI))
import motore_bn as m  # noqa: E402
import grafici_bn as g  # noqa: E402
import contesto_bn  # noqa: E402

TITOLO = f"Il buco nero al centro della Galassia {m.VERSIONE}"
CLASSE = "BucoNero"            # Tk la trasforma in "Buconero" (StartupWMClass=Buconero)
CONFIG = Path.home() / ".config" / "buco_nero.json"
USCITA_PREDEFINITA = Path.home() / "Scrivania" / "Astronomia" / "Buco_nero"
STELLE = ["S2", "S1", "S4", "S8", "S9", "S12", "S13", "S14", "S17", "S18", "S19", "S21", "S24",
          "S31", "S38", "S54", "S55"]
DIMENSIONI = ["100 %", "125 %", "150 %", "175 %", "200 %"]
# nomi brevi: con il testo al 150-200 % sette linguette lunghe non ci stanno (1.3 del 21/11)
SCHEDE = [("Orbita", g.disegna_orbita), ("Velocità", g.disegna_velocita),
          ("Massa", g.disegna_massa_distanza), ("Residui", g.disegna_residui),
          ("MCMC", g.disegna_mcmc),
          ("Centro", lambda f, r, fs: contesto_bn.disegna_contesto(f, getattr(r, "contesto", None) or [], fs))]
PASSI_MCMC = 40000
# lunghezze dell'MCMC a scelta (1.6): piu' passi = piu' campioni indipendenti, piu' tempo
LUNGHEZZE_MCMC = ["40 000 passi", "100 000 passi", "200 000 passi"]

SFONDO = "#f4f3ef"
INK = "#0b0b0b"
INK2 = "#52514e"


def fonti_italiano(fonti):
    return [f.replace("cached copy", "copia salvata sul PC").replace("copy shipped with the program",
            "copia inclusa nel programma").replace("downloaded from", "scaricata da") for f in fonti]


def virgola(t):
    """Decimali all'italiana (4,34) nei testi della finestra; le date restano come sono."""
    import re
    return re.sub(r"(?<=\d)\.(?=\d)", ",", t)


def leggi_config():
    try:
        import json
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def scrivi_config(c):
    try:
        import json
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(c, indent=1), encoding="utf-8")
    except OSError:
        pass


def ambiente_esterno():
    """Ambiente per i programmi esterni (zenity, xdg-open) con LD_LIBRARY_PATH originale."""
    env = dict(os.environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
    return env


def scegli_cartella(genitore, iniziale):
    if shutil.which("zenity"):
        try:
            r = subprocess.run(["zenity", "--file-selection", "--directory", "--title=Cartella per la scheda",
                                f"--filename={iniziale}/"], capture_output=True, text=True,
                               env=ambiente_esterno(), timeout=600)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            return None
        except Exception:  # noqa: BLE001
            pass
    return filedialog.askdirectory(parent=genitore, initialdir=str(iniziale), title="Cartella per la scheda") or None


def apri(percorso):
    try:
        subprocess.Popen(["xdg-open", str(percorso)], env=ambiente_esterno(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        pass


# =============================================================================
class Finestra(tk.Tk):
    def __init__(self, autotest=False):
        super().__init__(className=CLASSE)
        self.autotest = autotest
        self.title(TITOLO)
        self.configure(bg=SFONDO)
        self.cfg = {} if autotest else leggi_config()
        self.coda = queue.Queue()
        self.risultato = None
        self.occupato = False
        self._animando = False
        self._mcmc_in_corso = False
        self.contesto = None
        self._misura = (0, 0)
        self.uscita = Path(self.cfg.get("uscita", str(USCITA_PREDEFINITA)))
        self._icona()

        scelte = self.cfg.get("stelle") or [self.cfg.get("stella", "S2")]
        self.v_stelle = {st: tk.BooleanVar(value=st in scelte) for st in STELLE}
        self.v_chu = tk.BooleanVar(value=self.cfg.get("chu", False))
        self.v_keck = tk.BooleanVar(value=self.cfg.get("keck2018", False))
        self.v_gr = tk.BooleanVar(value=self.cfg.get("relativita", False))
        self.v_anom = tk.BooleanVar(value=self.cfg.get("anomali", True))
        self.v_naco = tk.BooleanVar(value=self.cfg.get("naco", True))
        self.v_prec = tk.BooleanVar(value=self.cfg.get("precessione", False))
        lung = self.cfg.get("lunghezza_mcmc", LUNGHEZZE_MCMC[0])
        self.v_lung = tk.StringVar(value=lung if lung in LUNGHEZZE_MCMC else LUNGHEZZE_MCMC[0])
        self.v_dim = tk.StringVar(value=self.cfg.get("dimensione", "150 %"))

        self.font_base = tkfont.nametofont("TkDefaultFont")
        self.font_testo = tkfont.nametofont("TkTextFont")
        self.font_fisso = tkfont.nametofont("TkFixedFont")
        self.font_titolo = tkfont.Font(family=self.font_base.actual("family"), weight="bold")
        self.font_linguette = tkfont.Font(family=self.font_base.actual("family"))
        # base del 100 % fissa (13 punti): il carattere predefinito di Tk cambia da un avvio
        # all'altro (13 o 10) e con esso cambiava la dimensione del 150 % (1.2 del 21/11)
        self.dim_base = 13

        self._costruisci()
        self.applica_dimensione()
        if self.cfg.get("geometria") and not autotest:
            self.geometry(self.cfg["geometria"])
        else:
            self.dimensione_iniziale()
        self.protocol("WM_DELETE_WINDOW", self.chiudi)
        self.after(100, self._controlla_coda)
        self.after(300, self.calcola)
        if not autotest:
            self.after(1500, self.carica_contesto)

    # ------------------------------------------------------------------ aspetto
    def _icona(self):
        for p in (QUI / "buco_nero.png", Path.home() / ".local/share/icons/buco_nero.png"):
            if p.exists():
                try:
                    self._img = tk.PhotoImage(file=str(p))
                    self.iconphoto(True, self._img)
                    return
                except tk.TclError:
                    pass

    def dimensione_iniziale(self, frazione=0.88):
        """Finestra grande quanto l'88 % dello schermo (Tk vede lo schermo ingrandito di Ubuntu)."""
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h = int(sw * frazione), int(sh * (frazione - 0.04))
            self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
        except (tk.TclError, TypeError, ValueError):
            self.geometry("1500x950")

    def dpi_grafici(self):
        """dpi tale che il testo dei grafici (10 pt) sia circa l'85 % di quello dell'interfaccia:
        si parte dall'altezza vera della riga, cosi' vale con qualsiasi ingrandimento di Ubuntu."""
        try:
            px = self.font_base.metrics("linespace") / 1.2          # altezza del carattere in pixel
            return max(60.0, min(600.0, px * 0.85 * 72 / 10))
        except (tk.TclError, TypeError, ValueError, ZeroDivisionError):
            return self.pixel_pollice() * self.scala()

    def _colonna_scorrevole(self, padre):
        """Cornice con barra di scorrimento verticale: nessun comando puo' finire sotto il bordo."""
        barra = ttk.Scrollbar(padre, orient="vertical")
        barra.pack(side="right", fill="y")
        tela = tk.Canvas(padre, highlightthickness=0, bg=SFONDO, yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        barra.configure(command=tela.yview)
        dentro = ttk.Frame(tela, padding=(0, 0, 6, 0))
        voce = tela.create_window(0, 0, window=dentro, anchor="nw")
        def aggiorna_barra(*_):
            tela.configure(scrollregion=tela.bbox("all"))
            serve = dentro.winfo_reqheight() > tela.winfo_height() + 2
            if serve and not barra.winfo_ismapped():
                barra.pack(side="right", fill="y", before=tela)
            elif not serve and barra.winfo_ismapped():
                barra.pack_forget()
                tela.yview_moveto(0)
        dentro.bind("<Configure>", aggiorna_barra)
        tela.bind("<Configure>", lambda e: (tela.itemconfigure(voce, width=e.width), aggiorna_barra()))

        def rotella(e):
            if getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0:
                tela.yview_scroll(-2, "units")
            else:
                tela.yview_scroll(2, "units")
        for w in (tela, dentro):
            w.bind("<Button-4>", rotella, add="+")
            w.bind("<Button-5>", rotella, add="+")
            w.bind("<MouseWheel>", rotella, add="+")
        self._tela_sx = tela
        self._barra_sx = barra
        self._dentro_sx = dentro
        return dentro

    def porta_in_vista(self, widget):
        """Scorre la colonna di sinistra finche' il widget e' visibile (se sta li')."""
        try:
            if not str(widget).startswith(str(self._dentro_sx)):
                return
            tot = max(1, self._dentro_sx.winfo_height())
            y = widget.winfo_rooty() - self._dentro_sx.winfo_rooty()
            self._tela_sx.yview_moveto(max(0.0, (y - 20) / tot))
        except (tk.TclError, AttributeError):
            pass

    def larghezza_colonna(self):
        """Colonna di sinistra: 44 caratteri o la riga di pulsanti piu' larga (le etichette che vanno a
        capo non contano: chiederebbero la larghezza che hanno gia'). Il divisore del PanedWindow va
        spostato a mano: dopo la prima disposizione non segue piu' la larghezza richiesta (1.4 del 21/11)."""
        try:
            self.update_idletasks()
            righe = [r.winfo_reqwidth() for r in self._righe_fisse]
            larg = max([self.font_base.measure("0" * 34)] + righe) + 24
            larg = min(larg, int(self.winfo_width() * 0.45)) if self.winfo_width() > 400 else larg
            self._tela_sx.configure(width=larg)
            barra = 0 if not self._barra_sx.winfo_ismapped() else self._barra_sx.winfo_reqwidth()
            self.principale.sashpos(0, larg + barra + 4)
            self._larghezza_voluta = larg
        except (tk.TclError, AttributeError, ValueError):
            pass
        self.adatta_linguette()

    def adatta_linguette(self):
        """Carattere delle linguette che si rimpicciolisce finche' tutte ci stanno (minimo 9 punti)."""
        try:
            self.update_idletasks()
            larghezza = self.nb.winfo_width()
            if larghezza < 100:
                return
            testi = [self.nb.tab(k, "text") for k in range(len(self.nb.tabs()))]
            alt = self.font_base.metrics("linespace")
            st = ttk.Style(self)
            dim = max(9, round(self.font_base.actual("size") * 0.85))
            while True:
                self.font_linguette.configure(size=dim)
                pad = round(self.font_linguette.metrics("linespace") * 0.45)
                serve = sum(self.font_linguette.measure(t) for t in testi) + len(testi) * (2 * pad + 6) + 20
                if serve <= larghezza or dim <= 9:
                    break
                dim -= 1
            st.configure("TNotebook.Tab", padding=(pad, round(alt * 0.2)), font=self.font_linguette)
            self._linguette_servono = serve
        except (tk.TclError, AttributeError):
            pass

    def _spunta(self, padre, testo, var):
        """Spunta con un'etichetta che va a capo (il testo dei Checkbutton di Tk non va a capo)."""
        riga = ttk.Frame(padre)
        riga.pack(fill="x", anchor="w", pady=1)
        c = ttk.Checkbutton(riga, variable=var)
        c.pack(side="left", anchor="n")
        l = ttk.Label(riga, text=testo, wraplength=1, justify="left")
        l.pack(side="left", fill="x", expand=True, anchor="w")
        self._a_capo(l)
        l.bind("<Button-1>", lambda e: var.set(not var.get()))
        return c

    def pixel_pollice(self):
        """Pixel di Tk per pollice (con l'ingrandimento di Ubuntu sono ~2 per punto, non 1)."""
        try:
            v = float(self.winfo_fpixels("1i"))
            return v if 50 < v < 600 else 96.0
        except (tk.TclError, TypeError, ValueError):
            return 96.0

    def scala(self):
        try:
            return int(self.v_dim.get().split()[0]) / 100
        except ValueError:
            return 1.5

    def applica_dimensione(self, *_):
        s = self.scala()
        n = max(8, round(self.dim_base * s))
        for f in (self.font_base, self.font_testo, tkfont.nametofont("TkMenuFont"),
                  tkfont.nametofont("TkHeadingFont"), tkfont.nametofont("TkCaptionFont")):
            f.configure(size=n)
        self.font_fisso.configure(size=n)
        self.font_titolo.configure(size=round(n * 1.25))
        alt = self.font_base.metrics("linespace")
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", font=self.font_base, background=SFONDO, foreground=INK)
        st.configure("TButton", padding=(round(alt * 0.6), round(alt * 0.3)))
        st.configure("TCheckbutton", indicatorsize=round(alt * 0.8), padding=round(alt * 0.15), background=SFONDO)
        st.configure("TCombobox", arrowsize=round(alt * 0.9), padding=round(alt * 0.2))
        st.configure("Vertical.TScrollbar", arrowsize=round(alt * 0.9), width=round(alt * 0.9))
        self.font_linguette.configure(size=max(8, round(n * 0.85)))
        st.configure("TNotebook.Tab", padding=(round(alt * 0.45), round(alt * 0.2)), font=self.font_linguette)
        st.configure("TLabel", background=SFONDO)
        st.configure("TFrame", background=SFONDO)
        st.configure("TLabelframe", background=SFONDO)
        st.configure("TLabelframe.Label", background=SFONDO, font=self.font_titolo)
        self.option_add("*TCombobox*Listbox.font", self.font_base)
        self.testo.configure(font=self.font_testo)
        self.lista_dim.configure(font=self.font_base)
        self.lista_lung.configure(font=self.font_base)
        self.cfg["dimensione"] = self.v_dim.get()
        self.larghezza_colonna()
        self.after(250, self.larghezza_colonna)
        self.ridisegna()

    # ---------------------------------------------------------------- struttura
    def _costruisci(self):
        principale = ttk.PanedWindow(self, orient="horizontal")
        principale.pack(fill="both", expand=True, padx=8, pady=8)
        self.principale = principale
        self._righe_fisse = []           # righe di pulsanti: decidono la larghezza della colonna

        contenitore = ttk.Frame(principale)
        principale.add(contenitore, weight=1)
        sx = self._colonna_scorrevole(contenitore)
        dx = ttk.Frame(principale)
        principale.add(dx, weight=3)

        f3 = ttk.Frame(sx)
        self._righe_fisse.append(f3)
        f3.pack(fill="x", pady=(0, 4))
        ttk.Label(f3, text="Dimensione testo:").pack(side="left")
        self.lista_dim = ttk.Combobox(f3, textvariable=self.v_dim, values=DIMENSIONI, state="readonly", width=7)
        self.lista_dim.pack(side="left", padx=6)
        self.lista_dim.bind("<<ComboboxSelected>>", self.applica_dimensione)

        f = ttk.LabelFrame(sx, text="Calcolo", padding=8)
        f.pack(fill="x", pady=(8, 4))
        l = ttk.Label(f, text="Stelle (con più di una: massa e distanza in comune):", wraplength=1)
        l.pack(fill="x")
        self._a_capo(l)
        griglia = ttk.Frame(f)
        griglia.pack(fill="x", pady=(2, 4))
        for k, st in enumerate(STELLE):
            ttk.Checkbutton(griglia, text=st, variable=self.v_stelle[st]).grid(row=k // 4, column=k % 4, sticky="w",
                                                                              padx=(0, 8))
        pre = ttk.Frame(f)
        self._righe_fisse.append(pre)
        pre.pack(fill="x", pady=(0, 6))
        ttk.Button(pre, text="Solo S2", command=lambda: self.scegli_stelle(["S2"])).pack(side="left")
        ttk.Button(pre, text="S2 + S38 + S55", command=lambda: self.scegli_stelle(["S2", "S38", "S55"])) \
            .pack(side="left", padx=6)
        for testo, var in (("Aggiungi le velocità Keck di Chu 2018 (solo S2)", self.v_chu),
                           ("Aggiungi le velocità Keck fino al 2018, pericentro compreso (Do 2019, solo S2)",
                            self.v_keck),
                           ("Includi il redshift relativistico nel calcolo", self.v_gr),
                           ("Escludi i punti anomali (oltre 4 σ)", self.v_anom),
                           ("Errori NACO × 1,42 (come Gillessen)", self.v_naco),
                           ("Precessione relativistica libera (fattore f_SP; 1 = Einstein, 0 = Newton)",
                            self.v_prec)):
            self._spunta(f, testo, var)
        b = ttk.Frame(f)
        self._righe_fisse.append(b)
        b.pack(fill="x", pady=(6, 0))
        self.b_calcola = ttk.Button(b, text="Calcola", command=self.calcola)
        self.b_calcola.pack(side="left")
        ttk.Button(b, text="Riscarica i dati", command=lambda: self.calcola(riscarica=True)).pack(side="left", padx=6)
        rl = ttk.Frame(f)
        self._righe_fisse.append(rl)
        rl.pack(fill="x", pady=(6, 0))
        ttk.Label(rl, text="MCMC:").pack(side="left")
        self.lista_lung = ttk.Combobox(rl, textvariable=self.v_lung, values=LUNGHEZZE_MCMC, state="readonly",
                                       width=max(len(x) for x in LUNGHEZZE_MCMC) + 2)
        self.lista_lung.pack(side="left", padx=6)
        self.b_mcmc = ttk.Button(f, text="Incertezze con MCMC", command=self.avvia_mcmc)
        self.b_mcmc.pack(fill="x", pady=(6, 0))
        self.l_mcmc = ttk.Label(f, text="", foreground=INK2, wraplength=1)
        self.l_mcmc.pack(fill="x")
        self._a_capo(self.l_mcmc)
        self.b_rs = ttk.Button(f, text="Misura il redshift relativistico", command=self.avvia_redshift)
        self.b_rs.pack(fill="x", pady=(6, 0))
        self.l_rs = ttk.Label(f, text="", foreground=INK2, wraplength=1)
        self.l_rs.pack(fill="x")
        self._a_capo(self.l_rs)

        f2 = ttk.LabelFrame(sx, text="Scheda", padding=8)
        f2.pack(fill="x", pady=4)
        self.b_salva = ttk.Button(f2, text="Salva scheda (PDF, PNG, CSV)", command=self.salva)
        self.b_salva.pack(fill="x")
        self.b_anim = ttk.Button(f2, text="Crea animazione delle orbite", command=self.anima)
        self.b_anim.pack(fill="x", pady=(6, 0))
        self.l_anim = ttk.Label(f2, text="", foreground=INK2, wraplength=1)
        self.l_anim.pack(fill="x")
        self._a_capo(self.l_anim)
        r2 = ttk.Frame(f2)
        self._righe_fisse.append(r2)
        r2.pack(fill="x", pady=(6, 0))
        ttk.Button(r2, text="Cambia cartella", command=self.cambia_cartella).pack(side="left")
        ttk.Button(r2, text="Apri cartella", command=lambda: apri(self.uscita)).pack(side="left", padx=6)
        self.l_cartella = ttk.Label(f2, text="", foreground=INK2, wraplength=1)
        self.l_cartella.pack(fill="x", pady=(6, 0))
        self._a_capo(self.l_cartella)
        self._mostra_cartella()

        ttk.Label(sx, text=m.FIRMA, foreground=INK2).pack(anchor="w", pady=(12, 0))

        # risultati (prima scheda) e grafici
        self.nb = ttk.Notebook(dx)
        self.nb.pack(fill="both", expand=True)
        f4 = ttk.Frame(self.nb, padding=4)
        self.nb.add(f4, text="Risultati")
        barra = ttk.Scrollbar(f4, orient="vertical")
        self.testo = tk.Text(f4, wrap="word", relief="flat", bg="#fcfcfb", fg=INK, padx=16, pady=12,
                             yscrollcommand=barra.set, height=10, width=10, spacing1=2, spacing3=4)
        barra.configure(command=self.testo.yview)
        barra.pack(side="right", fill="y")
        self.testo.pack(fill="both", expand=True)
        self.testo.tag_configure("titolo", font=self.font_titolo, spacing1=8, spacing3=6)
        self.testo.tag_configure("piccolo", foreground=INK2)
        self.scrivi("Carico i dati e calcolo l'orbita…")
        self.grafici = []
        self._pulsanti_grafici = []
        for nome, funz in SCHEDE:
            fr = ttk.Frame(self.nb)
            self.nb.add(fr, text=nome)
            fig = Figure(figsize=(8, 6))
            canvas = FigureCanvasTkAgg(fig, master=fr)
            barra_mpl = NavigationToolbar2Tk(canvas, fr, pack_toolbar=False)   # nascosta: icone minuscole
            pul = ttk.Frame(fr)
            pul.pack(side="bottom", fill="x", pady=4)          # prima del grafico: non finisce sotto il bordo
            comandi = (("Vista iniziale", barra_mpl.home), ("Indietro", barra_mpl.back),
                       ("Avanti", barra_mpl.forward), ("Sposta", barra_mpl.pan),
                       ("Ingrandisci", barra_mpl.zoom),
                       ("Salva immagine", lambda f=fig, n=nome: self.salva_immagine(f, n)))
            for c in range(3):
                pul.columnconfigure(c, weight=1, uniform="pul")
            for k, (t, cmd) in enumerate(comandi):
                bt = ttk.Button(pul, text=t, command=cmd)
                bt.grid(row=k // 3, column=k % 3, sticky="ew", padx=3, pady=2)
                if not self.grafici:
                    self._pulsanti_grafici.append(bt)
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self.grafici.append((fig, canvas, funz, barra_mpl))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.after(60, lambda: self.ridisegna(solo_visibile=True)))
        self.nb.bind("<Configure>", lambda e: self.after_idle(self.adatta_linguette))

    def pulsanti_importanti(self):
        return [self.b_calcola, self.b_mcmc, self.b_rs, self.b_salva, self.b_anim] + self._pulsanti_grafici

    def _a_capo(self, w):
        """Le etichette vanno a capo seguendo la larghezza della finestra."""
        w.bind("<Configure>", lambda e: w.configure(wraplength=max(50, e.width - 4)))

    def _mostra_cartella(self):
        p = str(self.uscita)
        casa = str(Path.home())
        if p.startswith(casa):
            p = "~" + p[len(casa):]
        self.l_cartella.configure(text=f"Cartella: {p}")

    # ------------------------------------------------------------------ testo
    def scrivi(self, t, tag=None, pulisci=True):
        self.testo.configure(state="normal")
        if pulisci:
            self.testo.delete("1.0", "end")
        self.testo.insert("end", t + "\n", tag)
        self.testo.configure(state="disabled")
        self.testo.see("end")

    def mostra_risultato(self, r):
        if len(getattr(r, "stelle", []) or []) > 1:
            return self.mostra_risultato_multi(r)
        p, e, dv = r.p, r.err, r.derivati
        pr = m.previsione_pericentro(r, 0)
        fmt = g._fmt
        self.scrivi(f"Sagittarius A* pesato con {r.stella}", "titolo")
        righe = [
            f"Massa: {fmt(p['M'], e['M'])} milioni di masse solari",
            f"Distanza dal Sole: {fmt(p['R0'], e['R0'])} kpc ({p['R0'] * 3.2616:.1f} mila anni luce)",
            f"Massa e distanza sono legate (correlazione {r.corr_M_R0:.2f}): lungo la «valle» degli errori "
            f"la massa va come R0 alla {g.pendenza_M_R0(r):.1f}.",
            "",
            f"Periodo {fmt(p['P'], e['P'])} anni, eccentricità {fmt(p['e'], e['e'])}, "
            f"semiasse {dv['a'][0] * 1000:.1f} mas = {dv['a'][0] * p['R0'] * 1000:.0f} UA.",
            f"Pericentro {fmt(p['tp'], e['tp'])} ({m.anno_in_data(p['tp'])}) a {dv['rp'][0]:.0f} UA "
            f"= {dv['rp_rs']:.0f} raggi di Schwarzschild, velocità {dv['vp'][0]:.0f} km/s "
            f"({dv['vp'][0] / m.C_KMS * 100:.1f} % della luce).",
            f"Prossimi pericentri previsti: {dv['peri'][0]:.2f} ({m.anno_in_data(dv['peri'][0])}) e "
            f"{dv['peri'][1]:.2f} ({m.anno_in_data(dv['peri'][1])}).",
            f"Previsto dalla relatività al pericentro 2018: redshift {pr['redshift_gr']:.0f} km/s, "
            f"precessione {dv['precessione_arcmin']:.1f}′ per orbita.",
            "",
            f"Dati usati: {r.n_a} posizioni e {r.n_v} velocità radiali"
            + (f" (esclusi {len(r.esclusi_a)} + {len(r.esclusi_v)} punti anomali)." if r.esclusi_a or r.esclusi_v
               else ", nessun punto escluso."),
            f"Qualità: χ² = {r.chi2:.1f} con {r.dof} gradi di libertà (ridotto {r.chi2_rid:.2f}).",
        ]
        if r.err["R0"] > 1.0 or r.n_v < 6:
            righe.append("Attenzione: con poche velocità radiali la distanza (e quindi la massa) è poco "
                         "vincolata; il risultato serve solo come controllo.")
        for t in righe:
            self.scrivi(virgola(t), pulisci=False)
        self.scrivi("\nConfronto con i valori pubblicati:", "titolo", pulisci=False)
        for nome, M, eM, R, eR in m.LETTERATURA:
            self.scrivi(virgola(f"{nome}: M = {M:.3f} ± {eM:.3f}, R0 = {R:.3f} ± {eR:.3f}"), pulisci=False)
        self.scrivi("\nFonti: " + "; ".join(fonti_italiano(r.dati.fonti)), "piccolo", pulisci=False)

    def mostra_risultato_multi(self, r):
        p, e = r.p, r.err
        fmt = g._fmt
        self.scrivi(f"Sagittarius A* pesato con {', '.join(r.stelle)} insieme", "titolo")
        righe = [f"Massa: {fmt(p['M'], e['M'])} milioni di masse solari",
                 f"Distanza dal Sole: {fmt(p['R0'], e['R0'])} kpc ({p['R0'] * 3.2616:.1f} mila anni luce)",
                 f"Massa, distanza e sistema di riferimento sono in comune; ogni stella ha i suoi 6 elementi "
                 f"dell'orbita. Qualità: χ² = {r.chi2:.1f} con {r.dof} gradi di libertà (ridotto {r.chi2_rid:.2f}).",
                 ""]
        for s, rs in r.sub.items():
            q, qe = rs.p, rs.err
            prossimo = q["tp"] + q["P"] * max(1, int((2026.9 - q["tp"]) / q["P"]) + 1)
            righe.append(f"{s}: periodo {fmt(q['P'], qe['P'])} anni, eccentricità {fmt(q['e'], qe['e'])}, "
                         f"pericentro {q['tp']:.2f}, prossimo {prossimo:.2f}; {rs.n_a} posizioni e "
                         f"{rs.n_v} velocità" + (f", {len(rs.esclusi_a) + len(rs.esclusi_v)} punti esclusi"
                                                  if rs.esclusi_a or rs.esclusi_v else "") + ".")
        for t in righe:
            self.scrivi(virgola(t), pulisci=False)
        ctl = getattr(r, "controllo", None)
        if ctl:
            self.scrivi("\nControllo: la massa di ogni stella da sola (distanza fissata a quella comune)", "titolo",
                        pulisci=False)
            for s, (M, eM) in ctl[0].items():
                self.scrivi(virgola(f"{s}: {fmt(M, eM)} milioni di masse solari"), pulisci=False)
            giudizio = ("le stelle sono d'accordo" if ctl[1] < 2 * len(ctl[0]) + 3
                        else "le stelle NON sono d'accordo: c'è tensione")
            self.scrivi(virgola(f"χ² della coerenza = {ctl[1]:.1f} per {len(ctl[0])} stelle: {giudizio}."),
                        pulisci=False)
        self.scrivi("\nConfronto con i valori pubblicati:", "titolo", pulisci=False)
        for nome, M, eM, R, eR in m.LETTERATURA:
            self.scrivi(virgola(f"{nome}: M = {M:.3f} ± {eM:.3f}, R0 = {R:.3f} ± {eR:.3f}"), pulisci=False)
        self.scrivi("\nFonti: " + "; ".join(fonti_italiano(r.dati.fonti)), "piccolo", pulisci=False)

    def mostra_extra(self, r):
        """Righe in piu' (italiano): precessione libera e MCMC."""
        fmt = g._fmt
        righe = []
        if "fSP" in r.p:
            righe.append(f"Precessione relativistica: f_SP = {fmt(r.p['fSP'], r.err.get('fSP', 0))} "
                         "(1 = relatività generale, 0 = Newton). Con i dati fino a metà 2016 non si può ancora "
                         "distinguere: GRAVITY l'ha misurata (1,10 ± 0,19) solo con le posizioni del pericentro 2018.")
        mc = getattr(r, "mcmc", None)
        if mc:
            p = mc["percentili"]
            righe.append(f"MCMC ({mc['n_passi']} passi, accettazione {mc['accettazione'] * 100:.0f} %, circa "
                         f"{mc['indipendenti']:.0f} campioni indipendenti): M = {p['M'][0]:.3f} −{p['M'][1]:.3f} "
                         f"/ +{p['M'][2]:.3f}, R0 = {p['R0'][0]:.3f} −{p['R0'][1]:.3f} / +{p['R0'][2]:.3f}"
                         + (f", f_SP = {p['fSP'][0]:.2f} −{p['fSP'][1]:.2f} / +{p['fSP'][2]:.2f}" if "fSP" in p
                            else "") + " (mediana e intervallo del 68 %).")
            rp, rh = mc.get("rhat_principali"), mc.get("rhat_max")
            if rp is not None and rp == rp:
                giud = lambda x: ("convergente" if x < 1.01 else "accettabile" if x < 1.05  # noqa: E731
                                  else "non ancora convergente: meglio un MCMC più lungo")
                t = f"Convergenza dell'MCMC (indice R di Gelman-Rubin, 1 = perfetta): per M, R0{' e f_SP' if 'fSP' in mc['rhat'] else ''} " \
                    f"{rp:.3f} ({giud(rp)})."
                peg = mc.get("rhat_peggiore", "")
                if rh >= 1.05 and peg not in ("M", "R0", "fSP"):
                    t += (f" Il parametro meno convergente è {peg} ({rh:.2f}): riguarda solo la forma di un'orbita "
                          "(per un'orbita vista quasi di faccia, come S38, gli angoli Ω e ω si scambiano tra loro), "
                          "non la massa e la distanza.")
                righe.append(t)
        rs = getattr(r, "redshift", None)
        if rs:
            u, e = rs["upsilon"], rs["errore"]
            righe.append(
                f"Redshift relativistico misurato (profilo del χ², {rs['n_rv_dopo_2016']} velocità dopo metà 2016): "
                f"fattore {u:.2f} ± {e:.2f} (1 = relatività generale, 0 = Newton). Newton escluso a "
                f"{abs(rs['sigma_da_newton']):.1f} σ, Einstein a {abs(rs['sigma_da_einstein']):.1f} σ. "
                "Confronto: GRAVITY 2019 1,04 ± 0,05, Do et al. 2019 0,88 ± 0,17, che usavano "
                "anche le posizioni del 2017–2018 (qui le posizioni finiscono nel 2016).")
        v = getattr(r, "verifica_1pn", None)
        if v:
            for s, x in v.items():
                giudizio = ("trascurabile" if x["diff_pos_max_mas"] < 0.5 * x["errore_pos_mas"]
                            and x["diff_vel_max_kms"] < 0.5 * x["errore_vel_kms"] else "da tenere d'occhio")
                righe.append(
                    f"Verifica relativistica di {s} (orbita 1PN integrata, {x['t_min']:.0f}–{x['t_max']:.0f}): "
                    f"la precessione approssimata del programma sbaglia al massimo di {x['diff_pos_max_mas']:.2f} mas "
                    f"e {x['diff_vel_max_kms']:.1f} km/s ({giudizio}: gli errori tipici delle misure sono "
                    f"{x['errore_pos_mas']:.2f} mas e {x['errore_vel_kms']:.0f} km/s). L'effetto intero della "
                    f"relatività in questi anni vale {x['gr_pos_max_mas']:.2f} mas e {x['gr_vel_max_kms']:.1f} km/s.")
        if righe:
            self.scrivi("\nIn più", "titolo", pulisci=False)
            for t in righe:
                self.scrivi(virgola(t), pulisci=False)

    # ---------------------------------------------------------------- MCMC e contesto
    def passi_mcmc(self):
        """Numero di passi scelto nella tendina («100 000 passi» -> 100000)."""
        try:
            return int(self.v_lung.get().split(" passi")[0].replace(" ", ""))
        except ValueError:
            return PASSI_MCMC

    def avvia_mcmc(self, passi=None, attendi=False):
        if self.risultato is None or self._mcmc_in_corso or self.occupato:
            return None
        if passi is None:
            passi = self.passi_mcmc()
        r = self.risultato
        self._mcmc_in_corso = True
        self.b_mcmc.state(["disabled"])
        self.b_calcola.state(["disabled"])
        n = len(getattr(r, "stelle", None) or [1])
        minuti = max(1, round(passi * 1.4e-3 * n / 60))
        self.l_mcmc.configure(text=f"MCMC: parto (circa {minuti} minut{'o' if minuti == 1 else 'i'} con "
                                   f"{n} stell{'a' if n == 1 else 'e'}; «Calcola» resta spento fino alla fine)…")
        esito = {}

        def lavoro():
            try:
                mc = m.mcmc(r, n_passi=passi, avanzamento=lambda f: self.coda.put(("mcmc", f"MCMC: {f * 100:.0f} %")))
                esito["mcmc"] = mc
                self.coda.put(("mcmc_fatto", (r, mc)))
            except Exception as e:  # noqa: BLE001
                esito["errore"] = e
                self.coda.put(("mcmc_errore", f"{type(e).__name__}: {e}"))

        th = threading.Thread(target=lavoro, daemon=True)
        th.start()
        if attendi:
            th.join()
        return esito

    def avvia_redshift(self, attendi=False):
        """Profilo del chi2 per il fattore del redshift (12 adattamenti) in sottofondo."""
        if self.risultato is None or self._mcmc_in_corso or self.occupato:
            return None
        r = self.risultato
        opz = r.opzioni
        if not (opz.con_keck2018 and "S2" in (list(opz.stelle) or [opz.stella])):
            self.l_rs.configure(text="Per misurare il redshift servono le velocità del 2018: spunta «Aggiungi le "
                                     "velocità Keck fino al 2018» e premi «Calcola».")
            return None
        self._mcmc_in_corso = True
        for b in (self.b_rs, self.b_mcmc, self.b_calcola):
            b.state(["disabled"])
        n = len(getattr(r, "stelle", None) or [1])
        self.l_rs.configure(text=f"Redshift: 12 calcoli con il fattore fisso (circa {15 * n} secondi)…")
        esito = {}

        def lavoro():
            try:
                rs = m.misura_redshift(opz, [QUI / "dati"], log=lambda t: self.coda.put(("log_quieto", t)),
                                       avanzamento=lambda f: self.coda.put(("rs", f"Redshift: {f * 100:.0f} %")))
                esito["redshift"] = rs
                self.coda.put(("rs_fatto", (r, rs)))
            except Exception as e:  # noqa: BLE001
                esito["errore"] = e
                self.coda.put(("rs_errore", f"{type(e).__name__}: {e}"))

        th = threading.Thread(target=lavoro, daemon=True)
        th.start()
        if attendi:
            th.join()
        return esito

    def carica_contesto(self, attendi=False):
        """Immagini del centro galattico da SkyView (una volta sola, poi dalla cache)."""
        esito = {}

        def lavoro():
            try:
                esito["img"] = contesto_bn.scarica_immagini(log=lambda t: self.coda.put(("log_quieto", t)))
            except Exception as e:  # noqa: BLE001
                esito["img"] = []
                esito["errore"] = e
            self.coda.put(("contesto", esito["img"]))

        th = threading.Thread(target=lavoro, daemon=True)
        th.start()
        if attendi:
            th.join()
        return esito

    # ---------------------------------------------------------------- animazione
    def anima(self, cartella=None, passo=0.05, attendi=False):
        if self.risultato is None or self._animando:
            return None
        r = self.risultato
        dest = Path(cartella) if cartella else self.uscita / f"{'_'.join(r.stelle)}_{dt.datetime.now():%Y-%m-%d_%H%M}"
        self._animando = True
        self.b_anim.state(["disabled"])
        self.l_anim.configure(text="Preparo l'animazione…")
        esito = {}

        def avanzamento(f):
            self.coda.put(("anim", f"Animazione: {f * 100:.0f} %"))

        def lavoro():
            try:
                esito["file"] = g.animazione(r, dest, passo=passo, avanzamento=avanzamento)
                self.coda.put(("anim_fatta", esito["file"]))
            except Exception as e:  # noqa: BLE001
                esito["errore"] = e
                self.coda.put(("anim_errore", f"{type(e).__name__}: {e}"))

        th = threading.Thread(target=lavoro, daemon=True)
        th.start()
        if attendi:
            th.join()
        return esito

    # ---------------------------------------------------------------- calcolo
    def stelle_scelte(self):
        return [st for st in STELLE if self.v_stelle[st].get()]

    def scegli_stelle(self, lista):
        for st, v in self.v_stelle.items():
            v.set(st in lista)

    def opzioni(self):
        st = self.stelle_scelte() or ["S2"]
        return m.Opzioni(stella=st[0], stelle=tuple(st) if len(st) > 1 else (), con_chu=self.v_chu.get(),
                         con_keck2018=self.v_keck.get(), relativita=self.v_gr.get(), escludi_anomali=self.v_anom.get(),
                         scala_naco=self.v_naco.get(), precessione=self.v_prec.get())

    def calcola(self, riscarica=False):
        if self.occupato or self._mcmc_in_corso:
            return
        self.occupato = True
        self.b_calcola.state(["disabled"])
        opz = self.opzioni()
        st = list(opz.stelle) or [opz.stella]
        if len(st) > 8:
            self.occupato = False
            self.b_calcola.state(["!disabled"])
            self.messaggio("Troppe stelle", "Si possono adattare insieme al massimo 8 stelle.")
            return
        self.scrivi(f"Calcolo l'orbita di {', '.join(st)}"
                    + (" (insieme: può volerci qualche secondo in più)…" if len(st) > 1 else "…"))
        extra = [QUI / "dati"]

        def lavoro():
            try:
                log = lambda t: self.coda.put(("log", t))  # noqa: E731
                r = m.calcola(opz, extra, riscarica, log)
                self.coda.put(("fatto", r))
            except Exception as e:  # noqa: BLE001
                self.coda.put(("errore", f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"))

        threading.Thread(target=lavoro, daemon=True).start()

    def _controlla_coda(self):
        try:
            while True:
                tipo, x = self.coda.get_nowait()
                if tipo == "log":
                    self.scrivi(x, "piccolo", pulisci=False)
                elif tipo == "log_quieto":
                    print(x, flush=True)
                elif tipo == "fatto":
                    self.occupato = False
                    self.b_calcola.state(["!disabled"])
                    self.risultato = x
                    x.contesto = self.contesto
                    self.l_mcmc.configure(text="")
                    self.l_rs.configure(text="")
                    self.mostra_risultato(x)
                    self.mostra_extra(x)
                    self.nb.select(0)
                    self.ridisegna()
                elif tipo == "mcmc":
                    self.l_mcmc.configure(text=x)
                elif tipo in ("mcmc_fatto", "mcmc_errore"):
                    self._mcmc_in_corso = False
                    self.b_mcmc.state(["!disabled"])
                    self.b_calcola.state(["!disabled"])
                    if tipo == "mcmc_fatto" and self.risultato is not None:
                        r, mc = x
                        r.mcmc = mc
                        if r is not self.risultato:
                            self.l_mcmc.configure(text="L'MCMC è finito, ma il calcolo è stato rifatto nel frattempo: "
                                                       "il risultato è stato scartato. Premi di nuovo il pulsante.")
                        if r is self.risultato:
                            pM, pR = mc["percentili"]["M"], mc["percentili"]["R0"]
                            self.l_mcmc.configure(text=virgola(
                                f"MCMC: M = {pM[0]:.2f} −{pM[1]:.2f}/+{pM[2]:.2f}, "
                                f"R0 = {pR[0]:.2f} −{pR[1]:.2f}/+{pR[2]:.2f}"))
                            self.mostra_risultato(r)
                            self.mostra_extra(r)
                            self.nb.select(5)
                            self.after(80, self.ridisegna)
                    elif tipo == "mcmc_errore":
                        self.l_mcmc.configure(text="L'MCMC non è riuscito.")
                        self.messaggio("Errore", f"L'MCMC non è riuscito:\n{x}")
                elif tipo == "rs":
                    self.l_rs.configure(text=x)
                elif tipo in ("rs_fatto", "rs_errore"):
                    self._mcmc_in_corso = False
                    for b in (self.b_rs, self.b_mcmc, self.b_calcola):
                        b.state(["!disabled"])
                    if tipo == "rs_fatto":
                        r, rs = x
                        r.redshift = rs
                        self.l_rs.configure(text=virgola(f"Redshift: fattore {rs['upsilon']:.2f} ± {rs['errore']:.2f} "
                                                         "(1 = Einstein, 0 = Newton)"))
                        if r is self.risultato:
                            self.mostra_risultato(r)
                            self.mostra_extra(r)
                            self.nb.select(0)
                    else:
                        self.l_rs.configure(text="La misura del redshift non è riuscita.")
                        self.messaggio("Errore", f"La misura del redshift non è riuscita:\n{x}")
                elif tipo == "contesto":
                    self.contesto = x
                    if self.risultato is not None:
                        self.risultato.contesto = x
                        self.ridisegna()
                elif tipo == "anim":
                    self.l_anim.configure(text=x)
                elif tipo in ("anim_fatta", "anim_errore"):
                    self._animando = False
                    self.b_anim.state(["!disabled"])
                    if tipo == "anim_fatta":
                        self.l_anim.configure(text=f"Animazione salvata: {x.name}")
                        self.messaggio("Animazione pronta", f"Ho salvato l'animazione in:\n{x}"
                                       + ("" if x.suffix == ".mp4" else "\n\n(ffmpeg non c'è: è una GIF animata.)"),
                                       apri_dopo=x.parent)
                    else:
                        self.l_anim.configure(text="L'animazione non è riuscita.")
                        self.messaggio("Errore", f"Non sono riuscito a creare l'animazione:\n{x}")
                elif tipo == "errore":
                    self.occupato = False
                    self.b_calcola.state(["!disabled"])
                    self.scrivi("Il calcolo non è riuscito.", "titolo")
                    self.scrivi(x, "piccolo", pulisci=False)
        except queue.Empty:
            pass
        self.after(150, self._controlla_coda)

    def misura_grafici(self):
        """Misura dell'area dei grafici, presa dalla scheda visibile (una scheda nascosta misura 1×1);
        tutte le schede hanno la stessa misura. Si ricorda l'ultima buona."""
        try:
            self.update_idletasks()
            for fig, canvas, *_ in self.grafici:
                w = canvas.get_tk_widget()
                if w.winfo_ismapped() and w.winfo_width() > 50 and w.winfo_height() > 50:
                    self._misura = (w.winfo_width(), w.winfo_height())
                    break
        except (tk.TclError, AttributeError):
            pass
        return getattr(self, "_misura", (0, 0))

    def ridisegna(self, solo_visibile=False):
        if not getattr(self, "grafici", None) or self.risultato is None:
            return
        s = self.scala()
        try:
            vis = self.nb.index(self.nb.select()) - 1      # la scheda 0 sono i risultati
        except tk.TclError:
            vis = -1
        larg, alt = self.misura_grafici()
        for k, (fig, canvas, funz, _) in enumerate(self.grafici):
            if solo_visibile and k != vis:
                continue
            dpi = self.dpi_grafici()
            if larg > 50 and alt > 50:
                # area piccola (200 %): figura almeno 7 × 4,5 pollici, se no le scritte si accavallano
                dpi = min(dpi, larg / 7.0, alt / 4.5)
            fig.set_dpi(dpi)
            if larg > 50 and alt > 50:
                fig.set_size_inches(larg / dpi, alt / dpi, forward=False)
            try:
                funz(fig, self.risultato, 10)
            except Exception as e:  # noqa: BLE001
                fig.clear()
                fig.text(0.05, 0.5, f"Errore nel grafico: {e}", wrap=True)
            canvas.draw_idle()

    # ------------------------------------------------------------------ salva
    def cambia_cartella(self):
        c = scegli_cartella(self, self.uscita)
        if c:
            self.uscita = Path(c)
            self.cfg["uscita"] = str(self.uscita)
            self._mostra_cartella()

    def salva(self, cartella=None):
        if self.risultato is None:
            self.messaggio("Nessun risultato", "Prima serve un calcolo riuscito.")
            return None
        r = self.risultato
        dest = Path(cartella) if cartella else self.uscita / f"{'_'.join(r.stelle)}_{dt.datetime.now():%Y-%m-%d_%H%M}"
        try:
            file = g.scheda(r, dest) + m.salva_csv(r, dest)
        except Exception as e:  # noqa: BLE001
            self.messaggio("Errore", f"Non sono riuscito a salvare la scheda:\n{type(e).__name__}: {e}")
            return None
        if not cartella:
            self.messaggio("Scheda salvata", f"Ho salvato {len(file)} file in:\n{dest}\n\n"
                           + "\n".join(f.name for f in file), apri_dopo=dest)
        return file

    def salva_immagine(self, fig, nome):
        self.uscita.mkdir(parents=True, exist_ok=True)
        quali = "_".join(getattr(self.risultato, "stelle", None) or self.stelle_scelte() or ["S2"])
        f = self.uscita / f"{quali}_{nome.replace(' ', '_').replace('à', 'a')}.png"
        dpi = fig.get_dpi()
        fig.savefig(f, dpi=150)
        fig.set_dpi(dpi)
        for fg, can, *_ in self.grafici:
            if fg is fig:
                can.draw_idle()
        self.messaggio("Immagine salvata", f"Salvata in:\n{f}")

    def messaggio(self, titolo, testo, apri_dopo=None):
        """Finestra di messaggio ridimensionabile, con testo che va a capo."""
        if self.autotest:
            print(f"[messaggio] {titolo}: {testo.splitlines()[0]}")
            return
        w = tk.Toplevel(self)
        w.title(titolo)
        w.configure(bg=SFONDO)
        w.transient(self)
        t = tk.Text(w, wrap="word", relief="flat", bg=SFONDO, fg=INK, font=self.font_testo, padx=12, pady=10,
                    height=min(14, testo.count("\n") + 3), width=60)
        t.insert("1.0", testo)
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)
        b = ttk.Frame(w)
        b.pack(fill="x", pady=8, padx=8)
        if apri_dopo:
            ttk.Button(b, text="Apri cartella", command=lambda: (apri(apri_dopo), w.destroy())).pack(side="right", padx=4)
        ttk.Button(b, text="Chiudi", command=w.destroy).pack(side="right")

    def chiudi(self):
        self.cfg.update(stelle=self.stelle_scelte(), chu=self.v_chu.get(), keck2018=self.v_keck.get(), relativita=self.v_gr.get(),
                        anomali=self.v_anom.get(), naco=self.v_naco.get(), precessione=self.v_prec.get(), lunghezza_mcmc=self.v_lung.get(),
                        geometria=self.geometry())
        scrivi_config(self.cfg)
        self.destroy()


# =============================================================================
def autotest():
    """Prova completa: dati, calcolo, scheda e finestra vera con i grafici."""
    esiti = []

    def ok(nome, cond, extra=""):
        esiti.append((nome, bool(cond)))
        print(f"[{'ok' if cond else 'ERRORE'}] {nome} {extra}", flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="buco_nero_prova_"))
    try:
        d = m.carica_dati("S2", cartelle_extra=[QUI / "dati"])
        ok("dati S2", d.n_a >= 140 and d.n_v >= 40, f"({d.n_a} posizioni, {d.n_v} velocità)")
        pub = m.orbita_pubblicata("S2", [QUI / "dati"])
        ok("orbita pubblicata", pub and abs(pub["Per"] - 16.0) < 0.1)
        r = m.adatta(d, m.Opzioni(), pub)
        ok("massa", 3.8 < r.p["M"] < 4.9, f"({r.p['M']:.3f} ± {r.err['M']:.3f} milioni)")
        ok("distanza", 7.6 < r.p["R0"] < 9.0, f"({r.p['R0']:.3f} ± {r.err['R0']:.3f} kpc)")
        ok("pericentro 2018", abs(r.derivati["peri"][0] - 2018.38) < 0.15, f"({r.derivati['peri'][0]:.3f})")
        f = g.scheda(r, tmp) + m.salva_csv(r, tmp)
        ok("scheda", all(x.exists() and x.stat().st_size > 200 for x in f), f"({len(f)} file)")
        d2 = m.carica_dati("S2", True, cartelle_extra=[QUI / "dati"])
        r2 = m.adatta(d2, m.Opzioni(con_chu=True), pub)
        ok("con Chu 2018", d2.n_v > d.n_v and 3.8 < r2.p["M"] < 4.9, f"({d2.n_v} velocità, M {r2.p['M']:.3f})")
        r3 = m.adatta(m.carica_dati("S1", cartelle_extra=[QUI / "dati"]), m.Opzioni(stella="S1"),
                      m.orbita_pubblicata("S1", [QUI / "dati"]))
        ok("stella S1", 2 < r3.p["M"] < 8, f"(M {r3.p['M']:.2f} ± {r3.err['M']:.2f})")
        r4 = m.calcola(m.Opzioni(stelle=("S2", "S38", "S55")), [QUI / "dati"])
        ok("S2 + S38 + S55 insieme", 3.8 < r4.p["M"] < 4.6 and 7.6 < r4.p["R0"] < 8.6 and len(r4.sub) == 3,
           f"(M {r4.p['M']:.3f} ± {r4.err['M']:.3f}, R0 {r4.p['R0']:.3f} ± {r4.err['R0']:.3f})")
        ok("coerenza delle masse", r4.controllo and r4.controllo[1] < 9,
           "(" + ", ".join(f"{k} {v[0]:.2f}" for k, v in r4.controllo[0].items()) + f"; χ² {r4.controllo[1]:.1f})")
        f4 = g.scheda(r4, tmp / "tre") + m.salva_csv(r4, tmp / "tre")
        ok("scheda a più stelle", all(x.exists() for x in f4), f"({len(f4)} file)")
        v1 = getattr(r4, "verifica_1pn", None) or {}
        ok("verifica con l'orbita 1PN integrata", len(v1) == 3 and v1["S2"]["diff_pos_max_mas"] < 0.5,
           "; ".join(f"{s} {x['diff_pos_max_mas']:.2f} mas / {x['diff_vel_max_kms']:.1f} km/s" for s, x in v1.items()))
        d6 = m.carica_dati("S2", cartelle_extra=[QUI / "dati"], con_keck2018=True)
        ok("velocità Keck fino al 2018 (Do 2019)", d6.n_v > 100 and d6.tv.max() > 2018.5,
           f"({d6.n_v} velocità, l'ultima nel {d6.tv.max():.2f})")
        rs6 = m.misura_redshift(m.Opzioni(con_keck2018=True), [QUI / "dati"])
        ok("redshift relativistico misurato", -0.5 < rs6["upsilon"] < 2.0 and rs6["errore"] < 0.6,
           f"(fattore {rs6['upsilon']:.2f} ± {rs6['errore']:.2f}; Newton escluso a {rs6['sigma_da_newton']:.1f} σ)")
        r5 = m.calcola(m.Opzioni(precessione=True), [QUI / "dati"])
        ok("precessione libera", "fSP" in r5.p and abs(r5.p["M"] - r.p["M"]) < 0.3,
           f"(f_SP {r5.p['fSP']:.2f} ± {r5.err['fSP']:.2f}; con i dati fino al 2016 non è ancora vincolata)")
        mc = m.mcmc(r, n_passi=4000)
        pM = mc["percentili"]["M"]
        ok("MCMC (breve)", abs(pM[0] - r.p["M"]) < 0.3 and 0.05 < mc["accettazione"] < 0.7,
           f"(M {pM[0]:.2f} −{pM[1]:.2f}/+{pM[2]:.2f}, accettazione {mc['accettazione'] * 100:.0f} %)")
        ok("convergenza R̂ calcolata", mc.get("rhat_principali", 0) > 0.9, f"(R̂ M, R0 {mc.get('rhat_principali', 0):.3f})")
        import numpy as _np
        prova = _np.arange(12, dtype=">f4").reshape(3, 4)
        testa = "".join(c.ljust(80) for c in ["SIMPLE  =                    T", "BITPIX  =                  -32",
                                              "NAXIS   =                    2", "NAXIS1  =                    4",
                                              "NAXIS2  =                    3", "END"]).ljust(2880)
        img, _ = contesto_bn.leggi_fits(testa.encode() + prova.tobytes().ljust(2880, b"\0"))
        ok("lettore FITS", img.shape == (3, 4) and img[2, 3] == 11)
        # 2MASS da IRSA (1.6): lettura della VOTable e mosaico di tessere finte con i WCS veri
        vot = ('<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE><TABLE>'
               '<FIELD name="band"/><FIELD name="download"/><TABLEDATA><TR><TD>K</TD><TD>u?name=k.fits</TD></TR>'
               '</TABLEDATA></TABLE></RESOURCE></VOTABLE>')
        rv = contesto_bn.leggi_votable(vot)
        ok("lettura VOTable", rv == [{"band": "K", "download": "u?name=k.fits"}])
        ra_g, dec_g = contesto_bn._griglia()
        righe_t, tess = [], []
        for a0, d0 in ((266.4512855, -29.11216722), (266.4512972, -28.84272277), (266.3156764, -29.106523)):
            righe_t.append({"band": "K", "type": "A", "dataset": "asky", "download": "u", "naxis": "512 1024",
                            "crval": f"{a0} {d0}", "crpix": "256.5 512.5", "scale": "-2.777777845e-04 2.777777845e-04",
                            "crota2": "0"})
            h = {"CRVAL1": a0, "CRVAL2": d0, "CRPIX1": 256.5, "CRPIX2": 512.5, "CDELT1": -2.777777845e-04,
                 "CDELT2": 2.777777845e-04, "MAGZP": 20}
            px, py = contesto_bn.pixel_sin(_np.array(contesto_bn.SGR_A[0]), _np.array(contesto_bn.SGR_A[1]), a0, d0,
                                           256.5, 512.5, h["CDELT1"], h["CDELT2"])
            yy, xx = _np.mgrid[0:1024, 0:512]
            tess.append((100 * _np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / 50.0), h))
        scelte_t, cop_t = contesto_bn.scegli_tessere(righe_t, ra_g, dec_g, "K")
        mos = contesto_bn.mosaico(tess, ra_g, dec_g)
        iy, ix = _np.unravel_index(_np.nanargmax(mos), mos.shape)
        ok("mosaico 2MASS (Sgr A* al centro)", abs(ix - 300) <= 2 and abs(iy - 300) <= 2 and cop_t > 0.9,
           f"(picco in {ix}, {iy}; copertura {cop_t * 100:.0f} %)")
        try:
            cont = contesto_bn.scarica_immagini(log=lambda t: print("[info]", t, flush=True), tentativi=2)
            print(f"[info] Immagini del centro: {len(cont)} su 2 (" + (", ".join(c[2] for c in cont)) + ")", flush=True)
            r.contesto = cont
        except Exception as e:  # noqa: BLE001
            print(f"[info] SkyView non raggiunto: {e}", flush=True)
        r.mcmc = mc
        f5 = g.scheda(r, tmp / "mcmc")
        ok("scheda con MCMC", any("mcmc" in x.name for x in f5), f"({len(f5)} file)")
        fa = g.animazione(r4, tmp / "anim", passo=1.0)
        ok("animazione", fa.exists() and fa.stat().st_size > 10000,
           f"({fa.suffix[1:].upper()}, {fa.stat().st_size // 1024} kB; ffmpeg: {g.trova_ffmpeg() or 'no, GIF'})")
    except Exception as e:  # noqa: BLE001
        ok("motore", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    try:
        w = Finestra(autotest=True)
        stato = {"n": 0}

        def controlla():
            stato["n"] += 1
            if w.risultato is None and stato["n"] < 480:          # fino a 2 minuti
                w.after(250, controlla)
                return
            ok("finestra con calcolo", w.risultato is not None)
            w.dimensione_iniziale()
            w.update()
            w.larghezza_colonna()
            w.update()
            print(f"[info] schermo visto da Tk {w.winfo_screenwidth()}x{w.winfo_screenheight()}, "
                  f"finestra {w.winfo_width()}x{w.winfo_height()}", flush=True)
            w.nb.select(1)                  # i pulsanti dei grafici si vedono nella scheda «Orbita»
            w.update()
            coperti = []
            for b in w.pulsanti_importanti():
                w.porta_in_vista(b)
                w.update()
                x = b.winfo_rootx() + b.winfo_width() // 2
                y = b.winfo_rooty() + b.winfo_height() // 2
                sopra = w.winfo_containing(x, y)
                if sopra is None or not str(sopra).startswith(str(b)):
                    coperti.append(f"{b.cget('text')} (sopra c'è {sopra})")
                if b.winfo_height() < 10 or b.winfo_ismapped() == 0:
                    coperti.append(f"{b.cget('text')} non visibile")
            ok("pulsanti visibili", not coperti, "; ".join(coperti))
            ok("testo al 150 % (base 13 punti)", w.font_base.actual("size") == 20 or w.font_base.actual("size") == -20,
               f"(carattere {w.font_base.actual('size')}, riga {w.font_base.metrics('linespace')} pixel)")
            ok("dpi dei grafici", 50 < w.dpi_grafici() < 600,
               f"({w.dpi_grafici():.0f} dpi; riga di testo {w.font_base.metrics('linespace')} pixel; "
               f"Tk {w.pixel_pollice():.0f} pixel per pollice)")
            for k in range(len(SCHEDE) + 1):
                w.nb.select(k)
                w.update()
            w.grafici[0][1].draw()
            ok("grafici nella finestra", all(len(fg.axes) > 0 for fg, *_ in w.grafici[:4]))
            w.update()
            w.adatta_linguette()
            serve = getattr(w, "_linguette_servono", 0)
            ok("linguette leggibili", serve <= w.nb.winfo_width() or w.font_linguette.actual("size") <= 9,
               f"({serve} su {w.nb.winfo_width()} pixel, carattere {w.font_linguette.actual('size')})")
            fg0, cv0 = w.grafici[0][0], w.grafici[0][1]
            w.nb.select(1)
            w.update()
            w.ridisegna()
            w.update()
            lw = cv0.get_tk_widget().winfo_width()
            lf = fg0.get_size_inches()[0] * fg0.get_dpi()
            ok("grafico grande quanto la scheda", lw < 60 or abs(lf - lw) < 0.05 * lw + 3,
               f"(figura {lf:.0f} pixel, scheda {lw} pixel)")
            w.v_dim.set("200 %")
            w.applica_dimensione()
            w.update()
            ok("dimensione testo 200 %", w.font_base.actual("size") >= 2 * (w.dim_base - 1))
            w.update()
            w.adatta_linguette()
            serve = getattr(w, "_linguette_servono", 0)
            ok("linguette leggibili al 200 %", serve <= w.nb.winfo_width() or w.font_linguette.actual("size") <= 9,
               f"({serve} su {w.nb.winfo_width()} pixel, carattere {w.font_linguette.actual('size')})")
            righe = max(r.winfo_reqwidth() for r in w._righe_fisse)
            ok("colonna di sinistra larga abbastanza", w._tela_sx.winfo_width() >= min(righe, w.winfo_width() * 0.45) - 4,
               f"(colonna {w._tela_sx.winfo_width()}, pulsanti {righe} pixel, finestra {w.winfo_width()})")
            w.nb.select(1)
            w.update()
            fuori = [b.cget("text") for b in w._pulsanti_grafici
                     if b.winfo_rooty() + b.winfo_height() > w.winfo_rooty() + w.winfo_height() + 2
                     or b.winfo_rootx() + b.winfo_width() > w.winfo_rootx() + w.winfo_width() + 2]
            ok("pulsanti dei grafici dentro la finestra al 200 %", not fuori, ", ".join(fuori))
            try:
                t = w._tela_sx
                alto = t.bbox("all")[3] if t.bbox("all") else 0
                print(f"[info] colonna di sinistra al 200 %: {alto} pixel di contenuto, {t.winfo_height()} visibili"
                      + (" (si scorre)" if alto > t.winfo_height() else ""), flush=True)
            except Exception:  # noqa: BLE001
                pass
            ok("salva dalla finestra", w.salva(tmp / "finestra"))
            w.grafici[0][3].zoom()
            w.grafici[0][3].home()
            ok("pulsanti del grafico", True)
            # secondo giro: tre stelle insieme dalla finestra
            w.scegli_stelle(["S2", "S38", "S55"])
            w.risultato = None
            w.calcola()
            stato["n"] = 0
            w.after(500, controlla_tre)

        def controlla_tre():
            stato["n"] += 1
            if w.risultato is None and stato["n"] < 480:
                w.after(250, controlla_tre)
                return
            ok("finestra con tre stelle", w.risultato is not None and len(w.risultato.sub) == 3)
            for k in range(len(SCHEDE) + 1):
                w.nb.select(k)
                w.update()
            ok("grafici a più stelle", all(len(fg.axes) > 0 for fg, *_ in w.grafici[:4]))
            senza = w.avvia_redshift()
            w.coda.put(("rs_fatto", (w.risultato, {"upsilon": 0.5, "errore": 0.28, "griglia": [], "chi2": [],
                                                   "sigma_da_newton": 1.8, "sigma_da_einstein": -1.8,
                                                   "n_rv_dopo_2016": 28})))
            w._controlla_coda()
            ok("redshift nella finestra", senza is None and getattr(w.risultato, "redshift", None) is not None,
               str(w.l_rs.cget("text"))[:60])
            w.v_lung.set("100 000 passi")
            ok("tendina della lunghezza dell'MCMC", w.passi_mcmc() == 100000, str(w.passi_mcmc()))
            w.v_lung.set(LUNGHEZZE_MCMC[0])
            em = w.avvia_mcmc(passi=3000, attendi=True)
            ok("MCMC dalla finestra", bool(em and em.get("mcmc")), repr(em.get("errore", "")) if em else "(non partito)")
            w._controlla_coda()
            ok("risultato dell'MCMC nella finestra", getattr(w.risultato, "mcmc", None) is not None
               and not w._mcmc_in_corso, str(w.l_mcmc.cget("text"))[:80])
            esito = w.anima(tmp / "anim_finestra", passo=1.0, attendi=True)
            ok("animazione dalla finestra", bool(esito and esito.get("file") and esito["file"].exists()),
               repr(esito.get("errore", "")) if esito else "(non partita)")
            w.after(1500, w.destroy)

        w.after(500, controlla)
        w.mainloop()
    except Exception as e:  # noqa: BLE001
        ok("finestra", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    shutil.rmtree(tmp, ignore_errors=True)
    n_ok = sum(1 for _, v in esiti if v)
    print(f"\nAutotest: {n_ok}/{len(esiti)} " + ("TUTTO OK" if n_ok == len(esiti) else "CI SONO ERRORI"))
    return 0 if n_ok == len(esiti) else 1


def main():
    if "--autotest" in sys.argv:
        sys.exit(autotest())
    if "--calcola" in sys.argv:
        k = sys.argv.index("--calcola")
        m.main(["--dati", str(QUI / "dati")] + sys.argv[k + 1:])
        return
    Finestra().mainloop()


if __name__ == "__main__":
    main()
