import re
from pathlib import Path

PLAYLIST = Path("tv_epg.m3u")
EPG_URL = "https://raw.githubusercontent.com/dadocadavero-debug/epg-altervista/main/epg.xml"

# Nome visualizzato nella M3U -> tvg-id da usare.
# Le varianti/backup condividono lo stesso EPG del canale principale.
NAME_TO_ID = {
    # Rai
    "Rai 1": "Rai1.it",
    "Rai 2": "Rai2.it",
    "Rai 3": "Rai3.it",
    "Rai 4": "Rai4.it",
    "Rai 5": "Rai5.it",
    "Rai Movie": "RaiMovie.it",
    "Rai Premium": "RaiPremium.it",
    "Rai Storia": "RaiStoria.it",
    "Rai Scuola": "RaiScuola.it",
    "Rai Radio 2": "RaiRadio2.it",
    "Rai Sport": "RaiSport.it",
    "Rai Sport 900p": "RaiSport.it",
    "rai sport HbbTVraiway": "RaiSport.it",
    "rai sport HbbTV raiway": "RaiSport.it",
    "rai movie HbbTV raiway": "RaiMovie.it",
    "rai 5 HbbTV raiway": "Rai5.it",
    "rai premium HbbTV akamai": "RaiPremium.it",
    "Rai Premium hls": "RaiPremium.it",
    "Rai 4 HbbTV raiway": "Rai4.it",
    "rai yoyo HbbTV raiway": "RaiYoyo.it",
    "rai gulp HbbTV raiway": "RaiGulp.it",
    "rai scuola HbbTV raiway": "RaiScuola.it",
    "rai storia HbbTV raiway": "RaiStoria.it",

    # Mediaset
    "Rete 4": "Rete.4.it",
    "Canale 5": "Canale.5.it",
    "Italia 1": "Italia.1.it",
    "Mediaset 20": "20.it",
    "Iris": "Iris.it",
    "TwentySeven": "27.Twentyseven.it",
    "LA5": "La.5.it",
    "Cine 34": "Cine34.it",
    "Focus": "Focus.it",
    "Top Crime": "Top.Crime.it",
    "Italia 2": "Italia.2.it",
    "Mediaset Extra": "Mediaset.Extra.it",
    "Rete 4 (hls)": "Rete.4.it",
    "Canale 5 (hls)": "Canale.5.it",
    "Italia 1 (hls)": "Italia.1.it",
    "Mediaset 20 (hls)": "20.it",

    # Discovery
    "NOVE": "Nove.it",
    "Real Time": "Real.Time.it",
    "Food Network": "Food.Network.it",
    "Discovery": "Discovery.Channel.it",
    "Giallo": "Giallo.TV.it",
    "K2 🔐": "K2.it",
    "K2": "K2.it",
    "Frisbee 🔐": "Frisbee.it",
    "Frisbee": "Frisbee.it",
    "DMAX": "DMAX.it",
    "HGTV": "HGTV.it",
    "Turbo": "Motor.Trend.it",

    # Backup Discovery
    "NOVE backup 🔐": "Nove.it",
    "RealTime backup 🔐": "Real.Time.it",
    "FoodNetwork backup 🔐": "Food.Network.it",
    "Discovery backup 🔐": "Discovery.Channel.it",
    "Giallo backup 🔐": "Giallo.TV.it",
    "DMAX backup 🔐": "DMAX.it",
    "HGTV backup 🔐": "HGTV.it",
    "Turbo backup 🔐": "Motor.Trend.it",

    # Altri già presenti in EPGShare
    "TV8 SD": "TV8.HD.it",
    "Gambero Rosso": "Gambero.Rosso.HD.it",
    "QVC Italia": "QVC.it",
    "Fashion TV": "Fashion.TV.it",

    # Grande Fratello: alias stabili generati da update_epg.py
    "GFVIP Regia 1": "GFVIPRegia1",
    "GFVIP Regia 2": "GFVIPRegia2",
    "GFVIP Un'ora fa": "GFVIPUnOraFa",
}

# Feed per cui non abbiamo una guida lineare affidabile nella sorgente IT1.
TECHNICAL_FEEDS = {
    "RaiPlay (eventi)",
    "RaiPlay 2 (eventi)",
    "RaiPlay 3 (eventi)",
    "RaiPlaySport 1",
    "RaiPlaySport 2",
    "RaiPlaySport 3",
    "Rai generic1",
    "Rai generic3",
    "Rai test1",
    "Rai test2",
    "Rai test3",
    "GFVIP - Open House",
    "Mediaset b2",
    "Mediaset b3",
    "Diretta",
    "LA7 eventi live",
    "LA7 agenzie?",
}

def set_attr(line, key, value):
    pattern = rf'(\b{re.escape(key)}=")[^"]*(")'
    if re.search(pattern, line):
        return re.sub(pattern, rf'\g<1>{value}\2', line, count=1)

    comma = line.rfind(",")
    if comma == -1:
        return line
    return line[:comma] + f' {key}="{value}"' + line[comma:]

def display_name(extinf_line):
    comma = extinf_line.rfind(",")
    return extinf_line[comma + 1:].strip() if comma != -1 else ""

if not PLAYLIST.exists():
    raise SystemExit(f"File non trovato: {PLAYLIST}")

lines = PLAYLIST.read_text(encoding="utf-8-sig").splitlines()

out = []
changes = []
technical_found = []

# Un solo header, sempre con il link EPG corrente.
header_written = False

for line in lines:
    if line.startswith("#EXTM3U"):
        if not header_written:
            out.append(f'#EXTM3U x-tvg-url="{EPG_URL}"')
            header_written = True
        continue

    if line.startswith("#EXTINF"):
        name = display_name(line)

        target_id = NAME_TO_ID.get(name)
        if target_id:
            old_match = re.search(r'\btvg-id="([^"]*)"', line)
            old_id = old_match.group(1) if old_match else ""
            line = set_attr(line, "tvg-id", target_id)
            if old_id != target_id:
                changes.append(f"{name}: {old_id or '(vuoto)'} -> {target_id}")

        if name in TECHNICAL_FEEDS:
            technical_found.append(name)

    out.append(line)

if not header_written:
    out.insert(0, f'#EXTM3U x-tvg-url="{EPG_URL}"')

PLAYLIST.write_text("\n".join(out) + "\n", encoding="utf-8")

with open("epg_id_report.txt", "w", encoding="utf-8") as f:
    f.write("CORREZIONI TVG-ID AUTOMATICHE\n\n")
    if changes:
        for item in changes:
            f.write(item + "\n")
    else:
        f.write("Nessuna correzione necessaria.\n")

    f.write("\nFEED TECNICI/EVENTO SENZA EPG LINEARE IT1\n\n")
    for name in sorted(set(technical_found)):
        f.write(name + "\n")

print(f"Playlist aggiornata: {PLAYLIST}")
print(f"tvg-id corretti: {len(changes)}")
print(f"feed tecnici/evento rilevati: {len(set(technical_found))}")
