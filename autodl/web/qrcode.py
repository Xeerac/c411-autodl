"""QR code en SVG, sans bibliothèque (pour la double authentification : lien otpauth://).

Mode octet, correction d'erreur M, versions 1 à 10 (jusqu'à 213 octets : largement assez pour un lien
otpauth). Algorithme de la norme ISO/IEC 18004, dans la lignée de l'implémentation de référence de
Project Nayuki. Vérifié dans les tests contre une bibliothèque indépendante.
"""
from __future__ import annotations

# version -> (octets de correction par bloc, [(nombre de blocs, octets de données par bloc), ...]) en niveau M
BLOCKS = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
         9: [6, 26, 46], 10: [6, 28, 50]}
EC_M = 0  # bits de format du niveau M


def _mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _mul(coef, factor)
    return result


def _capacity(version: int) -> int:
    return sum(n * k for n, k in BLOCKS[version][1])


def _codewords(data: bytes, version: int) -> list[int]:
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in reversed(range(length)))

    put(0b0100, 4)  # mode octet
    put(len(data), 8 if version < 10 else 16)
    for b in data:
        put(b, 8)
    cap = _capacity(version) * 8
    put(0, min(4, cap - len(bits)))  # terminateur
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    ec_len, groups = BLOCKS[version]
    divisor = _rs_divisor(ec_len)
    blocks, pos = [], 0
    for count, size in groups:
        for _ in range(count):
            block = words[pos:pos + size]
            pos += size
            blocks.append((block, _rs_remainder(block, divisor)))
    out = []
    for i in range(max(len(b) for b, _ in blocks)):  # données entrelacées, puis corrections entrelacées
        out.extend(b[i] for b, _ in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(e[i] for _, e in blocks)
    return out


class _Grid:
    def __init__(self, version: int):
        self.version = version
        self.size = version * 4 + 17
        self.mod = [[False] * self.size for _ in range(self.size)]
        self.func = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.mod[y][x] = dark
        self.func[y][x] = True

    def draw_functions(self) -> None:
        n = self.size
        for i in range(n):  # lignes de synchronisation
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # repères de position et séparateurs
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.set(x, y, d not in (2, 4))
        pos = ALIGN[self.version]
        last = len(pos) - 1
        for i, cx in enumerate(pos):  # repères d'alignement
            for j, cy in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)  # réservé, réécrit après le masque
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def draw_format(self, mask: int) -> None:
        n = self.size
        data = EC_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = [(bits >> i) & 1 == 1 for i in range(15)]
        for i in range(6):
            self.set(8, i, bit[i])
        self.set(8, 7, bit[6])
        self.set(8, 8, bit[7])
        self.set(7, 8, bit[8])
        for i in range(9, 15):
            self.set(14 - i, 8, bit[i])
        for i in range(8):
            self.set(n - 1 - i, 8, bit[i])
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit[i])
        self.set(8, n - 8, True)  # module toujours sombre

    def draw_data(self, words: list[int]) -> None:
        n, i = self.size, 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.func[y][x] and i < len(words) * 8:
                        self.mod[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        tests = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
                 lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
                 lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
                 lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)
        f = tests[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.func[y][x] and f(x, y):
                    self.mod[y][x] = not self.mod[y][x]

    def penalty(self) -> int:
        n, m, score = self.size, self.mod, 0
        lines = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        for line in lines:  # suites de 5 modules ou plus de même couleur
            run, prev = 0, None
            for v in line:
                run = run + 1 if v == prev else 1
                prev = v
                if run == 5:
                    score += 3
                elif run > 5:
                    score += 1
            s = "".join("1" if v else "0" for v in line)  # motifs ressemblant aux repères
            for pat in ("10111010000", "00001011101"):
                start = s.find(pat)
                while start != -1:
                    score += 40
                    start = s.find(pat, start + 1)
        for y in range(n - 1):  # carrés 2×2 de même couleur
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in m)
        score += abs(dark * 20 - n * n * 10) // (n * n) * 10  # équilibre clair / sombre
        return score


def matrix(text: str, mask: int | None = None, version: int | None = None) -> list[list[bool]]:
    """Matrice du QR code (True = module sombre), sans la marge."""
    data = text.encode("utf-8")
    if version is None:
        version = next((v for v in BLOCKS if _capacity(v) - (2 if v < 10 else 3) >= len(data)), None)
        if version is None:
            raise ValueError("texte trop long pour le QR code")
    words = _codewords(data, version)
    best = None
    for m in ([mask] if mask is not None else range(8)):
        g = _Grid(version)
        g.draw_functions()
        g.draw_data(words)
        g.apply_mask(m)
        g.draw_format(m)
        score = g.penalty() if mask is None else 0
        if best is None or score < best[0]:
            best = (score, g)
    return best[1].mod


def svg(text: str, border: int = 4) -> str:
    """QR code en SVG autonome (fond blanc, modules noirs) : lisible par tous les téléphones."""
    m = matrix(text)
    n = len(m) + 2 * border
    path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(m) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
