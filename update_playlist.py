#!/usr/bin/env python3
import gzip
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

M3U_URL = "https://inthemix.altervista.org/tv.m3u"
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"
OUT_M3U = Path("tv_epg.m3u")
OUT_REPORT = Path("mapping_report.txt")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "*/*",
}

# tvg-id Altervista -> tvg-id EPGShare verificati sulla playlist che funzionava.
ID_MAP = {
    "Rete4.it": "Rete.4.it", "Canale5.it": "Canale.5.it", "Italia1.it": "Italia.1.it",
    "la7": "LA7.HD.it", "Tv8.it": "TV8.HD.it", "PlutoEuronews.it": "Euronews.it",
    "20Mediaset.it": "20.it", "rai4.it": "Rai4.it", "iris.it": "Iris.it",
    "rai5.it": "Rai5.it", "raimovie.it": "RaiMovie.it", "raipremium.it": "RaiPremium.it",
    "Twentyseven.it": "27.Twentyseven.it", "TwentySeven.it": "27.Twentyseven.it",
    "la7d": "LA7.CINEMA.it", "la5": "La.5.it", "LA5.it": "La.5.it",
    "RealTime.it": "Real.Time.it", "GamberoRosso.it": "Gambero.Rosso.HD.it",
    "foodnetwork.it": "Food.Network.it", "cine34.it": "Cine34.it", "rtl102.5tv": "RTL.102.5.HD.it",
    "discovery": "Discovery.Channel.it", "Giallo.it": "Giallo.TV.it", "TopCrime.it": "Top.Crime.it",
    "TOPCrime.it": "Top.Crime.it", "super": "Super!.it", "rai news 24": "RaiNews24.it",
    "Italia2.it": "Italia.2.it", "TGCom24.it": "TGCom.it", "MediasetExtra.it": "Mediaset.Extra.it",
    "raisport": "RaiSport.it", "ITBC4700002CO": "Solocalcio.it.it", "SuperTennis.it": "SuperTennis.HD.it",
    "R101TV": "R101tv.it", "DeejayTV.it": "Deejay.TV.it", "radioitaliatv": "Radio.Italia.TV.HD.it",
    "RakutenFashionTv.it": "Fashion.TV.it", "qvcitalia": "QVC.it", "AciSportTV.it": "ACI.Sport.Tv.it",
    "bikesmartmobility": "BIKE.it", "VirginRadioTV.it": "Virgin.Radio.it", "radiomontecarlotv": "RMC.it",
    "rairadio2": "RaiRadio2.it", "rete4": "Rete.4.it", "canale5": "Canale.5.it", "italia1": "Italia.1.it",
    "rai4": "Rai4.it", "rai3": "Rai3.it", "rai 1": "Rai1.it", "rai 2": "Rai2.it", "rai 3": "Rai3.it",
    "rete 4": "Rete.4.it", "canale 5": "Canale.5.it", "italia 1": "Italia.1.it", "Cielo.it": "cielo.it",
    "RaiYoYo.it": "RaiYoyo.it", "tg norba 24": "TG.NORBA.24.it",
}

# Nomi Altervista con ID mancante ma corrispondenza EPG sicura.
NAME_MAP = {
    "sky tg24 sd": "Sky.TG24.it",
    "radio 105 tv": "Radio.105.it",
    "class cnbc": "Class.CNBC.it",
    "inter tv": "Inter.TV.it",
    "radio freccia": "RADIOFRECCIA.HD.it",
    "radio norba": "RADIONORBA.TV.it",
    "rai sport 900p": "RaiSport.it",
    "rai 1 europa": "Rai1.it", "rai 1": "Rai1.it", "rai 2 europa": "Rai2.it",
    "rai 3 europa": "Rai3.it", "rai 3": "Rai3.it", "la7 hd": "LA7.HD.it",
    "rai scuola europa": "RaiScuola.it", "rai storia europa": "RaiStoria.it",
    "tgcom24": "TGCom.it", "tgcom24 hd europa": "TGCom.it", "rai news 24 europa hd": "RaiNews24.it",
    "nove backup": "Nove.it", "nove 720p 50fps": "Nove.it", "discovery backup": "Discovery.Channel.it",
    "giallo backup": "Giallo.TV.it", "dmax backup": "DMAX.it", "hgtv backup": "HGTV.it",
    # HbbTV Rai: stessa programmazione del canale lineare.
    "rai premium hbbtv akamai": "RaiPremium.it",
    "rai movie hbbtv raiway": "RaiMovie.it",
    "rai 5 hbbtv raiway": "Rai5.it",
    "rai yoyo hbbtv raiway": "RaiYoyo.it",
    "rai gulp hbbtv raiway": "RaiGulp.it",
    "rai scuola hbbtv raiway": "RaiScuola.it",
    "rai storia hbbtv raiway": "RaiStoria.it",
    "rai sport hbbtv raiway": "RaiSport.it",
}

TECH_WORDS = {
    "hd", "sd", "hls", "dash", "hbbtv", "raiway", "akamai", "backup", "fps", "europa",
    "900p", "720p", "1080p", "4k", "uhd", "tv", "italia", "🔐",
}


# Loghi manuali per canali/varianti che spesso arrivano senza tvg-logo.
# Gli URL sono centralizzati qui per poterli aggiornare facilmente.
LOGO_MAP = {
    "rai 1": "https://www.raiplay.it/dl/img/2016/09/1473661951374Logo-Rai1.png",
    "rai 2": "https://www.raiplay.it/dl/img/2016/09/1473662585214Logo-Rai2.png",
    "rai 3": "https://www.raiplay.it/dl/img/2016/09/1473662801274Logo-Rai3.png",
    "rai 4": "https://www.raiplay.it/dl/img/2016/09/1473662992107Logo-Rai4.png",
    "rai 5": "https://www.raiplay.it/dl/img/2021/11/19/1637322377457_logo-rai5.png",
    "rai movie": "https://www.raiplay.it/dl/img/2021/11/19/1637309933509_1579882457761_rai-movie.png",
    "rai premium": "https://www.raiplay.it/dl/img/2021/11/19/1637309566388_1579882215002_rai-premium.png",
    "rai gulp": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raigulp.png",
    "rai yoyo": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raiyoyo.png",
    "nove": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/nove.png",
    "real time": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/realtime.png",
    "realtime": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/realtime.png",
    "food network": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/foodnetwork.png",
    "foodnetwork": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/foodnetwork.png",
    "giallo": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/giallo.png",
    "k2": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/k2.png",
    "frisbee": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/frisbee.png",
    "dmax": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/dmax.png",
    "hgtv": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/homegardentv.png",
    "motor trend": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/motortrend.png",
    "discovery": "https://i.imgur.com/5IxIFJ0.png",
}

def set_tvg_logo(extinf: str, logo_url: str) -> str:
    if re.search(r'tvg-logo="[^"]*"', extinf):
        return re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo_url}"', extinf, count=1)
    pos = extinf.find(" ")
    if pos != -1:
        return extinf[:pos+1] + f'tvg-logo="{logo_url}" ' + extinf[pos+1:]
    return extinf

def get_tvg_logo(extinf: str) -> str:
    m = re.search(r'tvg-logo="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""

def logo_key(name: str) -> str:
    n = norm(name)
    # rimuove qualificatori tecnici ma preserva il nome base
    toks = [t for t in n.split() if t not in TECH_WORDS and not re.fullmatch(r"\d+p", t)]
    return " ".join(toks)

def best_logo_for_name(name: str, learned: dict) -> str:
    n = norm(name)
    k = logo_key(name)
    if k in learned:
        return learned[k]
    if n in learned:
        return learned[n]
    if k in LOGO_MAP:
        return LOGO_MAP[k]
    if n in LOGO_MAP:
        return LOGO_MAP[n]
    # fallback per varianti tipo "nove backup", "rai 1 hbbtv", ecc.
    for base, url in LOGO_MAP.items():
        if k == base or k.startswith(base + " "):
            return url
    return ""


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def stripped_norm(s: str) -> str:
    toks = [t for t in norm(s).split() if t not in TECH_WORDS and not re.fullmatch(r"\d+p", t)]
    return " ".join(toks)


def set_tvg_id(extinf: str, new_id: str) -> str:
    if re.search(r'tvg-id="[^"]*"', extinf):
        return re.sub(r'tvg-id="[^"]*"', f'tvg-id="{new_id}"', extinf, count=1)
    # inserisce subito dopo #EXTINF durata
    comma = extinf.find(" ")
    if comma != -1:
        return extinf[:comma+1] + f'tvg-id="{new_id}" ' + extinf[comma+1:]
    return extinf


def main():
    m3u = fetch(M3U_URL).decode("utf-8", errors="replace")
    epg_raw = fetch(EPG_URL)
    try:
        epg_xml = gzip.decompress(epg_raw)
    except OSError:
        epg_xml = epg_raw
    root = ET.fromstring(epg_xml)

    epg_ids = set()
    names_to_ids = {}
    stripped_to_ids = {}
    for ch in root.findall("channel"):
        cid = ch.get("id") or ""
        if not cid:
            continue
        epg_ids.add(cid)
        for dn in ch.findall("display-name"):
            if not dn.text:
                continue
            n = norm(dn.text)
            sn = stripped_norm(dn.text)
            names_to_ids.setdefault(n, set()).add(cid)
            if sn:
                stripped_to_ids.setdefault(sn, set()).add(cid)

    lines = m3u.splitlines()

    # Impara i loghi già presenti nella playlist Altervista per riusarli
    # automaticamente sui duplicati/backup dello stesso canale.
    learned_logos = {}
    for src_line in lines:
        if not src_line.startswith("#EXTINF"):
            continue
        src_name = src_line.rsplit(",", 1)[-1].strip() if "," in src_line else ""
        src_logo = get_tvg_logo(src_line)
        if src_logo:
            learned_logos.setdefault(norm(src_name), src_logo)
            lk = logo_key(src_name)
            if lk:
                learned_logos.setdefault(lk, src_logo)

    out = []
    report = []
    changed = 0
    auto = 0
    preserved = 0
    logos_added = 0

    # Imposta EPGShare direttamente nell'header senza toccare altre opzioni.
    if lines and lines[0].startswith("#EXTM3U"):
        header = re.sub(r'\s+x-tvg-url="[^"]*"', '', lines[0])
        header += f' x-tvg-url="{EPG_URL}"'
        out.append(header)
        start = 1
    else:
        out.append(f'#EXTM3U x-tvg-url="{EPG_URL}"')
        start = 0

    for line in lines[start:]:
        if not line.startswith("#EXTINF"):
            out.append(line)
            continue

        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
        m = re.search(r'tvg-id="([^"]*)"', line)
        old_id = m.group(1) if m else ""
        new_id = None
        reason = ""

        # 1) ID già valido EPGShare: lascialo.
        if old_id and old_id in epg_ids:
            preserved += 1
        # 2) Mappa ID verificata.
        elif old_id and old_id in ID_MAP and ID_MAP[old_id] in epg_ids:
            new_id = ID_MAP[old_id]
            reason = f"id:{old_id}"
        # 3) Mappa nome verificata (soprattutto ID vuoti/HbbTV).
        elif norm(name) in NAME_MAP and NAME_MAP[norm(name)] in epg_ids:
            new_id = NAME_MAP[norm(name)]
            reason = "nome-verificato"
        # 4) Match automatico SOLO se univoco: nome esatto normalizzato.
        else:
            candidates = names_to_ids.get(norm(name), set())
            if len(candidates) == 1:
                new_id = next(iter(candidates))
                reason = "nome-esatto"
                auto += 1
            else:
                # Match tecnico ripulito solo se univoco e nome base non troppo corto.
                sn = stripped_norm(name)
                candidates = stripped_to_ids.get(sn, set()) if len(sn) >= 4 else set()
                if len(candidates) == 1:
                    new_id = next(iter(candidates))
                    reason = "nome-ripulito"
                    auto += 1

        if new_id and new_id != old_id:
            line = set_tvg_id(line, new_id)
            changed += 1
            report.append(f"{name} | {old_id or '(vuoto)'} -> {new_id} | {reason}")

        # Aggiunge i loghi mancanti e sostituisce i vecchi URL
        # disco-api.com che Fermata XTream non visualizza.
        current_logo = get_tvg_logo(line)
        bad_logo = "eu1-prod-images.disco-api.com" in current_logo
        explicit_logo = LOGO_MAP.get(logo_key(name)) or LOGO_MAP.get(norm(name))
        mapped_logo = best_logo_for_name(name, learned_logos)
        wanted_logo = explicit_logo or mapped_logo

        if wanted_logo and (not current_logo or bad_logo):
            line = set_tvg_logo(line, wanted_logo)
            logos_added += 1
            report.append(f"{name} | logo {'sostituito' if bad_logo else 'aggiunto'} -> {wanted_logo}")

        out.append(line)

    OUT_M3U.write_text("\n".join(out) + "\n", encoding="utf-8")
    OUT_REPORT.write_text(
        f"Canali/righe EXTINF modificate: {changed}\n"
        f"Match automatici univoci: {auto}\n"
        f"ID già validi preservati: {preserved}\n"
        f"Loghi aggiunti: {logos_added}\n\n" + "\n".join(report) + "\n",
        encoding="utf-8",
    )
    print(f"Creato {OUT_M3U} - {changed} tvg-id aggiunti/corretti, {logos_added} loghi aggiunti")
    print(f"Report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
