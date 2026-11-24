# Icona originale: buco nero con anello di luce, orbita ellittica dorata di S2 con la stella
# vicino al pericentro, piccole stelle, scritta "M●" dorata; fondo blu-viola notte.
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch
import sys
N = int(sys.argv[2]) if len(sys.argv) > 2 else 256
K = 72 / 128
fig = Figure(figsize=(1, 1), dpi=N); FigureCanvasAgg(fig)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
fig.patch.set_alpha(0)
ax.add_patch(FancyBboxPatch((0.03, 0.03), 0.94, 0.94, boxstyle="round,pad=0,rounding_size=0.18",
                            fc="#141233", ec="#2b2766", lw=K))
# alone
yy, xx = np.mgrid[0:1:400j, 0:1:400j]
FX, FY = 0.37, 0.40
r = np.hypot(xx - FX, yy - FY)
alone = np.exp(-((r - 0.12) / 0.07) ** 2) * 0.55
img = np.zeros((400, 400, 4)); img[..., 0] = 1.0; img[..., 1] = 0.62; img[..., 2] = 0.25; img[..., 3] = alone
mask = (np.abs(xx - 0.5) < 0.47) & (np.abs(yy - 0.5) < 0.47)
img[..., 3] *= mask
ax.imshow(img, extent=(0, 1, 0, 1), origin="lower", zorder=1)
rng = np.random.default_rng(7)
for _ in range(45):
    x, y = rng.uniform(0.1, 0.9, 2)
    if np.hypot(x - FX, y - FY) > 0.2:
        ax.plot(x, y, "o", ms=rng.uniform(0.3, 1.3) * K, color="#dcdcff", alpha=rng.uniform(0.4, 0.9), zorder=1)
# orbita (ellisse inclinata, il buco nero in un fuoco)
a, e = 0.30, 0.75
b = a * np.sqrt(1 - e * e)
ang = 28
th = np.radians(ang)
cx, cy = FX + a * e * np.cos(th), FY + a * e * np.sin(th)
ax.add_patch(Ellipse((cx, cy), 2 * a, 2 * b, angle=ang, fc="none", ec="#f2c14e", lw=2.2 * K, zorder=3))
# buco nero e anello di fotoni
ax.add_patch(Circle((FX, FY), 0.085, fc="#ffb347", ec="none", zorder=4, alpha=0.9))
ax.add_patch(Circle((FX, FY), 0.068, fc="#000000", ec="none", zorder=5))
# la stella S2 vicino al pericentro
t_ = np.radians(205)
px, py = cx + a * np.cos(t_) * np.cos(th) - b * np.sin(t_) * np.sin(th), cy + a * np.cos(t_) * np.sin(th) + b * np.sin(t_) * np.cos(th)
ax.plot(px, py, "o", ms=7 * K, color="#bfe3ff", mec="white", mew=0.8 * K, zorder=6)
ax.text(0.9, 0.08, "M●", color="#f2c14e", fontsize=16 * K, ha="right", va="bottom",
        weight="bold", zorder=7)
fig.savefig(sys.argv[1], dpi=N, transparent=True)
