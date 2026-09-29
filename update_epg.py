#!/usr/bin/env python3
"""
DAVIDE EPG + PLAYLIST SYNC MASTER
2026-09-28

UN SOLO MOTORE per playlist ed EPG.

Questo risolve il problema strutturale dei due vecchi updater:
- prima update_epg.py dipendeva dai tvg-id della playlist;
- update_playlist.py dipendeva dagli ID presenti nell'EPG;
- quindi i due file potevano essere corretti separatamente ma non allineati.

Ora entrambi vengono generati dalla STESSA mappa nello stesso processo.

GARANZIE STREAM:
- tutti gli stream/payload Altervista restano byte-per-byte invariati;
- UNICA eccezione intenzionale già richiesta: Rai 1/2/3 usano il payload
  corrente di Rai 1/2/3 Europa;
- nessun probe/auto-repair sostituisce URL;
- Rai 1 4K e tutte le altre varianti restano indipendenti.

EPG:
- assegna un ID interno STABILE e sicuro a ogni guida trovata;
- scrive lo stesso ID nella M3U e nell'XMLTV;
- usa solo guide reali e fresche;
- copre tutte le categorie, non solo Sport;
- nessun palinsesto inventato per canali senza una fonte reale.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import lzma
import re
import shutil
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

M3U_URL = "https://inthemix.altervista.org/tv.m3u"
EPG_URL = "https://raw.githubusercontent.com/dadocadavero-debug/epg-altervista/main/epg.xml"
LOGO_SOURCE_URL = "https://raw.githubusercontent.com/Tundrak/IPTV-Italia/main/iptvitaplus.m3u"

OUT_M3U = Path("tv_epg.m3u")
OUT_EPG = Path("epg.xml")
OUT_EPG_REPORT = Path("epg_report.txt")
OUT_MAPPING_REPORT = Path("mapping_report.txt")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "*/*",
}

PAST_GRACE = timedelta(hours=8)
FUTURE_LIMIT = timedelta(days=10)

ID_MAP = {'20Mediaset.it': '20.it',
 'AciSportTV.it': 'ACI.Sport.Tv.it',
 'Canale5.it': 'Canale.5.it',
 'Cielo.it': 'cielo.it',
 'DeejayTV.it': 'Deejay.TV.it',
 'GamberoRosso.it': 'Gambero.Rosso.HD.it',
 'Giallo.it': 'Giallo.TV.it',
 'ITBC4700002CO': 'Solocalcio.it.it',
 'Italia1.it': 'Italia.1.it',
 'Italia2.it': 'Italia.2.it',
 'LA5.it': 'La.5.it',
 'Mediaset20.it': '20.it',
 'MediasetExtra.it': 'Mediaset.Extra.it',
 'PlutoEuronews.it': 'Euronews.it',
 'R101TV': 'R101tv.it',
 'RaiYoYo.it': 'RaiYoyo.it',
 'RakutenFashionTv.it': 'Fashion.TV.it',
 'RealTime.it': 'Real.Time.it',
 'Rete4.it': 'Rete.4.it',
 'SuperTennis.it': 'SuperTennis.HD.it',
 'TGCom24.it': 'TGCom.it',
 'TOPCrime.it': 'Top.Crime.it',
 'TopCrime.it': 'Top.Crime.it',
 'Tv8.it': 'TV8.HD.it',
 'TwentySeven.it': '27.Twentyseven.it',
 'Twentyseven.it': '27.Twentyseven.it',
 'VirginRadioTV.it': 'Virgin.Radio.it',
 'bikesmartmobility': 'BIKE.it',
 'canale 5': 'Canale.5.it',
 'canale5': 'Canale.5.it',
 'cine34.it': 'Cine34.it',
 'discovery': 'Discovery.Channel.it',
 'foodnetwork.it': 'Food.Network.it',
 'iris.it': 'Iris.it',
 'italia 1': 'Italia.1.it',
 'italia1': 'Italia.1.it',
 'la5': 'La.5.it',
 'la7': 'LA7.HD.it',
 'la7d': 'LA7.CINEMA.it',
 'qvcitalia': 'QVC.it',
 'radioitaliatv': 'Radio.Italia.TV.HD.it',
 'radiomontecarlotv': 'RMC.it',
 'rai 1': 'Rai1.it',
 'rai 2': 'Rai2.it',
 'rai 3': 'Rai3.it',
 'rai news 24': 'RaiNews24.it',
 'rai3': 'Rai3.it',
 'rai4': 'Rai4.it',
 'rai4.it': 'Rai4.it',
 'rai5.it': 'Rai5.it',
 'raimovie.it': 'RaiMovie.it',
 'raipremium.it': 'RaiPremium.it',
 'rairadio2': 'RaiRadio2.it',
 'raisport': 'RaiSport.it',
 'rete 4': 'Rete.4.it',
 'rete4': 'Rete.4.it',
 'rtl102.5tv': 'RTL.102.5.HD.it',
 'sportitalia': 'Sportitalia.it',
 'super': 'Super!.it',
 'tg norba 24': 'TG.NORBA.24.it'}
NAME_MAP = {'20 mediaset': '20.it',
 '27 twentyseven': '27.Twentyseven.it',
 'aci sport tv': 'ACI.Sport.Tv.it',
 'bike': 'BIKE.it',
 'canale 5': 'Canale.5.it',
 'cine 34': 'Cine34.it',
 'class cnbc': 'Class.CNBC.it',
 'discovery backup': 'Discovery.Channel.it',
 'dmax backup': 'DMAX.it',
 'equ tv': 'EQUtv.it',
 'fifa plus': 'IT:.FIFA+.be',
 'focus': 'Focus.it',
 'foodnetwork backup': 'Food.Network.it',
 'frisbee': 'Frisbee.it',
 'gfvip regia 1': 'GF.VIP.-.Regia.1.it',
 'gfvip regia 2': 'GF.VIP.-.Regia.2.it',
 'gfvip un ora fa': 'GF.VIP.-.Un’ora.fa.it',
 'giallo backup': 'Giallo.TV.it',
 'glory kickboxing': 'IT:.GLORY.Kickboxing.be',
 'hgtv backup': 'HGTV.it',
 'inter 24 7': 'IT:.INTER.24/7.be',
 'inter tv': 'Inter.TV.it',
 'italia 1': 'Italia.1.it',
 'italia 2': 'Italia.2.it',
 'juventus play': 'IT:.Juventus.Play.be',
 'k2': 'K2.it',
 'la7 hd': 'LA7.HD.it',
 'mediaset 20': '20.it',
 'mediaset extra': 'Mediaset.Extra.it',
 'motoretro': 'IT:.Motoretrò.be',
 'motorvision tv': 'IT:.MOTORVISION.TV.be',
 'nove 720p 50fps': 'Nove.it',
 'nove backup': 'Nove.it',
 'pfl mma': 'IT:.PFL.MMA.be',
 'racer international': 'IT:.RACER.International.be',
 'radio 105 tv': 'Radio.105.it',
 'radio freccia': 'RADIOFRECCIA.HD.it',
 'radio norba': 'RADIONORBA.TV.it',
 'rai 1': 'Rai1.it',
 'rai 1 europa': 'Rai1.it',
 'rai 2 europa': 'Rai2.it',
 'rai 3': 'Rai3.it',
 'rai 3 europa': 'Rai3.it',
 'rai 4': 'Rai4.it',
 'rai 5': 'Rai5.it',
 'rai 5 hbbtv raiway': 'Rai5.it',
 'rai gulp hbbtv raiway': 'RaiGulp.it',
 'rai movie': 'RaiMovie.it',
 'rai movie hbbtv raiway': 'RaiMovie.it',
 'rai news 24': 'RaiNews24.it',
 'rai news 24 europa hd': 'RaiNews24.it',
 'rai premium': 'RaiPremium.it',
 'rai premium hbbtv akamai': 'RaiPremium.it',
 'rai scuola europa': 'RaiScuola.it',
 'rai scuola hbbtv raiway': 'RaiScuola.it',
 'rai sport': 'RaiSport.it',
 'rai sport 900p': 'RaiSport.it',
 'rai sport hbbtv raiway': 'RaiSport.it',
 'rai storia europa': 'RaiStoria.it',
 'rai storia hbbtv raiway': 'RaiStoria.it',
 'rai yoyo hbbtv raiway': 'RaiYoyo.it',
 'rally tv': 'IT:.Rally.TV.FAST+.be',
 'realtime backup': 'Real.Time.it',
 'red bull tv': 'IT:.Red.Bull.TV.be',
 'redbull tv': 'IT:.Red.Bull.TV.be',
 'rete 4': 'Rete.4.it',
 'sky tg24 sd': 'Sky.TG24.it',
 'solocalcio': 'Solocalcio.it.it',
 'sport italia': 'Sportitalia.it',
 'sportitalia': 'Sportitalia.it',
 'super tennis': 'SuperTennis.HD.it',
 'supertennis': 'SuperTennis.HD.it',
 'tennis plus': 'IT:.Tennis+.be',
 'tgcom24': 'TGCom.it',
 'tgcom24 hd europa': 'TGCom.it',
 'top barca': 'IT:.TOP.Barça.be',
 'top crime': 'Top.Crime.it',
 'turbo': 'Motor.Trend.it',
 'turbo backup': 'Motor.Trend.it',
 'twentyseven': '27.Twentyseven.it'}
LOGO_MAP = {'20 mediaset': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/20mediaset.png',
 'aci sport live 01': 'https://i.imgur.com/U8cHMOt.png',
 'aci sport live 01(non sempre attivo)': 'https://i.imgur.com/U8cHMOt.png',
 'aci sport tv': 'https://i.imgur.com/U8cHMOt.png',
 'discovery': 'https://i.imgur.com/5IxIFJ0.png',
 'dmax': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/dmax.png',
 'equ tv': 'https://www.google.com/s2/favicons?domain=eqtv.it&sz=256',
 'f1 tv': 'https://statics.quattroruote.it/content/dam/quattroruote/it/news/sport/2018/03/02/formula_1_liberty_media_lancia_lo_streaming_online_nasce_f1_tv_/gallery/rsmall/f1-tv-formula-1-3.jpg',
 'ff motorsport': 'https://www.google.com/s2/favicons?domain=ffmotorsport.it&sz=256',
 'food network': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/foodnetwork.png',
 'foodnetwork': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/foodnetwork.png',
 'frisbee': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/frisbee.png',
 'fubo sports': 'https://i.imgur.com/qFNRJLb.png',
 'fubo sports network': 'https://i.imgur.com/qFNRJLb.png',
 'giallo': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/giallo.png',
 'hgtv': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/homegardentv.png',
 'inter tv': 'https://raw.githubusercontent.com/tv-logo/tv-logos/refs/heads/main/countries/italy/inter-tv-it.png',
 'k2': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/k2.png',
 'lazio style': 'https://www.tvdream.net/img/lazio-style-tv.png',
 'lazio style channel': 'https://www.tvdream.net/img/lazio-style-tv.png',
 'lazio style tv': 'https://www.tvdream.net/img/lazio-style-tv.png',
 'mediaset 20': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/20mediaset.png',
 'motor trend': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/motortrend.png',
 'nove': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/nove.png',
 'primavera tv': 'https://www.tvdream.net/img/primavera-tv.png',
 'rai 1': 'https://www.raiplay.it/dl/img/2016/09/1473661951374Logo-Rai1.png',
 'rai 2': 'https://www.raiplay.it/dl/img/2016/09/1473662585214Logo-Rai2.png',
 'rai 3': 'https://www.raiplay.it/dl/img/2016/09/1473662801274Logo-Rai3.png',
 'rai 4': 'https://www.raiplay.it/dl/img/2016/09/1473662992107Logo-Rai4.png',
 'rai 5': 'https://www.raiplay.it/dl/img/2021/11/19/1637322377457_logo-rai5.png',
 'rai gulp': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raigulp.png',
 'rai movie': 'https://www.raiplay.it/dl/img/2021/11/19/1637309933509_1579882457761_rai-movie.png',
 'rai premium': 'https://www.raiplay.it/dl/img/2021/11/19/1637309566388_1579882215002_rai-premium.png',
 'rai sport': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png',
 'rai sport jolly 1': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png',
 'rai sport jolly 2': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raisport+hd.png',
 'rai yoyo': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/raiyoyo.png',
 'rally tv': 'https://i.postimg.cc/WtLq2C7c/logo-Rally-Tv1.png',
 'real time': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/realtime.png',
 'realtime': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/realtime.png',
 'red bull tv': 'https://www.redbull.com/cs/RedBull2/images/branding/redbull-tv-logo-2x.png',
 'redbull tv': 'https://www.redbull.com/cs/RedBull2/images/branding/redbull-tv-logo-2x.png',
 'sportoutdoor': 'https://www.google.com/s2/favicons?domain=sportoutdoor.tv&sz=256',
 'sportoutdoor tv': 'https://www.google.com/s2/favicons?domain=sportoutdoor.tv&sz=256',
 'super tennis': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis plus': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis plus 1': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis plus 2': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis plus 3': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis plus 4': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis+ 1': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis+ 2': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis+ 3': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'supertennis+ 4': 'https://cdn.jsdelivr.net/gh/Tundrak/IPTV-Italia/logos/supertennis.png',
 'tennis channel': 'https://i.imgur.com/tsljAnY.png',
 'tennis channel 2': 'https://i.imgur.com/tsljAnY.png',
 'top calcio 24': 'https://i.imgur.com/DnVPKPE.png',
 'unbeaten': 'https://i.imgur.com/LmkNt3v.png'}
RAI_EUROPA_SOURCE = {'rai 1': 'rai 1 europa', 'rai 2': 'rai 2 europa', 'rai 3': 'rai 3 europa'}
TECH_WORDS = {'1080p',
 '25fps',
 '4k',
 '50fps',
 '720p',
 '900p',
 'akamai',
 'attiva',
 'attivo',
 'backup',
 'dash',
 'europa',
 'fps',
 'h264',
 'h265',
 'hbbtv',
 'hd',
 'hevc',
 'hls',
 'italia',
 'non',
 'raiway',
 'raramente',
 'sd',
 'sempre',
 'tv',
 'uhd',
 '🔐'}

# Fonti verificate/utili. Solo IT1 è obbligatoria; le altre sono fallback.
SOURCES = [
    {
        "name": "EPGShare IT1",
        "urls": ["https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"],
        "priority": 100,
        "required": True,
    },
    {
        "name": "EPG Italia",
        "urls": ["https://www.epgitalia.tv/gzip"],
        "priority": 97,
        "required": False,
    },
    {
        "name": "TVIT Italia",
        "urls": ["https://tvit.leicaflorianrobert.dev/epg/list.xml"],
        "priority": 94,
        "required": False,
    },
    {
        "name": "EPGShare Rakuten",
        "urls": ["https://epgshare01.online/epgshare01/epg_ripper_RAKUTEN1.xml.gz"],
        "priority": 90,
        "required": False,
    },
    {
        "name": "EPGShare BE2 FAST/Sport",
        "urls": ["https://epgshare01.online/epgshare01/epg_ripper_BE2.xml.gz"],
        "priority": 84,
        "required": False,
    },
    {
        "name": "Samsung TV Plus Italia",
        "urls": ["https://i.mjh.nz/SamsungTVPlus/it.xml.gz"],
        "priority": 80,
        "required": False,
    },
    {
        "name": "Pluto TV Italia",
        "urls": ["https://i.mjh.nz/PlutoTV/it.xml.gz"],
        "priority": 80,
        "required": False,
    },
    {
        "name": "EPGShare Plex",
        "urls": ["https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz"],
        "priority": 76,
        "required": False,
    },
]

CORE_NAMES = {
    "rai 1", "rai 2", "rai 3", "rete 4", "canale 5", "italia 1"
}

# Manual logo is forced only for these known problematic families.
FORCE_MANUAL_LOGO_PREFIXES = (
    "supertennis",
    "super tennis",
)

class SafeSkipUpdate(Exception):
    """Errore esterno/transitorio: non pubblicare nulla, ma lascia intatti i file buoni."""


@dataclass
class M3uBlock:
    original_extinf: str
    name: str
    old_id: str
    tvg_name: str
    group: str
    payload: list[str]

@dataclass
class SourceData:
    name: str
    priority: int
    url: str
    channels: dict[str, ET.Element]
    programmes: dict[str, list[ET.Element]]
    exact_names: dict[str, set[str]]
    stripped_names: dict[str, set[str]]
    has_now: dict[str, bool]
    horizon: dict[str, datetime]
    raw_channel_count: int
    raw_programme_count: int

@dataclass
class Candidate:
    source: SourceData
    source_id: str
    quality: int
    reason: str

    def score(self):
        h = self.source.horizon.get(self.source_id)
        return (
            self.quality,
            1 if self.source.has_now.get(self.source_id, False) else 0,
            self.source.priority,
            h.timestamp() if h else 0,
            len(self.source.programmes.get(self.source_id, [])),
        )

def fetch(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def decompress(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if data[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(data)
    return data

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode().lower()
    s = s.replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

def stripped_norm(s: str) -> str:
    toks = []
    for t in norm(s).split():
        if t in TECH_WORDS:
            continue
        if re.fullmatch(r"\d+(?:p|fps)", t):
            continue
        toks.append(t)
    return " ".join(toks)

def get_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""

def set_attr(extinf: str, key: str, value: str) -> str:
    value = value.replace('"', "")
    pat = rf'{re.escape(key)}="[^"]*"'
    if re.search(pat, extinf):
        return re.sub(pat, f'{key}="{value}"', extinf, count=1)

    pos = extinf.find(" ")
    if pos != -1:
        return extinf[:pos + 1] + f'{key}="{value}" ' + extinf[pos + 1:]

    # EXTINF minimale: inserisce prima della virgola.
    comma = extinf.rfind(",")
    if comma != -1:
        return extinf[:comma] + f' {key}="{value}"' + extinf[comma:]
    return extinf

def get_logo(extinf: str) -> str:
    return get_attr(extinf, "tvg-logo")

def channel_name(extinf: str) -> str:
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else ""

def channel_names(ch: ET.Element) -> list[str]:
    return [
        x.text.strip()
        for x in ch.findall("display-name")
        if x.text and x.text.strip()
    ]

def parse_xmltv_time(value: str):
    value = (value or "").strip()
    m = re.match(r"^(\d{12,14})(?:\s*([+-]\d{4}|Z))?", value)
    if not m:
        return None

    digits, offset = m.groups()
    try:
        fmt = "%Y%m%d%H%M%S" if len(digits) == 14 else "%Y%m%d%H%M"
        dt = datetime.strptime(digits, fmt)

        if offset == "Z":
            return dt.replace(tzinfo=timezone.utc)
        if offset:
            sign = 1 if offset[0] == "+" else -1
            hh, mm = int(offset[1:3]), int(offset[3:5])
            return dt.replace(
                tzinfo=timezone(sign * timedelta(hours=hh, minutes=mm))
            )
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def fresh_programme(p: ET.Element, now: datetime) -> bool:
    start = parse_xmltv_time(p.get("start", ""))
    stop = parse_xmltv_time(p.get("stop", ""))
    if not start:
        return False
    if not stop:
        stop = start + timedelta(hours=6)

    start = start.astimezone(timezone.utc)
    stop = stop.astimezone(timezone.utc)

    return stop >= now - PAST_GRACE and start <= now + FUTURE_LIMIT

def programme_key(p: ET.Element, cid: str):
    return (
        cid,
        p.get("start") or "",
        p.get("stop") or "",
        norm(p.findtext("title") or ""),
    )

def parse_m3u(text: str):
    lines = text.splitlines()
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

    parsed = []
    for b in blocks:
        extinf = b[0]
        parsed.append(
            M3uBlock(
                original_extinf=extinf,
                name=channel_name(extinf),
                old_id=get_attr(extinf, "tvg-id"),
                tvg_name=get_attr(extinf, "tvg-name"),
                group=get_attr(extinf, "group-title"),
                payload=list(b[1:]),
            )
        )

    return prefix, parsed

def target_payloads(blocks: list[M3uBlock]):
    by_name = defaultdict(list)
    for b in blocks:
        by_name[norm(b.name)].append(b)

    europa = {}
    for main_name, europa_name in RAI_EUROPA_SOURCE.items():
        matches = by_name.get(europa_name, [])
        if not matches or not matches[0].payload:
            raise RuntimeError(
                f'Feed richiesto "{europa_name}" non trovato/senza payload. '
                "Nessuno stream viene pubblicato."
            )
        europa[main_name] = list(matches[0].payload)

    result = []
    for b in blocks:
        n = norm(b.name)
        if b.group == "Rai" and n in europa:
            result.append(list(europa[n]))
        else:
            result.append(list(b.payload))

    return result

def name_keys(block: M3uBlock):
    keys = []
    for raw in (block.name, block.tvg_name):
        for k in (norm(raw), stripped_norm(raw)):
            if k and k not in keys:
                keys.append(k)
    return keys

def canonical_hint(block: M3uBlock):
    # Known name mapping first.
    for key in name_keys(block):
        if key in NAME_MAP:
            return NAME_MAP[key]

    # Known source-ID alias.
    if block.old_id:
        return ID_MAP.get(block.old_id, block.old_id)

    # Stable fallback by logical channel name.
    return stripped_norm(block.name) or norm(block.name) or "channel"

def safe_epg_id(block: M3uBlock):
    hint = canonical_hint(block)
    slug = norm(hint).replace(" ", "-")
    slug = re.sub(r"-+", "-", slug).strip("-") or "channel"
    slug = slug[:48]
    digest = hashlib.sha1(hint.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"dv.{slug}.{digest}"

def relevance_for_blocks(blocks):
    ids = set()
    names = set()
    stripped = set()

    for b in blocks:
        if b.old_id:
            ids.add(b.old_id)
            mapped = ID_MAP.get(b.old_id)
            if mapped:
                ids.add(mapped)

        hint = canonical_hint(b)
        if hint and "." in hint:
            ids.add(hint)

        for raw in (b.name, b.tvg_name):
            n = norm(raw)
            sn = stripped_norm(raw)
            if n:
                names.add(n)
                mapped = NAME_MAP.get(n)
                if mapped:
                    ids.add(mapped)
            if sn:
                stripped.add(sn)
                mapped = NAME_MAP.get(sn)
                if mapped:
                    ids.add(mapped)

    return ids, names, stripped

def build_source(spec, raw: bytes, now: datetime, relevance):
    root = ET.fromstring(decompress(raw))
    all_channels = root.findall("channel")
    all_programmes = root.findall("programme")

    wanted_ids, wanted_names, wanted_stripped = relevance

    channels = {}
    exact_names = defaultdict(set)
    stripped_names = defaultdict(set)

    for ch in all_channels:
        cid = (ch.get("id") or "").strip()
        if not cid:
            continue

        names = channel_names(ch)
        nset = {norm(x) for x in names if norm(x)}
        sset = {stripped_norm(x) for x in names if stripped_norm(x)}

        if not (
            cid in wanted_ids
            or bool(nset & wanted_names)
            or bool(sset & wanted_stripped)
        ):
            continue

        channels[cid] = ch
        for n in nset:
            exact_names[n].add(cid)
        for s in sset:
            stripped_names[s].add(cid)

    programmes = defaultdict(list)
    has_now = defaultdict(bool)
    horizon = {}
    selected_ids = set(channels)

    for p in all_programmes:
        cid = (p.get("channel") or "").strip()
        if cid not in selected_ids or not fresh_programme(p, now):
            continue

        programmes[cid].append(p)

        start = parse_xmltv_time(p.get("start", ""))
        stop = parse_xmltv_time(p.get("stop", ""))
        if start:
            start_u = start.astimezone(timezone.utc)
            stop_u = (stop or (start + timedelta(hours=6))).astimezone(timezone.utc)
            if start_u <= now < stop_u:
                has_now[cid] = True
            if cid not in horizon or stop_u > horizon[cid]:
                horizon[cid] = stop_u

    return SourceData(
        name=spec["name"],
        priority=spec["priority"],
        url="",
        channels=channels,
        programmes=dict(programmes),
        exact_names=dict(exact_names),
        stripped_names=dict(stripped_names),
        has_now=dict(has_now),
        horizon=horizon,
        raw_channel_count=len(all_channels),
        raw_programme_count=len(all_programmes),
    )

def load_sources(now, relevance):
    sources = []
    failures = []

    for spec in SOURCES:
        errors = []
        loaded = None

        for url in spec["urls"]:
            try:
                raw = fetch(url, timeout=120 if spec["required"] else 35)
                data = build_source(spec, raw, now, relevance)
                data.url = url

                total_fresh = sum(len(v) for v in data.programmes.values())
                if spec["required"]:
                    if data.raw_channel_count < 100 or data.raw_programme_count < 1000:
                        raise RuntimeError(
                            f"fonte primaria incompleta: "
                            f"{data.raw_channel_count} canali / "
                            f"{data.raw_programme_count} programmi"
                        )

                if total_fresh == 0:
                    raise RuntimeError("0 programmi freschi pertinenti")

                loaded = data
                break
            except Exception as exc:
                errors.append(f"{url} -> {exc}")

        if loaded:
            sources.append(loaded)
            print(
                f"{loaded.name}: sorgente {loaded.raw_channel_count} canali / "
                f"{loaded.raw_programme_count} programmi; pertinenti "
                f"{len(loaded.channels)} canali / "
                f"{sum(len(v) for v in loaded.programmes.values())} programmi"
            )
        else:
            if spec["required"]:
                raise SafeSkipUpdate(
                    f'Fonte obbligatoria {spec["name"]} temporaneamente non disponibile: '
                    + " | ".join(errors)
                )
            failures.append((spec["name"], errors))
            print(
                f'ATTENZIONE: fonte opzionale {spec["name"]} saltata: '
                + " | ".join(errors)
            )

    return sources, failures

def add_candidate(bucket, source, cid, quality, reason):
    if cid not in source.channels:
        return
    if not source.programmes.get(cid):
        return

    cand = Candidate(source, cid, quality, reason)
    key = (source.name, cid)

    if key not in bucket or cand.score() > bucket[key].score():
        bucket[key] = cand

def candidates(block: M3uBlock, sources):
    bucket = {}
    keys = name_keys(block)

    for src in sources:
        # Explicit canonical name mapping.
        for key in keys:
            mapped = NAME_MAP.get(key)
            if mapped:
                add_candidate(bucket, src, mapped, 110, f"name-map:{key}")

        # Original ID.
        if block.old_id:
            add_candidate(bucket, src, block.old_id, 105, "old-id")

            mapped = ID_MAP.get(block.old_id)
            if mapped:
                add_candidate(bucket, src, mapped, 103, f"id-map:{block.old_id}")

        # Canonical hint.
        hint = canonical_hint(block)
        if hint:
            add_candidate(bucket, src, hint, 102, "canonical-hint")

        # Exact display-name.
        for key in keys:
            for cid in src.exact_names.get(key, set()):
                add_candidate(bucket, src, cid, 95, f"name-exact:{key}")

        # Stripped exact only if unique inside source.
        for raw in (block.name, block.tvg_name):
            sn = stripped_norm(raw)
            if len(sn) < 4:
                continue
            ids = src.stripped_names.get(sn, set())
            if len(ids) == 1:
                add_candidate(
                    bucket, src, next(iter(ids)), 85, f"name-stripped:{sn}"
                )

    return sorted(bucket.values(), key=lambda x: x.score(), reverse=True)

def choose_candidate(block, sources):
    cands = candidates(block, sources)
    return cands[0] if cands else None

def epg_icon(ch):
    icon = ch.find("icon")
    return (icon.get("src") or "").strip() if icon is not None else ""

def load_external_logos():
    by_name = {}
    by_stripped = {}
    try:
        raw = fetch(LOGO_SOURCE_URL, timeout=35).decode("utf-8", errors="replace")
    except Exception:
        return by_name, by_stripped

    for line in raw.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        name = channel_name(line)
        logo = get_logo(line)
        if not name or not logo:
            continue
        n = norm(name)
        sn = stripped_norm(name)
        if n:
            by_name.setdefault(n, logo)
        if sn:
            by_stripped.setdefault(sn, logo)

    return by_name, by_stripped

def manual_logo(name):
    n = norm(name)
    sn = stripped_norm(name)

    for key in (n, sn):
        if key in LOGO_MAP:
            return LOGO_MAP[key]

    # Families / variants.
    if n.startswith("supertennis plus") or n.startswith("super tennis plus"):
        return LOGO_MAP.get("supertennis", "")
    if n.startswith("rai sport jolly"):
        return LOGO_MAP.get("rai sport", "")

    for base, url in LOGO_MAP.items():
        if n == base or n.startswith(base + " "):
            return url

    return ""

def bad_logo(url):
    if not url:
        return True
    low = url.lower()
    return (
        "eu1-prod-images.disco-api.com" in low
        or "tv_icon.svg" in low
        or "placehold.co" in low
    )

def choose_logo(block, cand, extlogos):
    source_logo = get_logo(block.original_extinf)
    man = manual_logo(block.name)

    n = norm(block.name)
    force_manual = any(
        n == p or n.startswith(p + " ")
        for p in FORCE_MANUAL_LOGO_PREFIXES
    )

    if force_manual and man:
        return man

    if source_logo and not bad_logo(source_logo):
        return source_logo

    if man:
        return man

    if cand:
        ico = epg_icon(cand.source.channels[cand.source_id])
        if ico:
            return ico

    by_name, by_stripped = extlogos
    ext = by_name.get(n) or by_stripped.get(stripped_norm(block.name))
    if ext:
        return ext

    label = quote((block.name or "TV")[:24], safe="")
    return f"https://placehold.co/256x256/202020/FFFFFF.png?text={label}"

def append_epg_channel(out_root, output_ids, programme_keys, stable_id, block, cand):
    if stable_id not in output_ids:
        src_ch = copy.deepcopy(cand.source.channels[cand.source_id])
        src_ch.set("id", stable_id)

        # First display name exactly as the playlist.
        dn = ET.Element("display-name")
        dn.text = block.name
        src_ch.insert(0, dn)

        out_root.append(src_ch)
        output_ids.add(stable_id)

    added = 0
    for p in cand.source.programmes[cand.source_id]:
        cp = copy.deepcopy(p)
        cp.set("channel", stable_id)
        key = programme_key(cp, stable_id)
        if key in programme_keys:
            continue
        programme_keys.add(key)
        out_root.append(cp)
        added += 1

    return added

def run_update():
    now = datetime.now(timezone.utc)
    print("=== DAVIDE EPG + PLAYLIST SYNC MASTER ===")

    # 1) Source playlist.
    try:
        m3u = fetch(M3U_URL, timeout=90).decode("utf-8", errors="replace")
    except Exception as exc:
        raise SafeSkipUpdate(
            f"Playlist Altervista temporaneamente non disponibile: {exc}"
        )

    prefix, blocks = parse_m3u(m3u)

    if len(blocks) < 50:
        raise SafeSkipUpdate(
            f"Playlist Altervista anomala/incompleta: {len(blocks)} canali. "
            "Nessun file viene aggiornato."
        )

    wanted_payloads = target_payloads(blocks)

    # 2) EPG sources selected specifically for the current Altervista list.
    relevance = relevance_for_blocks(blocks)
    sources, failures = load_sources(now, relevance)

    # 3) External logo catalogue (optional).
    extlogos = load_external_logos()

    # 4) One mapping drives BOTH files.
    matches = []
    for b in blocks:
        cand = choose_candidate(b, sources)
        stable_id = safe_epg_id(b) if cand else ""
        matches.append((cand, stable_id))

    matched = sum(1 for c, _ in matches if c)
    if matched < 30:
        raise RuntimeError(
            f"Mapping EPG anomalo: solo {matched}/{len(blocks)} canali con guida. "
            "Output precedente mantenuto."
        )

    # 5) EPG.
    epg_root = ET.Element(
        "tv",
        {
            "generator-info-name": "davide-epg-playlist-sync",
            "generator-info-url": "https://github.com/dadocadavero-debug/epg-altervista",
        },
    )

    output_epg_ids = set()
    programme_keys = set()
    programme_counts = defaultdict(int)
    source_usage = defaultdict(int)
    group_total = defaultdict(int)
    group_matched = defaultdict(int)
    group_now = defaultdict(int)
    report_lines = []

    for b, (cand, stable_id) in zip(blocks, matches):
        group = b.group or "(senza gruppo)"
        group_total[group] += 1

        if not cand:
            report_lines.append(
                f"NO_GUIDE | {group} | {b.name} | old-id={b.old_id or '(vuoto)'}"
            )
            continue

        group_matched[group] += 1
        if cand.source.has_now.get(cand.source_id, False):
            group_now[group] += 1

        added = append_epg_channel(
            epg_root, output_epg_ids, programme_keys, stable_id, b, cand
        )
        programme_counts[stable_id] += added
        source_usage[cand.source.name] += 1

        report_lines.append(
            f"OK | {group} | {b.name} | {stable_id} <- "
            f"{cand.source_id} | {cand.source.name} | {cand.reason} | "
            f"now={cand.source.has_now.get(cand.source_id, False)} | "
            f"programmi={len(cand.source.programmes[cand.source_id])}"
        )

    # 6) M3U built from the same IDs.
    out_lines = [
        f'#EXTM3U x-tvg-url="{EPG_URL}" url-tvg="{EPG_URL}"'
    ]

    for idx, (b, payload, match) in enumerate(zip(blocks, wanted_payloads, matches)):
        cand, stable_id = match
        extinf = b.original_extinf

        if cand:
            extinf = set_attr(extinf, "tvg-id", stable_id)

        logo = choose_logo(b, cand, extlogos)
        extinf = set_attr(extinf, "tvg-logo", logo)

        out_lines.append(extinf)
        out_lines.extend(payload)

        # Stream/payload anti-regression check.
        n = norm(b.name)
        if b.group == "Rai" and n in RAI_EUROPA_SOURCE:
            expected_name = RAI_EUROPA_SOURCE[n]
            src = next(
                (x for x in blocks if norm(x.name) == expected_name),
                None,
            )
            if src is None or payload != src.payload:
                raise RuntimeError(
                    f"Validazione stream fallita per {b.name}: "
                    f"payload diverso da {expected_name}."
                )
        elif payload != b.payload:
            raise RuntimeError(
                f"Validazione stream fallita per {b.name}: "
                "payload Altervista modificato inaspettatamente."
            )

    # 7) Cross-validation M3U <-> XMLTV.
    epg_ids_with_programmes = {
        (p.get("channel") or "").strip()
        for p in epg_root.findall("programme")
        if (p.get("channel") or "").strip()
    }

    broken = []
    for b, (cand, stable_id) in zip(blocks, matches):
        if cand and stable_id not in epg_ids_with_programmes:
            broken.append(f"{b.name} -> {stable_id}")

    if broken:
        raise RuntimeError(
            "M3U/EPG non allineati: " + ", ".join(broken[:20])
        )

    # Core sanity.
    core_ok = 0
    for b, (cand, _) in zip(blocks, matches):
        if stripped_norm(b.name) in CORE_NAMES and cand:
            core_ok += 1
    if core_ok < 5:
        raise RuntimeError(
            f"Guide nazionali fondamentali insufficienti: {core_ok}/6."
        )

    # Every channel gets a logo.
    missing_logo = [
        channel_name(x)
        for x in out_lines
        if x.startswith("#EXTINF") and not get_logo(x)
    ]
    if missing_logo:
        raise RuntimeError(
            "Canali senza logo: " + ", ".join(missing_logo[:20])
        )

    # 8) Reports.
    report = [
        "DAVIDE EPG + PLAYLIST SYNC MASTER",
        f"Generato UTC: {now.isoformat(timespec='seconds')}",
        f"Canali Altervista: {len(blocks)}",
        f"Canali con guida reale/fresca: {matched}",
        f"EPG channel IDs: {len(output_epg_ids)}",
        f"Programmi XMLTV: {len(epg_root.findall('programme'))}",
        "",
        "COPERTURA PER CATEGORIA",
    ]

    for group in sorted(group_total, key=lambda g: (-group_total[g], g.lower())):
        report.append(
            f"{group}: guida={group_matched[group]}/{group_total[group]} | "
            f"programma-adesso={group_now[group]}/{group_total[group]}"
        )

    report += ["", "FONTI USATE"]
    for src, count in sorted(source_usage.items(), key=lambda x: (-x[1], x[0])):
        report.append(f"{src}: {count} canali")

    report += ["", "MAPPING"]
    report.extend(report_lines)

    if failures:
        report += ["", "FONTI OPZIONALI NON DISPONIBILI"]
        for name, errors in failures:
            report.append(f"{name}: " + " | ".join(errors))

    report_text = "\n".join(report) + "\n"

    # 9) Pubblicazione transazionale con rollback.
    ET.indent(epg_root, space="  ")

    epg_tmp = OUT_EPG.with_suffix(".xml.tmp")
    m3u_tmp = OUT_M3U.with_suffix(".m3u.tmp")
    epg_report_tmp = OUT_EPG_REPORT.with_suffix(".txt.tmp")
    mapping_report_tmp = OUT_MAPPING_REPORT.with_suffix(".txt.tmp")

    ET.ElementTree(epg_root).write(
        epg_tmp, encoding="utf-8", xml_declaration=True
    )
    m3u_tmp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    epg_report_tmp.write_text(report_text, encoding="utf-8")
    mapping_report_tmp.write_text(report_text, encoding="utf-8")

    # Validazione finale dei file temporanei.
    ET.parse(epg_tmp)
    tmp_m3u_text = m3u_tmp.read_text(encoding="utf-8", errors="strict")
    if not tmp_m3u_text.startswith("#EXTM3U "):
        raise RuntimeError("M3U temporanea non valida: header mancante.")
    if tmp_m3u_text.count("#EXTINF") != len(blocks):
        raise RuntimeError(
            f"M3U temporanea incompleta: {tmp_m3u_text.count('#EXTINF')} "
            f"EXTINF invece di {len(blocks)}."
        )

    destinations = [
        (epg_tmp, OUT_EPG),
        (m3u_tmp, OUT_M3U),
        (epg_report_tmp, OUT_EPG_REPORT),
        (mapping_report_tmp, OUT_MAPPING_REPORT),
    ]
    backups = {}
    published = []

    try:
        for _, dst in destinations:
            if dst.exists():
                bak = dst.with_suffix(dst.suffix + ".rollback")
                shutil.copy2(dst, bak)
                backups[dst] = bak

        for tmp, dst in destinations:
            tmp.replace(dst)
            published.append(dst)

    except Exception:
        for dst in published:
            bak = backups.get(dst)
            if bak and bak.exists():
                shutil.copy2(bak, dst)
            elif dst.exists():
                dst.unlink()

        for dst, bak in backups.items():
            if bak.exists() and not dst.exists():
                shutil.copy2(bak, dst)
        raise

    finally:
        for _, dst in destinations:
            bak = dst.with_suffix(dst.suffix + ".rollback")
            if bak.exists():
                bak.unlink()

    print()
    print("=== RISULTATO ===")
    print(f"Canali: {len(blocks)}")
    print(f"Con guida: {matched}")
    print(f"Programmi: {len(epg_root.findall('programme'))}")
    print("M3U ed EPG generati dalla STESSA mappa.")
    print("Stream non modificati, tranne Rai 1/2/3 <- rispettivi Europa.")

    print("Copertura per categoria:")
    for group in sorted(group_total, key=lambda g: (-group_total[g], g.lower()))[:40]:
        print(
            f"  {group}: {group_matched[group]}/{group_total[group]} "
            f"(adesso {group_now[group]})"
        )

    # Diagnostic channels requested repeatedly.
    wanted_diag = (
        "mediaset 20", "rai sport", "sport italia", "solocalcio",
        "super tennis", "supertennis", "juventus play", "inter tv",
        "inter 24 7", "fifa plus", "motoretro", "rally tv", "redbull tv",
    )
    print("Diagnostica canali chiave:")
    for b, (cand, stable_id) in zip(blocks, matches):
        if stripped_norm(b.name) in wanted_diag or norm(b.name) in wanted_diag:
            if cand:
                print(
                    f"  OK | {b.name} | {stable_id} <- {cand.source_id} | "
                    f"{cand.source.name} | "
                    f"{len(cand.source.programmes[cand.source_id])} programmi | "
                    f"now={cand.source.has_now.get(cand.source_id, False)}"
                )
            else:
                print(f"  NO GUIDE | {b.name} | old-id={b.old_id or '(vuoto)'}")

def main():
    try:
        run_update()
        return 0
    except SafeSkipUpdate as exc:
        print()
        print("=== SAFE NO-OP ===")
        print(str(exc))
        print("Nessun file pubblicato è stato modificato.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
