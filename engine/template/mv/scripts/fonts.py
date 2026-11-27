"""Display and mono typefaces for a video, fetched once and shared by every project.

A video's type should not be whichever face the system happens to have. This fetches openly licensed
(SIL Open Font License 1.1) faces from the public google/fonts repository at one pinned commit, with plain
anonymous GET requests, checks each file against a pinned SHA-256, and keeps it with its license text in
~/.cache/music-video/fonts/. The OFL allows use in released, commercial videos.

In fx.py:
    from fonts import face
    DISPLAY = face("Bricolage Grotesque")        # a (path, 0) spec for ov.font, downloaded on first use
    ov.font(DISPLAY, 120, axes={"wght": 800, "wdth": 75})   # variable faces take axes

From the shell:
    .venv/bin/python mv/scripts/fonts.py                  list the faces with their character and axes
    .venv/bin/python mv/scripts/fonts.py "Rubik Mono One" fetch one and print its path
    .venv/bin/python mv/scripts/fonts.py --sheet mv/review/fonts.jpg "WORDS FROM THE SONG"
                                                           every face setting those words, to choose by eye

Any other OFL family in that repository works too: face("ofl/<folder>/<File>.ttf") fetches that file at
the pinned commit (no checksum is pinned for it; the commit fixes its content).

The list is a starting range, not a house style: pick by what the song's world is made of (a ticket stub, a
truck door, a cassette inlay, a shop sign), and write the face into the video's history entry so the next
video starts elsewhere (SKILL.md Phase 3).
"""
import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache" / "music-video" / "fonts"
REPO_REV = "5026800714d07231937d92eb4cceabf06e05d74e"   # github.com/google/fonts
BASE = f"https://raw.githubusercontent.com/google/fonts/{REPO_REV}/"

# name: (folder under ofl/, file, sha256, what it is, variable axes)
FACES = {
    "Anton": ("anton", "Anton-Regular.ttf", "a4ba3a92350ebb031da0cb47630ac49eb265082ca1bc0450442f4a83ab947cab",
              "tall condensed poster sans; tabloid headlines, protest signs", ""),
    "Archivo Black": ("archivoblack", "ArchivoBlack-Regular.ttf",
                      "dd9a89a019b4849f66ab75455fe7bdf931311042cbb0f0f97acc061539703180",
                      "wide heavy grotesque; packaging, sports print", ""),
    "Alfa Slab One": ("alfaslabone", "AlfaSlabOne-Regular.ttf",
                      "28664afa698a3393bd5a29eec750230a0645c5301d62200e5f2d3a027fb2299d",
                      "fat slab; wanted posters, boxing bills, crates", ""),
    "Bangers": ("bangers", "Bangers-Regular.ttf", "4160a7311de9342674cce9160cde9fcbb30f48190397d86ff1b70b455af65824",
                "comic-book capitals; sound effects, cartoons", ""),
    "Righteous": ("righteous", "Righteous-Regular.ttf",
                  "2ffb3fe5c27d7e6571210b800448c4e234e651b46c6b4426c1bb567e5341348a",
                  "rounded deco; 1930s travel posters, diners", ""),
    "Rye": ("rye", "Rye-Regular.ttf", "b7edee5e615ae1b6b07e9d030c1309152bf3672a0e8a2a46293e273730f5adba",
            "western woodtype; saloons, rodeo bills", ""),
    "UnifrakturMaguntia": ("unifrakturmaguntia", "UnifrakturMaguntia-Book.ttf",
                           "d64afc0547059dd2e4a78da48bda0aba0a9901be58c7f8c201a8b2b6b4492cc8",
                           "blackletter; mastheads, metal, tattoo, beer labels", ""),
    "Bricolage Grotesque": ("bricolagegrotesque", "BricolageGrotesque[opsz,wdth,wght].ttf",
                            "413e7357809ddd12fd80a96a8a396de0e401638d4acd3cb3e37532f0472ac682",
                            "quirky grotesque with ink traps; zines, indie record sleeves",
                            "opsz 12-96, wdth 75-100, wght 200-800"),
    "Anybody": ("anybody", "Anybody[wdth,wght].ttf", "b184bd7e6ca8348bbaecec98951565729d7e89b7872d4898a1f9981342b5b64c",
                "squared sans from very narrow to very wide; sport, tech, rave flyers",
                "wdth 50-150, wght 100-900"),
    "Besley": ("besley", "Besley[wght].ttf", "71f352d8859c787631a0978161d48497a72caa69dcae6996d6712a564df86c1e",
               "sturdy Victorian slab serif; newspapers, timetables, ledgers", "wght 400-900"),
    "Zilla Slab": ("zillaslab", "ZillaSlab-Bold.ttf", "4ec3a04a4eef37074b42ef542e4d874e13646668cfe65256e0bf100441cf8719",
                   "sharp modern slab; manuals, typewritten reports", ""),
    "Gabarito": ("gabarito", "Gabarito[wght].ttf", "8650e2bd7747f7d74619fd7aecbcb0309e6f37b7964024f3fb15ae4833b67ca5",
                 "friendly geometric; apps, toys, bright pop", "wght 400-900"),
    "Funnel Display": ("funneldisplay", "FunnelDisplay[wght].ttf",
                       "b4151c9c4b7b07eb74320096b4ff4156cca8821f5adfab34af9fd9a2d6c1179d",
                       "clean display sans with cut corners; product launches, signage", "wght 300-800"),
    "Big Shoulders Display": ("bigshouldersdisplay", "BigShouldersDisplay[wght].ttf",
                              "60e208dc276a1c35fc5b62e94f9fb959c40c11783a9eb7548175c14b1fbeb720",
                              "condensed civic capitals; railways, stadiums, city signs", "wght 100-900"),
    "Bebas Neue": ("bebasneue", "BebasNeue-Regular.ttf", "08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73",
                   "condensed capitals; film titles, gym walls (common: use with a reason)", ""),
    "Abril Fatface": ("abrilfatface", "AbrilFatface-Regular.ttf",
                      "5971d4a3758a922a9fedc7f6fb825a96341a2e718c45a4b2c9a6b417c8c4dbe9",
                      "high-contrast fat face; fashion covers, theatre bills", ""),
    "Monoton": ("monoton", "Monoton-Regular.ttf", "951c4cea65ffede784a7c9672feec5d329a7e1e12216c42d53ecf36c90d04dea",
                "triple-line deco capitals; marquees, disco, casinos", ""),
    "Rubik Mono One": ("rubikmonoone", "RubikMonoOne-Regular.ttf",
                       "b22624b6a36e543e942106edfccd198c50b57b65b924bfe02a6f0a5699429e6b",
                       "chunky rounded monospace capitals; arcade, toys, crates", ""),
    "Unbounded": ("unbounded", "Unbounded[wght].ttf", "323b511be380c8d474ef030686b71aedde501f8d9cd46da558b7c40454372c3f",
                  "very wide rounded sans; club nights, crypto, space", "wght 200-900"),
    "Bowlby One": ("bowlbyone", "BowlbyOne-Regular.ttf", "c46a806d7b51fd4987e5f0be449fe40a944cb407e43290ce1cdeed029a8cdc1d",
                   "heavy friendly grotesque; market stalls, fruit boxes", ""),
    "Shrikhand": ("shrikhand", "Shrikhand-Regular.ttf", "8ba32f6d6a96fb8dbc92fc1acfbc4d2123d5348063d89b2c3dd784e7afcb81af",
                  "fat italic with swing; hand-painted shopfronts, film posters", ""),
    "Six Caps": ("sixcaps", "SixCaps.ttf", "7b54a46671722fb670647c9c3951e6e618b6a9d876fc5d9ae34dfd311628ae5a",
                 "extremely condensed capitals; a whole line as one tall word", ""),
    "Staatliches": ("staatliches", "Staatliches-Regular.ttf",
                    "8395212aa4c6c3534bd39a745d956305ff080c3f3ed73ba61e4fbaae951e55cc",
                    "Bauhaus-style capitals; exhibition posters, schools", ""),
    "Black Ops One": ("blackopsone", "BlackOpsOne-Regular.ttf",
                      "282a825b5f294377387e3969f765408157dbea8da0f5d0aae68c6bc704b145b3",
                      "stencil; shipping containers, military crates", ""),
    "Fascinate": ("fascinate", "Fascinate-Regular.ttf", "2f3d4e1d3b1f58ba4700eba078c07d9f05d9f39513f6d29b0306ddc007bd7fec",
                  "deco script capitals; cocktail bars, cinema lobbies", ""),
    "Chivo Mono": ("chivomono", "ChivoMono[wght].ttf", "725256f30b7b1b25dd001a96ff8d4a23773197bb886cd847a97ff8eabc9c1d9d",
                   "mono with grotesque warmth; receipts, tickets", "wght 100-900"),
    "JetBrains Mono": ("jetbrainsmono", "JetBrainsMono[wght].ttf",
                       "48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda",
                       "code mono; terminals, editors", "wght 100-800"),
    "Red Hat Mono": ("redhatmono", "RedHatMono[wght].ttf", "253377ac29ccce89cb1b5fb297c69812ffe993b0c436322b3656323ff30fd14f",
                     "round friendly mono; dashboards, labels", "wght 300-700"),
    "Martian Mono": ("martianmono", "MartianMono[wdth,wght].ttf",
                     "c3467843ec1c2574b05fbcfd7147c7bfbcf63ddca8fc2bcb9d117f1bfb1b22e7",
                     "wide square mono; instruments, sci-fi readouts", "wdth 75-112.5, wght 100-800"),
}


def _get(url, out, sha256=None):
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    print(f"downloading {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit(f"checksum mismatch for {url}; nothing was kept")
    tmp.write_bytes(data)
    tmp.replace(out)
    return out


def face(name):
    """A (path, 0) font spec for ov.font: a face from FACES by name, or "ofl/<folder>/<File>.ttf" for any
    other OFL family in google/fonts at the pinned commit. Downloaded on first use, with its license."""
    if name in FACES:
        folder, file, sha, _, _ = FACES[name]
    elif name.startswith("ofl/") and name.count("/") == 2 and name.lower().endswith((".ttf", ".otf")):
        _, folder, file = name.split("/")
        sha = None
    else:
        raise KeyError(f"{name!r} is not in fonts.FACES; run fonts.py for the list, or give 'ofl/<folder>/<File>.ttf'")
    d = CACHE / folder
    _get(BASE + "ofl/" + folder + "/OFL.txt", d / "OFL.txt")
    return (str(_get(BASE + "ofl/" + folder + "/" + urllib.parse.quote(file), d / file, sha)), 0)


def sheet(out, text):
    from PIL import Image, ImageDraw, ImageFont
    rows = []
    for name in FACES:
        path, _ = face(name)
        f = ImageFont.truetype(path, 64)
        rows.append((name, f))
    img = Image.new("RGB", (1500, 24 + 96 * len(rows)), (18, 18, 20))
    d = ImageDraw.Draw(img)
    lab = rows[[n for n, _ in rows].index("Red Hat Mono")][1].font_variant(size=18)
    for i, (name, f) in enumerate(rows):
        y = 24 + 96 * i
        d.text((20, y + 30), name, font=lab, fill=(150, 150, 160))
        while f.getlength(text) > 1150 and f.size > 20:
            f = f.font_variant(size=int(f.size * 0.92))
        d.text((320, y + 40), text, font=f, fill=(240, 240, 236), anchor="lm")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=90)
    print(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--sheet":
        sheet(a[1], a[2] if len(a) > 2 else "Words from the song 0123")
    elif a:
        for n in a:
            print(face(n)[0])
    else:
        for n, (_, _, _, what, axes) in FACES.items():
            print(f"{n:22s} {what}" + (f"  [{axes}]" if axes else ""))
