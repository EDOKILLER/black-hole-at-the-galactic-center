<p align="center"><img src="buco_nero.png" width="128" alt="The Black Hole at the Centre of the Galaxy icon"></p>

# The Black Hole at the Centre of the Galaxy

*Weigh Sgr A* yourself: mass and distance of the Milky Way's black hole from the orbits of the S stars* — original Italian name: «Il buco nero al centro della Galassia»

Fits Keplerian orbits to the published positions and radial velocities of the S stars around Sgr A* (Gillessen et al. 2017, plus Keck velocities from Chu et al. 2018 and Do et al. 2019) and measures the mass of the black hole and the distance to the Galactic Centre. It includes the Rømer delay, an optional relativistic redshift and Schwarzschild precession, outlier rejection, a joint fit of several stars, an MCMC with the Gelman–Rubin index, a 1PN orbit check and an MP4 animation.

## Features

* Single-star or multi-star fits with a star-by-star consistency check
* Adaptive Metropolis MCMC (numpy only) with uncertainties and convergence index
* *Measure the relativistic redshift* button (χ² profile of the redshift factor)
* Galactic Centre card with DSS2 and 2MASS J/H/Ks images (SkyView, IRSA)
* Offline copies of the VizieR tables in `dati/`; PDF/PNG card and CSV/JSON in English

## Tested on real data

S2 alone: M = 4.34 ± 0.26 million M☉, R0 = 8.32 ± 0.26 kpc (Gillessen+2017: 4.28 / 8.32; GRAVITY 2022: 4.297 / 8.277). Seven stars: 4.17 ± 0.16 / 8.05 ± 0.14. Relativistic redshift of S2 with velocities up to 2018.7: f = 0.49 ± 0.28.

> **Language note.** The interface is in **Italian** (large, adjustable text); plots, PDF/PNG cards and scientific output are in **English**. Code comments are in Italian. The original Italian guide is [`LEGGIMI.txt`](LEGGIMI.txt).

**Version:** 1.8 (2026-11-21). **Status:** Stable: 1.8 built, installed and tested.

## Quick start

Requirements: Python 3.10+ (tested with Python 3.14 on Ubuntu) with `tkinter` (Ubuntu: `sudo apt install python3-tk`).

```bash
git clone https://github.com/EDOKILLER/black-hole-at-the-galactic-center.git
cd black-hole-at-the-galactic-center
python3 -m pip install -r requirements.txt

python3 buco_nero.py --autotest
python3 motore_bn.py --stella S2        # command-line fit
python3 buco_nero.py        # opens the window
```

### Standalone executable

`bash crea_eseguibile_ubuntu.sh` builds a single-file executable with PyInstaller in a temporary virtual environment, runs the self-test, and adds the program with its icon to the application menu and the desktop (first time on GNOME: right-click → *Allow launching*). `installa.sh` installs it as a script instead, without compiling.

The build scripts were written for the author's machine: check the paths at the top before running them.

## Data sources and acknowledgements

Data are downloaded at run time from public services. If you publish results, please follow their acknowledgement policies:

* [VizieR catalogue service, CDS, Strasbourg (the Harvard mirror is used)](https://vizier.cds.unistra.fr/)
* [NASA/GSFC SkyView virtual observatory](https://skyview.gsfc.nasa.gov/)
* [NASA/IPAC Infrared Science Archive: 2MASS, WISE, Spitzer, Euclid, Planck](https://irsa.ipac.caltech.edu/)

The tables in `dati/` are copies of VizieR catalogues (Gillessen et al. 2009, ApJ 707, L114; Gillessen et al. 2017, ApJ 837, 30; Chu et al. 2018, ApJ 854, 12; Chu et al. 2023, ApJ 948, 94 — table 4 contains the Keck velocities of Do et al. 2019, Science 365, 664). Please cite the original papers.

This project is independent and not endorsed by any of these institutions.

## License

Code: [BSD 3-Clause](LICENSE) © 2026 Edoardo Battistel. You can use, modify and redistribute it, also commercially, as long as you keep the copyright notice; the author's name may not be used to promote derived works without permission. If you use it in research, see [`CITATION.cff`](CITATION.cff).

---
Part of a series of astronomy programs by Edoardo Battistel — see also [X-rays from Black Holes](https://github.com/EDOKILLER/x-rays-from-black-holes) and the other repositories on [this profile](https://github.com/EDOKILLER?tab=repositories).
