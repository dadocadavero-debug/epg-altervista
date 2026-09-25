#!/usr/bin/env python3
import gzip
import re
import unicodedata
import urllib.request
from urllib.parse import quote
import xml.etree.ElementTree as ET
from pathlib import Path

M3U_URL = "https://inthemix.altervista.org/tv.m3u"
EPG_URL = "https://raw.githubusercontent.com/dadocadavero-debug/epg-altervista/main/epg.xml"
LOGO_SOURCE_URL = "https://raw.githubusercontent.com/Tundrak/IPTV-Italia/main/iptvitaplus.m3u"
FALLBACK_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a0/TV_icon.svg"
OUT_M3U = Path("tv_epg.m3u")
OUT_REPORT = Path("mapping_report.txt")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "*/*",
}

# tvg-id Altervista -> tvg-id presenti nel nostro epg.xml personalizzato.
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
    "raisport": "RaiSport.it", "sportitalia": "Sportitalia.it",
    "ITBC4700002CO": "Solocalcio.it.it", "SuperTennis.it": "SuperTennis.HD.it",
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

    # Discovery: varianti/backup rimaste senza EPG
    "realtime backup": "Real.Time.it",
    "foodnetwork backup": "Food.Network.it",
    "turbo": "Motor.Trend.it",
    "turbo backup": "Motor.Trend.it",
    "k2": "K2.it",
    "frisbee": "Frisbee.it",

    # Grande Fratello: feed presenti nel nostro epg.xml personalizzato
    "gfvip regia 1": "GF.VIP.-.Regia.1.it",
    "gfvip regia 2": "GF.VIP.-.Regia.2.it",
    "gfvip un ora fa": "GF.VIP.-.Un’ora.fa.it",

    # Sport: questi ID sono inclusi dal workflow EPG Altervista nel nostro epg.xml.
    "sport italia": "Sportitalia.it",
    "equ tv": "EQUtv.it",
    "fifa plus": "IT:.FIFA+.be",
    "inter 24 7": "IT:.INTER.24/7.be",
    "juventus play": "IT:.Juventus.Play.be",
    "motoretro": "IT:.Motoretrò.be",
    "rally tv": "IT:.Rally.TV.FAST+.be",
    "redbull tv": "IT:.Red.Bull.TV.be",
    "red bull tv": "IT:.Red.Bull.TV.be",
    "tennis plus": "IT:.Tennis+.be",

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

RAI2_STREAM = "https://d3k8wzt41aflvx.cloudfront.net/RAI2/Live.m3u8"

# Rai 1 viene preso dinamicamente da "Rai 1 Europa" nella playlist Altervista.
# Rai 3 principale preferisce dinamicamente "Rai 3 Europa" dalla playlist Altervista.
# Se non fosse disponibile, usa come fallback "Rai 3 (900 dash)" senza eliminarlo.
# Tutti gli altri canali restano esattamente come arrivano dalla sorgente.

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
    "lazio style": "https://www.tvdream.net/img/lazio-style-tv.png",
    "lazio style tv": "https://www.tvdream.net/img/lazio-style-tv.png",
    "lazio style channel": "https://www.tvdream.net/img/lazio-style-tv.png",
    "f1 tv": "https://statics.quattroruote.it/content/dam/quattroruote/it/news/sport/2018/03/02/formula_1_liberty_media_lancia_lo_streaming_online_nasce_f1_tv_/gallery/rsmall/f1-tv-formula-1-3.jpg",
    "primavera tv": "https://i.imgur.com/0CJGGgd.png",
    "aci sport tv": "https://i.imgur.com/U8cHMOt.png",
    "aci sport live 01(non sempre attivo)": "https://i.imgur.com/U8cHMOt.png",
    "aci sport live 01": "https://i.imgur.com/U8cHMOt.png",
    "top calcio 24": "https://i.imgur.com/DnVPKPE.png",
    "redbull tv": "https://www.redbull.com/cs/RedBull2/images/branding/redbull-tv-logo-2x.png",
    "red bull tv": "https://www.redbull.com/cs/RedBull2/images/branding/redbull-tv-logo-2x.png",
    "rally tv": "https://i.postimg.cc/WtLq2C7c/logo-Rally-Tv1.png",
    "super tennis": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis+ 1": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis+ 2": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis+ 3": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis+ 4": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis plus 1": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis plus 2": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis plus 3": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis plus 4": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",
    "supertennis plus": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png",

    "inter tv": "https://raw.githubusercontent.com/tv-logo/tv-logos/refs/heads/main/countries/italy/inter-tv-it.png",
    "tennis channel": "https://i.imgur.com/tsljAnY.png",
    "tennis channel 2": "https://i.imgur.com/tsljAnY.png",
    "unbeaten": "https://i.imgur.com/LmkNt3v.png",
    "fubo sports": "https://i.imgur.com/qFNRJLb.png",
    "fubo sports network": "https://i.imgur.com/qFNRJLb.png",
    "rai sport": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png",
    "rai sport jolly 1": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png",
    "rai sport jolly 2": "https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png",
    "sportoutdoor": "https://www.google.com/s2/favicons?domain=sportoutdoor.tv&sz=256",
    "sportoutdoor tv": "https://www.google.com/s2/favicons?domain=sportoutdoor.tv&sz=256",
    "ff motorsport": "https://www.google.com/s2/favicons?domain=ffmotorsport.it&sz=256",
    "equ tv": "https://www.google.com/s2/favicons?domain=eqtv.it&sz=256",
}


def set_tvg_logo(extinf: str, logo_url: str) -> str:
    if re.search(r'tvg-logo="[^"]*"', extinf):
        return re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo_url}"', extinf, count=1)
    pos = extinf.find(" ")
    if pos != -1:
        return extinf[:pos + 1] + f'tvg-logo="{logo_url}" ' + extinf[pos + 1:]
    return extinf


def get_tvg_logo(extinf: str) -> str:
    m = re.search(r'tvg-logo="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""


def logo_key(name: str) -> str:
    n = norm(name)
    # rimuove qualificatori tecnici ma preserva il nome base
    toks = [t for t in n.split() if t not in TECH_WORDS and not re.fullmatch(r"\d+p", t)]
    return " ".join(toks)



def logo_lookup_name(name: str) -> str:
    """
    Normalizzazione SOLO per cercare il logo.
    Non modifica mai il nome visualizzato del canale nella M3U.
    """
    n = norm(name)

    # Elimina solo qualificatori informativi/tecnici dalla chiave di ricerca.
    # Esempi:
    # "Sky Sport (non sempre attivo)" -> "sky sport"
    # "Sport Italia (25fps)" -> "sport italia"
    # "Rai Sport jolly 1 (attivo raramente)" -> "rai sport jolly 1"
    phrases = [
        "non sempre attivo",
        "attivo raramente",
        "25fps",
        "50fps",
    ]
    for phrase in phrases:
        n = re.sub(rf"\b{re.escape(phrase)}\b", " ", n)

    n = re.sub(r"\s+", " ", n).strip()
    return n


def channel_specific_fallback_logo(name: str) -> str:
    """
    Ultima risorsa: crea un'immagine PNG diversa per ogni canale
    con il nome del canale. Così nessun canale resta senza immagine
    e non appare più la stessa icona TV generica per tutti.
    """
    label = name.strip() or "TV"
    return (
        "https://placehold.co/256x256/202020/FFFFFF.png?text="
        + quote(label[:24], safe="")
    )


def best_logo_for_name(name: str, learned: dict) -> str:
    n = norm(name)
    k = logo_key(name)
    lookup = logo_lookup_name(name)
    lookup_key = logo_key(lookup)

    # Prima prova le chiavi ripulite, ma senza cambiare il nome reale del canale.
    for candidate in (lookup, lookup_key, k, n):
        if candidate and candidate in learned:
            return learned[candidate]
        if candidate and candidate in LOGO_MAP:
            return LOGO_MAP[candidate]

    # Varianti numerate che devono condividere il logo principale.
    if lookup.startswith("tennis channel "):
        return LOGO_MAP.get("tennis channel", "")
    if lookup.startswith("rai sport jolly "):
        return LOGO_MAP.get("rai sport", "")

    # Fallback per varianti tipo "nove backup", "rai 1 hbbtv", ecc.
    for base, url in LOGO_MAP.items():
        if (
            lookup == base
            or lookup.startswith(base + " ")
            or lookup_key == base
            or lookup_key.startswith(base + " ")
        ):
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
    pos = extinf.find(" ")
    if pos != -1:
        return extinf[:pos + 1] + f'tvg-id="{new_id}" ' + extinf[pos + 1:]
    return extinf


def get_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""


def valid_epg_id(candidate: str, epg_ids: set) -> str:
    """
    Restituisce un ID EPG valido:
    - direttamente, se esiste nell'EPG;
    - tramite ID_MAP, se la sorgente usa un alias noto.
    """
    candidate = (candidate or "").strip()
    if not candidate:
        return ""
    if candidate in epg_ids:
        return candidate
    mapped = ID_MAP.get(candidate, "")
    if mapped and mapped in epg_ids:
        return mapped
    return ""


def alternate_epg_id(extinf: str, epg_ids: set):
    """
    Alcune righe Altervista usano attributi non standard come tvgid=, vg-id=
    o channel-id= invece di tvg-id=. Li usiamo SOLO se il valore esiste davvero
    nell'EPG, così non inventiamo associazioni.
    """
    for key in ("tvgid", "vg-id", "channel-id", "channel id"):
        raw = get_attr(extinf, key)
        cid = valid_epg_id(raw, epg_ids)
        if cid:
            return cid, key
    return "", ""


def _channel_blocks(lines):
    """Divide la M3U in prefisso + blocchi canale (#EXTINF + opzioni + URL)."""
    prefix = []
    blocks = []
    current = None

    for line in lines:
        if line.startswith("#EXTINF"):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is None:
            prefix.append(line)
        else:
            current.append(line)

    if current is not None:
        blocks.append(current)

    return prefix, blocks


def _block_name(block):
    extinf = block[0] if block else ""
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else ""


def _is_group_rai(block):
    return bool(block and 'group-title="Rai"' in block[0])


def _payload(block):
    """Restituisce opzioni + URL del canale, lasciando fuori la sua #EXTINF."""
    return list(block[1:])


def apply_rai_overrides(lines):
    """
    Correzioni minime e deliberate:
      - Rai 1 principale usa il payload di "Rai 1 Europa" dalla stessa playlist Altervista.
      - Rai 2 principale usa il CDN già verificato.
      - Rai 3 principale preferisce il payload di "Rai 3 Europa" dalla stessa playlist Altervista.
        Se manca, usa "Rai 3 (900 dash)" come fallback.
      - elimina soltanto il doppione Rai 1 Europa.
      - lascia Rai 1 4K hls/dash esattamente come arrivano da Altervista.
      - lascia SEMPRE "Rai 3 (900 dash)" nella playlist come alternativa.
      - NON modifica nessun altro canale Rai o non-Rai.

    Se manca una sorgente necessaria, l'aggiornamento viene annullato invece di produrre
    una playlist parzialmente rotta.
    """
    prefix, blocks = _channel_blocks(lines)

    by_name = {}
    for block in blocks:
        by_name.setdefault(norm(_block_name(block)), []).append(block)

    rai1_src = (by_name.get("rai 1 europa") or [None])[0]

    # Per Rai 3 preferiamo il feed Europa; 900 DASH resta comunque visibile
    # nella playlist e viene usato solo come fallback se Europa non esiste.
    rai3_src = (by_name.get("rai 3 europa") or by_name.get("rai 3 900 dash") or [None])[0]

    if rai1_src is None:
        raise RuntimeError('Sorgente "Rai 1 Europa" non trovata nella playlist Altervista; aggiornamento annullato.')
    if rai3_src is None:
        raise RuntimeError('Né "Rai 3 Europa" né "Rai 3 (900 dash)" trovati nella playlist Altervista; aggiornamento annullato.')

    rai1_payload = _payload(rai1_src)
    rai3_payload = _payload(rai3_src)

    if not rai1_payload:
        raise RuntimeError('"Rai 1 Europa" non contiene uno stream; aggiornamento annullato.')
    if not rai3_payload:
        raise RuntimeError('La sorgente scelta per Rai 3 non contiene uno stream; aggiornamento annullato.')

    out_blocks = []
    removed = {"rai 1 europa"}

    for block in blocks:
        name = norm(_block_name(block))

        # Elimina solo Rai 1 Europa, perché il suo stream viene riusato da Rai 1 principale.
        if name in removed:
            continue

        if _is_group_rai(block) and name == "rai 1":
            out_blocks.append([block[0], *rai1_payload])
        elif _is_group_rai(block) and name == "rai 2":
            out_blocks.append([block[0], RAI2_STREAM])
        elif _is_group_rai(block) and name == "rai 3":
            out_blocks.append([block[0], *rai3_payload])
        else:
            out_blocks.append(block)

    out = list(prefix)
    for block in out_blocks:
        out.extend(block)
    return out
def channel_name_from_extinf(extinf: str) -> str:
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else ""


def load_external_logo_index():
    """
    Scarica una seconda playlist pubblica usata SOLO come catalogo loghi.
    Se non è disponibile, lo script continua normalmente.
    """
    by_name = {}
    by_stripped = {}

    try:
        raw = fetch(LOGO_SOURCE_URL).decode("utf-8", errors="replace")
    except Exception:
        return by_name, by_stripped

    for line in raw.splitlines():
        if not line.startswith("#EXTINF"):
            continue

        name = channel_name_from_extinf(line)
        logo = get_tvg_logo(line)

        if not name or not logo:
            continue
        if "eu1-prod-images.disco-api.com" in logo:
            continue

        n = norm(name)
        sn = stripped_norm(name)

        if n:
            by_name.setdefault(n, logo)
        if sn:
            by_stripped.setdefault(sn, logo)

    return by_name, by_stripped


def main():
    # =========================================================
    # 1. SCARICA E CONTROLLA LA PLAYLIST SORGENTE
    # =========================================================
    m3u = fetch(M3U_URL).decode("utf-8", errors="replace")

    # Protezione: se Altervista restituisce temporaneamente una
    # playlist vuota/incompleta, NON generiamo una tv_epg.m3u vuota.
    source_channels = m3u.count("#EXTINF")
    if source_channels < 50:
        raise RuntimeError(
            f"Playlist Altervista incompleta: trovati solo {source_channels} canali. "
            "Aggiornamento annullato; viene mantenuta la tv_epg.m3u precedente."
        )

    # =========================================================
    # 2. SCARICA E CONTROLLA L'EPG
    # =========================================================
    epg_raw = fetch(EPG_URL)

    try:
        epg_xml = gzip.decompress(epg_raw)
    except OSError:
        epg_xml = epg_raw

    root = ET.fromstring(epg_xml)

    channel_count = len(root.findall("channel"))
    programme_count = len(root.findall("programme"))

    # Protezione: evita di lavorare con un EPG accidentalmente
    # vuoto o gravemente incompleto.
    if channel_count < 20 or programme_count < 1000:
        raise RuntimeError(
            f"EPG incompleto: {channel_count} canali, {programme_count} programmi. "
            "Aggiornamento annullato; viene mantenuta la playlist precedente."
        )

    # =========================================================
    # 3. INDICIZZA GLI ID E I NOMI PRESENTI NELL'EPG
    # =========================================================
    epg_ids = set()
    names_to_ids = {}
    stripped_to_ids = {}
    epg_icons_by_id = {}
    epg_icons_by_name = {}
    epg_icons_by_stripped = {}

    for ch in root.findall("channel"):
        cid = ch.get("id") or ""
        if not cid:
            continue

        epg_ids.add(cid)

        icon = ch.find("icon")
        icon_url = ""
        if icon is not None:
            icon_url = (icon.get("src") or "").strip()
            if icon_url:
                epg_icons_by_id[cid] = icon_url

        for dn in ch.findall("display-name"):
            if not dn.text:
                continue

            n = norm(dn.text)
            sn = stripped_norm(dn.text)

            names_to_ids.setdefault(n, set()).add(cid)

            if sn:
                stripped_to_ids.setdefault(sn, set()).add(cid)

            if icon_url:
                epg_icons_by_name.setdefault(n, set()).add(icon_url)
                if sn:
                    epg_icons_by_stripped.setdefault(sn, set()).add(icon_url)

    # Catalogo loghi supplementare: usato solo se il logo non arriva
    # già dalla playlist, dal mapping manuale o dall'EPG.
    external_logos, external_logos_stripped = load_external_logo_index()

    # =========================================================
    # 4. PREPARA LA PLAYLIST
    # =========================================================
    lines = m3u.splitlines()
    lines = apply_rai_overrides(lines)

    # Rimuove tutte le intestazioni #EXTM3U della sorgente.
    # Ne generiamo una nostra unica e consistente più sotto.
    lines = [
        line for line in lines
        if not line.lstrip("\ufeff").startswith("#EXTM3U")
    ]

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
    generic_logos = 0
    unmatched_epg = []

    # =========================================================
    # 5. HEADER M3U CON EPG AUTOMATICO
    # =========================================================
    # Un solo EPG per tutto: mapping e player leggono lo stesso epg.xml.
    # URL fisso: niente .xml.gz diretto, niente query string/cache-buster.
    out.append(
        f'#EXTM3U x-tvg-url="{EPG_URL}" url-tvg="{EPG_URL}"'
    )

    # =========================================================
    # 6. ELABORA I CANALI (backup e feed 🔐 originali vengono mantenuti)
    # =========================================================
    for line in lines:
        if not line.startswith("#EXTINF"):
            out.append(line)
            continue

        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""

        m = re.search(r'tvg-id="([^"]*)"', line)
        old_id = m.group(1).strip() if m else ""
        tvg_name = get_attr(line, "tvg-name")

        new_id = None
        reason = ""

        # 1) ID già valido nell'EPG: lascialo.
        if old_id and old_id in epg_ids:
            preserved += 1

        # 2) Alias ID verificato.
        elif old_id:
            mapped_old = valid_epg_id(old_id, epg_ids)
            if mapped_old:
                new_id = mapped_old
                reason = f"id:{old_id}"

        # 3) Recupera attributi alternativi/malformati della sorgente
        #    (tvgid=, vg-id=, channel-id=...), ma SOLO se validi nell'EPG.
        if not new_id and not (old_id and old_id in epg_ids):
            alt_id, alt_key = alternate_epg_id(line, epg_ids)
            if alt_id:
                new_id = alt_id
                reason = f"{alt_key}-verificato"

        # 4) Mappa nome verificata (soprattutto ID vuoti/HbbTV).
        if not new_id and not (old_id and old_id in epg_ids):
            mapped_name = NAME_MAP.get(norm(name), "")
            if mapped_name and mapped_name in epg_ids:
                new_id = mapped_name
                reason = "nome-verificato"

        # 5) Prova anche tvg-name se presente.
        if not new_id and not (old_id and old_id in epg_ids) and tvg_name:
            candidates = names_to_ids.get(norm(tvg_name), set())
            if len(candidates) == 1:
                new_id = next(iter(candidates))
                reason = "tvg-name-esatto"
                auto += 1
            else:
                sn_tvg = stripped_norm(tvg_name)
                candidates = stripped_to_ids.get(sn_tvg, set()) if len(sn_tvg) >= 4 else set()
                if len(candidates) == 1:
                    new_id = next(iter(candidates))
                    reason = "tvg-name-ripulito"
                    auto += 1

        # 6) Match automatico SOLO se univoco sul nome visualizzato.
        if not new_id and not (old_id and old_id in epg_ids):
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
            report.append(
                f"{name} | {old_id or '(vuoto)'} -> {new_id} | {reason}"
            )

        # Aggiunge un logo a OGNI canale.
        # Priorità:
        # 1) mapping manuale
        # 2) logo dell'EPG per il tvg-id effettivo
        # 3) logo già imparato da un duplicato/variante
        # 4) catalogo loghi supplementare
        # 5) logo EPG ricavato dal nome
        # 6) immagine personalizzata col nome del canale come ultima risorsa
        current_logo = get_tvg_logo(line)
        bad_logo = "eu1-prod-images.disco-api.com" in current_logo
        old_generic_logo = (
            current_logo == FALLBACK_LOGO_URL
            or current_logo.startswith("https://placehold.co/")
        )

        explicit_logo = (
            LOGO_MAP.get(logo_key(name))
            or LOGO_MAP.get(norm(name))
        )

        # Tutti i feed Supertennis+ usano il logo ufficiale di SuperTennis.
        normalized_name = norm(name)
        if (
            normalized_name.startswith("supertennis plus")
            or normalized_name.startswith("supertennis ")
            or normalized_name == "super tennis"
        ):
            explicit_logo = LOGO_MAP["supertennis"]

        effective_id_match = re.search(r'tvg-id="([^"]*)"', line)
        effective_id = effective_id_match.group(1).strip() if effective_id_match else ""

        if not effective_id or effective_id not in epg_ids:
            unmatched_epg.append(
                f"{name} | tvg-id={effective_id or '(vuoto)'} | group={get_attr(line, 'group-title') or '(vuoto)'}"
            )

        epg_id_logo = epg_icons_by_id.get(effective_id, "")
        learned_logo = best_logo_for_name(name, learned_logos)

        nname = norm(name)
        sname = stripped_norm(name)

        external_logo = (
            external_logos.get(nname)
            or external_logos_stripped.get(sname, "")
        )

        epg_name_logo = ""
        exact_epg_logos = epg_icons_by_name.get(nname, set())
        if len(exact_epg_logos) == 1:
            epg_name_logo = next(iter(exact_epg_logos))
        elif sname:
            stripped_epg_logos = epg_icons_by_stripped.get(sname, set())
            if len(stripped_epg_logos) == 1:
                epg_name_logo = next(iter(stripped_epg_logos))

        wanted_logo = (
            explicit_logo
            or epg_id_logo
            or learned_logo
            or external_logo
            or epg_name_logo
            or channel_specific_fallback_logo(name)
        )

        should_replace_logo = (
            not current_logo
            or bad_logo
            or old_generic_logo
            or (explicit_logo and current_logo != explicit_logo)
        )

        if should_replace_logo:
            line = set_tvg_logo(line, wanted_logo)
            logos_added += 1

            if wanted_logo.startswith("https://placehold.co/"):
                generic_logos += 1
                report.append(
                    f"{name} | logo generico aggiunto -> {wanted_logo}"
                )
            else:
                report.append(
                    f"{name} | logo {'sostituito' if bad_logo else 'aggiunto'} -> {wanted_logo}"
                )

        out.append(line)

    # =========================================================
    # 7. VALIDAZIONE FINALE PRIMA DI SOVRASCRIVERE LA PLAYLIST
    # =========================================================
    # Se per qualsiasi motivo l'EPG o il mapping risultassero anomali,
    # NON sostituiamo una tv_epg.m3u gia funzionante.
    output_extinf = [line for line in out if line.startswith("#EXTINF")]
    linked_ids = []
    for extinf in output_extinf:
        m = re.search(r'tvg-id="([^"]*)"', extinf)
        cid = m.group(1).strip() if m else ""
        if cid and cid in epg_ids:
            linked_ids.append(cid)

    required_ids = {
        "Rai1.it", "Rai2.it", "Rai3.it",
        "Rete.4.it", "Canale.5.it", "Italia.1.it",
    }
    missing_required_in_epg = sorted(required_ids - epg_ids)
    missing_required_in_playlist = sorted(required_ids - set(linked_ids))

    if missing_required_in_epg:
        raise RuntimeError(
            "EPG personalizzato anomalo: mancano ID fondamentali: "
            + ", ".join(missing_required_in_epg)
            + ". Aggiornamento annullato; la playlist precedente resta intatta."
        )

    if missing_required_in_playlist:
        raise RuntimeError(
            "Mapping playlist anomalo: mancano collegamenti EPG fondamentali: "
            + ", ".join(missing_required_in_playlist)
            + ". Aggiornamento annullato; la playlist precedente resta intatta."
        )

    if len(linked_ids) < 30:
        raise RuntimeError(
            f"Mapping EPG anomalo: solo {len(linked_ids)} canali risultano collegati all'EPG. "
            "Aggiornamento annullato; la playlist precedente resta intatta."
        )

    # Scrittura atomica: prima un file temporaneo, poi sostituzione finale.
    tmp_m3u = OUT_M3U.with_suffix(OUT_M3U.suffix + ".tmp")
    tmp_m3u.write_text("\n".join(out) + "\n", encoding="utf-8")
    tmp_m3u.replace(OUT_M3U)

    # =========================================================
    # 8. REPORT
    # =========================================================
    OUT_REPORT.write_text(
        f"Canali sorgente Altervista: {source_channels}\n"
        f"EPG unico usato per mapping e player: {EPG_URL}\n"
        f"Canali disponibili nell'EPG: {channel_count}\n"
        f"Programmi disponibili nell'EPG: {programme_count}\n"
        f"Canali della playlist collegati a un ID EPG valido: {len(linked_ids)}\n"
        f"Canali/righe EXTINF modificate: {changed}\n"
        f"Match automatici univoci: {auto}\n"
        f"ID già validi preservati: {preserved}\n"
        f"Loghi aggiunti/sostituiti: {logos_added}\n"
        f"Loghi generici usati come ultima risorsa: {generic_logos}\n"
        f"Canali senza EPG abbinabile: {len(unmatched_epg)}\n\n"
        + "\n".join(report)
        + ("\n\nCANALI SENZA EPG ABBINABILE\n" + "\n".join(unmatched_epg) if unmatched_epg else "")
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Creato {OUT_M3U} - "
        f"{changed} tvg-id aggiunti/corretti, "
        f"{logos_added} loghi aggiunti/sostituiti "
        f"({generic_logos} generici)"
    )
    print(
        f"EPG: {channel_count} canali, {programme_count} programmi"
    )
    print(f"Report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
