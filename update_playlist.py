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
    # Rai
    "rai 1": "https://upload.wikimedia.org/wikipedia/commons/f/fa/Rai_1_-_Logo_2016.svg",
    "rai1": "https://upload.wikimedia.org/wikipedia/commons/f/fa/Rai_1_-_Logo_2016.svg",
    "rai 2": "https://upload.wikimedia.org/wikipedia/commons/9/99/Rai_2_-_Logo_2016.svg",
    "rai2": "https://upload.wikimedia.org/wikipedia/commons/9/99/Rai_2_-_Logo_2016.svg",
    "rai 3": "https://upload.wikimedia.org/wikipedia/commons/9/9f/Rai_3_-_Logo_2016.svg",
    "rai3": "https://upload.wikimedia.org/wikipedia/commons/9/9f/Rai_3_-_Logo_2016.svg",
    "rai 4": "https://upload.wikimedia.org/wikipedia/commons/9/9b/Rai_4_-_Logo_2016.svg",
    "rai4": "https://upload.wikimedia.org/wikipedia/commons/9/9b/Rai_4_-_Logo_2016.svg",
    "rai 5": "https://upload.wikimedia.org/wikipedia/commons/8/86/Rai_5_-_Logo_2016.svg",
    "rai5": "https://upload.wikimedia.org/wikipedia/commons/8/86/Rai_5_-_Logo_2016.svg",
    "rai movie": "https://upload.wikimedia.org/wikipedia/commons/7/75/Rai_Movie_-_Logo_2016.svg",
    "rai premium": "https://upload.wikimedia.org/wikipedia/commons/1/14/Rai_Premium_-_Logo_2016.svg",
    "rai yoyo": "https://upload.wikimedia.org/wikipedia/commons/9/95/Rai_Yoyo_-_Logo_2017.svg",
    "rai gulp": "https://upload.wikimedia.org/wikipedia/commons/0/0b/Rai_Gulp_-_Logo_2017.svg",
    "rai scuola": "https://upload.wikimedia.org/wikipedia/commons/6/69/Rai_Scuola_-_Logo_2017.svg",
    "rai storia": "https://upload.wikimedia.org/wikipedia/commons/9/9d/Rai_Storia_-_Logo_2017.svg",
    "rai sport": "https://upload.wikimedia.org/wikipedia/commons/8/81/Rai_Sport_-_Logo_2022.svg",
    "rai news 24": "https://upload.wikimedia.org/wikipedia/commons/8/8a/Rai_News_24_-_Logo_2022.svg",

    # Discovery / Warner Bros. Discovery
    "nove": "https://upload.wikimedia.org/wikipedia/commons/4/43/Nove_-_Logo_2016.svg",
    "real time": "https://upload.wikimedia.org/wikipedia/commons/e/e1/Real_Time_-_Logo_2017.svg",
    "realtime": "https://upload.wikimedia.org/wikipedia/commons/e/e1/Real_Time_-_Logo_2017.svg",
    "food network": "https://upload.wikimedia.org/wikipedia/commons/0/06/Food_Network_logo.svg",
    "dmax": "https://upload.wikimedia.org/wikipedia/commons/8/8a/DMAX_logo.svg",
    "hgtv": "https://upload.wikimedia.org/wikipedia/commons/1/14/HGTV_logo.svg",
    "discovery": "https://upload.wikimedia.org/wikipedia/commons/2/27/Discovery_Channel_-_Logo_2019.svg",
    "giallo": "https://upload.wikimedia.org/wikipedia/commons/1/13/Giallo_logo.svg",

    # Mediaset / generalisti
    "rete 4": "https://upload.wikimedia.org/wikipedia/commons/4/4f/Rete_4_-_Logo_2018.svg",
    "rete4": "https://upload.wikimedia.org/wikipedia/commons/4/4f/Rete_4_-_Logo_2018.svg",
    "canale 5": "https://upload.wikimedia.org/wikipedia/commons/0/0c/Canale_5_-_Logo_2018.svg",
    "canale5": "https://upload.wikimedia.org/wikipedia/commons/0/0c/Canale_5_-_Logo_2018.svg",
    "italia 1": "https://upload.wikimedia.org/wikipedia/commons/2/2c/Italia_1_-_Logo_2018.svg",
    "italia1": "https://upload.wikimedia.org/wikipedia/commons/2/2c/Italia_1_-_Logo_2018.svg",
    "20 mediaset": "https://upload.wikimedia.org/wikipedia/commons/2/22/20_Mediaset_logo.svg",
    "la5": "https://upload.wikimedia.org/wikipedia/commons/9/92/La5_logo.svg",
    "cine34": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Cine34_logo.svg",
    "top crime": "https://upload.wikimedia.org/wikipedia/commons/f/fc/Top_Crime_logo.svg",
    "italia 2": "https://upload.wikimedia.org/wikipedia/commons/0/0e/Italia_2_logo.svg",
    "mediaset extra": "https://upload.wikimedia.org/wikipedia/commons/4/42/Mediaset_Extra_logo.svg",

    # Altri nazionali / sport
    "la7": "https://upload.wikimedia.org/wikipedia/commons/0/0f/LA7_-_Logo_2011.svg",
    "tv8": "https://upload.wikimedia.org/wikipedia/commons/9/9f/TV8_Logo_2016.svg",
    "cielo": "https://upload.wikimedia.org/wikipedia/commons/8/85/Cielo_TV_logo.svg",
    "super tennis": "https://upload.wikimedia.org/wikipedia/commons/5/55/SuperTennis_logo.svg",
    "supertennis": "https://upload.wikimedia.org/wikipedia/commons/5/55/SuperTennis_logo.svg",
    "inter tv": "https://upload.wikimedia.org/wikipedia/commons/0/05/FC_Internazionale_Milano_2021.svg",
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

        # Aggiunge un logo SOLO se la riga non ne ha già uno.
        if not get_tvg_logo(line):
            logo = best_logo_for_name(name, learned_logos)
            if logo:
                line = set_tvg_logo(line, logo)
                logos_added += 1
                report.append(f"{name} | logo aggiunto -> {logo}")

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
