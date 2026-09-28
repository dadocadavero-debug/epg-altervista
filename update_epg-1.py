#!/usr/bin/env python3
"""
EPG MASTER DEFINITIVO - playlist-aware
2026-09-28

Scopo:
- genera SOLO epg.xml (non modifica tv_epg.m3u, update_playlist.py o gli stream);
- legge la playlist realmente pubblicata nel repository (tv_epg.m3u), se presente;
- usa anche la playlist Altervista corrente come sorgente di target aggiuntivi;
- scarica più fonti XMLTV e sceglie la guida migliore PER OGNI tvg-id della playlist;
- copia la guida sotto l'ID ESATTO usato dalla playlist, evitando di obbligare
  Fermata a conoscere gli ID interni delle varie fonti;
- non conserva guide scadute: il vecchio epg.xml è solo un fallback se contiene
  ancora programmi attuali/futuri;
- non inventa palinsesti per canali senza una vera fonte;
- scrive epg.xml atomicamente solo dopo le validazioni.

Architettura:
1) exact tvg-id
2) alias ID noto
3) mapping esplicito nome -> ID sorgente
4) tvg-name/display-name esatto
5) nome ripulito esatto e univoco
6) vecchio epg.xml ancora fresco come ultima risorsa

Le fonti opzionali possono fallire senza bloccare il run.
EPGShare IT1 è la base richiesta.
"""

from __future__ import annotations

import copy
import gzip
import lzma
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# ============================================================
# CONFIG
# ============================================================

OUT_EPG = Path("epg.xml")
OUT_REPORT = Path("epg_report.txt")
LOCAL_PLAYLIST = Path("tv_epg.m3u")
ALTERVISTA_M3U_URL = "https://inthemix.altervista.org/tv.m3u"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    ),
    "Accept": "*/*",
}

# Finestra utile: teniamo un po' di passato per il programma appena terminato
# e fino a 10 giorni avanti. Le fonti italiane gratuite normalmente hanno
# un orizzonte molto più corto.
PAST_GRACE = timedelta(hours=8)
FUTURE_LIMIT = timedelta(days=10)

SOURCES = [
    {
        "name": "EPGShare IT1",
        "urls": [
            "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
        ],
        "priority": 100,
        "required": True,
    },
    {
        "name": "Open-EPG Italy3",
        "urls": [
            "https://www.open-epg.com/files/italy3.xml.gz",
        ],
        "priority": 92,
        "required": False,
    },
    {
        "name": "Open-EPG Italy8",
        "urls": [
            "https://www.open-epg.com/files/italy8.xml.gz",
        ],
        "priority": 88,
        "required": False,
    },
    # Rytec resta opzionale. Viene usato soltanto se contiene programmi
    # freschi per un canale della playlist.
    {
        "name": "Rytec Italia Basic",
        "urls": [
            "http://www.xmltvepg.nl/rytecIT_Basic.xz",
            "http://rytecepg.wanwizard.eu/rytecIT_Basic.xz",
            "http://epg.vuplus-community.net/rytecIT_Basic.xz",
        ],
        "priority": 84,
        "required": False,
    },
    {
        "name": "Rytec Italia SportMovies",
        "urls": [
            "http://www.xmltvepg.nl/rytecIT_SportMovies.xz",
            "http://rytecepg.wanwizard.eu/rytecIT_SportMovies.xz",
            "http://epg.vuplus-community.net/rytecIT_SportMovies.xz",
        ],
        "priority": 83,
        "required": False,
    },
    {
        "name": "Rytec Italia Sky",
        "urls": [
            "http://www.xmltvepg.nl/rytecIT_Sky.xz",
            "http://rytecepg.wanwizard.eu/rytecIT_Sky.xz",
            "http://epg.vuplus-community.net/rytecIT_Sky.xz",
        ],
        "priority": 82,
        "required": False,
    },
    # Questa è la sorgente che nel progetto ha restituito realmente i FAST
    # sportivi (FIFA+, INTER 24/7, Juventus Play, Motoretrò, Rally TV, ecc.).
    {
        "name": "EPGShare Rakuten",
        "urls": [
            "https://epgshare01.online/epgshare01/epg_ripper_RAKUTEN1.xml.gz",
        ],
        "priority": 80,
        "required": False,
    },
    {
        "name": "EPGShare BE2",
        "urls": [
            "https://epgshare01.online/epgshare01/epg_ripper_BE2.xml.gz",
        ],
        "priority": 74,
        "required": False,
    },
    {
        "name": "Samsung TV Plus Italia",
        "urls": [
            "https://i.mjh.nz/SamsungTVPlus/it.xml.gz",
        ],
        "priority": 72,
        "required": False,
    },
    {
        "name": "Pluto TV Italia",
        "urls": [
            "https://i.mjh.nz/PlutoTV/it.xml.gz",
        ],
        "priority": 72,
        "required": False,
    },
    {
        "name": "EPGShare Plex",
        "urls": [
            "https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz",
        ],
        "priority": 68,
        "required": False,
    },
]

TECH_WORDS = {
    "hd", "sd", "hls", "dash", "hbbtv", "raiway", "akamai", "backup",
    "fps", "europa", "900p", "720p", "1080p", "4k", "uhd",
    "non", "sempre", "attivo", "attiva", "raramente",
}

# Alias del tvg-id: playlist -> possibili ID reali nelle fonti.
ID_ALIASES = {
    "Rete4.it": ("Rete.4.it", "Rete 4.it"),
    "Canale5.it": ("Canale.5.it", "Canale 5.it"),
    "Italia1.it": ("Italia.1.it", "Italia 1.it", "Italia Uno.it"),
    "20Mediaset.it": ("20.it", "20 Mediaset.it", "canale 20.it"),
    "Mediaset20.it": ("20.it", "20 Mediaset.it", "canale 20.it"),
    "Twentyseven.it": ("27.Twentyseven.it", "27Twentyseven.it", "Mediaset 27.it"),
    "TwentySeven.it": ("27.Twentyseven.it", "27Twentyseven.it", "Mediaset 27.it"),
    "la7": ("LA7.HD.it", "La7.it", "LA7.it"),
    "la7d": ("LA7.CINEMA.it", "LA7.Cinema.it"),
    "la5": ("La.5.it", "La5.it"),
    "LA5.it": ("La.5.it", "La5.it"),
    "Tv8.it": ("TV8.HD.it", "TV8.it", "Tv8.it"),
    "rai4.it": ("Rai4.it", "Rai 4.it"),
    "rai5.it": ("Rai5.it", "Rai 5.it"),
    "raimovie.it": ("RaiMovie.it", "Rai Movie.it"),
    "raipremium.it": ("RaiPremium.it", "Rai Premium.it"),
    "raisport": ("RaiSport.it", "Rai Sport.it"),
    "sportitalia": ("Sportitalia.it", "Sport Italia.it"),
    "SuperTennis.it": ("SuperTennis.HD.it", "SuperTennis.it"),
    "AciSportTV.it": ("ACI.Sport.Tv.it", "ACI Sport TV.it"),
    "bikesmartmobility": ("BIKE.it", "Bike.it"),
    "RealTime.it": ("Real.Time.it", "Real Time.it"),
    "foodnetwork.it": ("Food.Network.it", "Food Network.it"),
    "Giallo.it": ("Giallo.TV.it", "Giallo.it"),
    "TGCom24.it": ("TGCom.it", "TGCOM24.it"),
}

# Mapping esplicito solo quando la corrispondenza è semanticamente sicura.
# NON assegniamo la guida del canale principale a feed alternativi con
# programmazione potenzialmente diversa (es. SuperTennis+ 1/2/3/4).
NAME_SOURCE_IDS = {
    # Rai
    "rai 1": ("Rai1.it", "Rai 1.it", "Rai.1.HD..101.it"),
    "rai 1 europa": ("Rai1.it", "Rai 1.it", "Rai.1.HD..101.it"),
    "rai 2": ("Rai2.it", "Rai 2.it", "Rai.2.HD..102.it"),
    "rai 2 europa": ("Rai2.it", "Rai 2.it", "Rai.2.HD..102.it"),
    "rai 3": ("Rai3.it", "Rai 3.it", "Rai.3.HD..103.it"),
    "rai 3 europa": ("Rai3.it", "Rai 3.it", "Rai.3.HD..103.it"),
    "rai 4": ("Rai4.it", "Rai 4.it"),
    "rai 5": ("Rai5.it", "Rai 5.it"),
    "rai movie": ("RaiMovie.it", "Rai Movie.it"),
    "rai premium": ("RaiPremium.it", "Rai Premium.it"),
    "rai storia": ("RaiStoria.it", "Rai Storia.it"),
    "rai scuola": ("RaiScuola.it", "Rai Scuola.it"),
    "rai yoyo": ("RaiYoyo.it", "Rai YoYo.it"),
    "rai gulp": ("RaiGulp.it", "Rai Gulp.it"),
    "rai news 24": ("RaiNews24.it", "Rai News 24.it"),
    "rai sport": ("RaiSport.it", "Rai Sport.it"),
    "rai sport 900p": ("RaiSport.it", "Rai Sport.it"),

    # Mediaset
    "rete 4": ("Rete.4.it", "Rete 4.it"),
    "canale 5": ("Canale.5.it", "Canale 5.it"),
    "italia 1": ("Italia.1.it", "Italia 1.it", "Italia Uno.it"),
    "mediaset 20": ("20.it", "20 Mediaset.it", "canale 20.it"),
    "20 mediaset": ("20.it", "20 Mediaset.it", "canale 20.it"),
    "twentyseven": ("27.Twentyseven.it", "27Twentyseven.it", "Mediaset 27.it"),
    "27 twentyseven": ("27.Twentyseven.it", "27Twentyseven.it", "Mediaset 27.it"),
    "la5": ("La.5.it", "La5.it"),
    "cine 34": ("Cine34.it", "Cine 34.it"),
    "focus": ("Focus.it", "FocusTv.it"),
    "top crime": ("Top.Crime.it", "TopCrime.it"),
    "italia 2": ("Italia.2.it", "Italia2.it"),
    "mediaset extra": ("Mediaset.Extra.it", "MediasetExtra.it"),
    "tgcom24": ("TGCom.it", "TGCOM24.it"),
    "la7": ("LA7.HD.it", "La7.it", "LA7.it"),
    "la7 hd": ("LA7.HD.it", "La7.it", "LA7.it"),
    "la7 cinema": ("LA7.CINEMA.it", "LA7.Cinema.it"),
    "la7d": ("LA7.CINEMA.it", "LA7.Cinema.it"),
    "tv8": ("TV8.HD.it", "TV8.it", "Tv8.it"),
    "cielo": ("cielo.it", "Cielo.it"),
    "sky tg24": ("Sky.TG24.it",),
    "sky tg24 sd": ("Sky.TG24.it",),
    "class cnbc": ("Class.CNBC.it",),

    # Discovery / intrattenimento
    "nove": ("Nove.it", "NOVE.HD..149.it"),
    "nove backup": ("Nove.it", "NOVE.HD..149.it"),
    "real time": ("Real.Time.it", "RealTime.it"),
    "realtime": ("Real.Time.it", "RealTime.it"),
    "realtime backup": ("Real.Time.it", "RealTime.it"),
    "food network": ("Food.Network.it", "FoodNetwork.it"),
    "foodnetwork": ("Food.Network.it", "FoodNetwork.it"),
    "foodnetwork backup": ("Food.Network.it", "FoodNetwork.it"),
    "giallo": ("Giallo.TV.it", "Giallo.it"),
    "giallo backup": ("Giallo.TV.it", "Giallo.it"),
    "dmax": ("DMAX.it",),
    "dmax backup": ("DMAX.it",),
    "hgtv": ("HGTV.it",),
    "hgtv backup": ("HGTV.it",),
    "motor trend": ("Motor.Trend.it", "MotorTrend.it"),
    "turbo": ("Motor.Trend.it", "MotorTrend.it"),
    "turbo backup": ("Motor.Trend.it", "MotorTrend.it"),
    "k2": ("K2.it",),
    "frisbee": ("Frisbee.it",),

    # Sport lineare
    "sport italia": ("Sportitalia.it", "Sport Italia.it", "IT:.Sport.Italia.be"),
    "sportitalia": ("Sportitalia.it", "Sport Italia.it", "IT:.Sport.Italia.be"),
    "solocalcio": ("Solocalcio.it.it", "Solocalcio.it"),
    "super tennis": ("SuperTennis.HD.it", "SuperTennis.it"),
    "supertennis": ("SuperTennis.HD.it", "SuperTennis.it"),
    "aci sport tv": ("ACI.Sport.Tv.it", "ACI Sport TV.it"),
    "bike": ("BIKE.it", "Bike.it"),
    "inter tv": ("Inter.TV.it",),
    "top calcio 24": ("Top.Calcio.24.it", "TopCalcio24.it"),

    # Sport / FAST. Questi sono ID sorgente, ma l'output sarà sempre
    # rinominato con il tvg-id della playlist.
    "fifa plus": ("IT:.FIFA+.be",),
    "inter 24 7": ("IT:.INTER.24/7.be",),
    "juventus play": ("IT:.Juventus.Play.be",),
    "motoretro": ("IT:.Motoretrò.be",),
    "rally tv": ("IT:.Rally.TV.FAST+.be",),
    "redbull tv": ("IT:.Red.Bull.TV.be",),
    "red bull tv": ("IT:.Red.Bull.TV.be",),
    "tennis plus": ("IT:.Tennis+.be",),
    "racer international": ("IT:.RACER.International.be",),
    "pfl mma": ("IT:.PFL.MMA.be",),
    "glory kickboxing": ("IT:.GLORY.Kickboxing.be",),
    "top barca": ("IT:.TOP.Barça.be",),
    "motorvision tv": ("IT:.MOTORVISION.TV.be",),
}

REQUIRED_SOURCE_IDS = {
    "Rai1.it", "Rai2.it", "Rai3.it",
    "Rete.4.it", "Canale.5.it", "Italia.1.it",
}


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class PlaylistTarget:
    tvg_id: str
    name: str
    tvg_name: str
    group: str
    origin: str


@dataclass
class SourceData:
    name: str
    priority: int
    url: str
    channels: dict
    programmes: dict
    exact_names: dict
    stripped_names: dict
    fresh_counts: dict
    has_now: dict
    horizons: dict
    raw_channel_count: int
    raw_programme_count: int


@dataclass
class Candidate:
    source: SourceData
    source_id: str
    quality: int
    reason: str

    def score(self):
        horizon = self.source.horizons.get(self.source_id)
        horizon_ts = horizon.timestamp() if horizon else 0
        return (
            self.quality,
            self.source.priority,
            1 if self.source.has_now.get(self.source_id, False) else 0,
            horizon_ts,
            self.source.fresh_counts.get(self.source_id, 0),
        )


# ============================================================
# BASIC HELPERS
# ============================================================

def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def decompress(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if data[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(data)
    return data


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode().lower()
    value = value.replace("+", " plus ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def stripped_norm(value: str) -> str:
    toks = []
    for token in norm(value).split():
        if token in TECH_WORDS:
            continue
        if re.fullmatch(r"\d+(?:p|fps)", token):
            continue
        if token in {"hevc", "h265", "h264"}:
            continue
        toks.append(token)
    return " ".join(toks)


def get_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""


def channel_names(channel: ET.Element) -> list[str]:
    out = []
    for dn in channel.findall("display-name"):
        if dn.text and dn.text.strip():
            out.append(dn.text.strip())
    return out


def parse_xmltv_time(value: str):
    value = (value or "").strip()
    if not value:
        return None

    # XMLTV normalmente: YYYYMMDDHHMMSS +0200
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
            hours = int(offset[1:3])
            minutes = int(offset[3:5])
            tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
            return dt.replace(tzinfo=tz)

        # Se la fonte non specifica timezone, non inventiamo un offset.
        # Usiamo UTC solo per poter confrontare la freschezza in modo coerente.
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def programme_window(programme: ET.Element):
    start = parse_xmltv_time(programme.get("start", ""))
    stop = parse_xmltv_time(programme.get("stop", ""))
    return start, stop


def is_relevant_programme(programme: ET.Element, now_utc: datetime) -> bool:
    start, stop = programme_window(programme)
    if not start:
        return False
    if not stop:
        stop = start + timedelta(hours=6)

    start_utc = start.astimezone(timezone.utc)
    stop_utc = stop.astimezone(timezone.utc)

    return (
        stop_utc >= now_utc - PAST_GRACE
        and start_utc <= now_utc + FUTURE_LIMIT
    )


def programme_key(programme: ET.Element, target_id: str):
    title = programme.findtext("title") or ""
    return (
        target_id,
        programme.get("start") or "",
        programme.get("stop") or "",
        norm(title),
    )


# ============================================================
# PLAYLIST
# ============================================================

def parse_playlist(text: str, origin: str) -> list[PlaylistTarget]:
    targets = []
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue

        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
        target = PlaylistTarget(
            tvg_id=get_attr(line, "tvg-id"),
            name=name,
            tvg_name=get_attr(line, "tvg-name"),
            group=get_attr(line, "group-title"),
            origin=origin,
        )
        targets.append(target)

    return targets


def load_targets():
    targets = []
    diagnostics = []

    # 1) La playlist realmente usata dal repository ha precedenza.
    if LOCAL_PLAYLIST.exists():
        try:
            text = LOCAL_PLAYLIST.read_text(encoding="utf-8", errors="replace")
            local = parse_playlist(text, "tv_epg.m3u")
            targets.extend(local)
            diagnostics.append(f"tv_epg.m3u locale: {len(local)} canali")
        except Exception as exc:
            diagnostics.append(f"tv_epg.m3u locale non leggibile: {exc}")

    # 2) Altervista serve a intercettare canali nuovi/cambiati.
    try:
        text = fetch(ALTERVISTA_M3U_URL).decode("utf-8", errors="replace")
        remote = parse_playlist(text, "Altervista")
        if len(remote) < 50:
            raise RuntimeError(f"solo {len(remote)} canali")
        targets.extend(remote)
        diagnostics.append(f"Altervista: {len(remote)} canali")
    except Exception as exc:
        diagnostics.append(f"Altervista non disponibile: {exc}")

    if not targets:
        raise RuntimeError("Nessuna playlist disponibile per costruire il mapping EPG.")

    # Dedup: preserviamo nomi diversi con lo stesso ID perché possono aiutare il match.
    seen = set()
    deduped = []
    for t in targets:
        key = (t.tvg_id, norm(t.name), norm(t.tvg_name), norm(t.group))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)

    return deduped, diagnostics


# ============================================================
# EPG SOURCE LOADING
# ============================================================

def build_relevance(targets: list[PlaylistTarget]):
    """
    Costruisce il perimetro dei soli canali che possono servire alla playlist.
    Così non teniamo in memoria centinaia di migliaia di programmi estranei.
    """
    ids = set()
    names = set()
    stripped = set()

    for target in targets:
        if target.tvg_id:
            ids.add(target.tvg_id)
            ids.update(ID_ALIASES.get(target.tvg_id, ()))

        for raw_name in (target.name, target.tvg_name):
            n = norm(raw_name)
            sn = stripped_norm(raw_name)
            if n:
                names.add(n)
                ids.update(NAME_SOURCE_IDS.get(n, ()))
            if sn:
                stripped.add(sn)

    # Core sempre utile per compatibilità/validazione.
    ids.update(REQUIRED_SOURCE_IDS)

    return {
        "ids": ids,
        "names": names,
        "stripped": stripped,
    }


def build_source_data(name, priority, url, raw, now_utc, relevance) -> SourceData:
    root = ET.fromstring(decompress(raw))

    all_channel_elements = root.findall("channel")
    all_programme_elements = root.findall("programme")

    channels = {}
    exact_names = defaultdict(set)
    stripped_names = defaultdict(set)

    wanted_ids = relevance["ids"]
    wanted_names = relevance["names"]
    wanted_stripped = relevance["stripped"]

    # Prima selezioniamo SOLO i canali che possono davvero servire.
    for ch in all_channel_elements:
        cid = (ch.get("id") or "").strip()
        if not cid:
            continue

        displays = channel_names(ch)
        nset = {norm(x) for x in displays if norm(x)}
        sset = {stripped_norm(x) for x in displays if stripped_norm(x)}

        relevant = (
            cid in wanted_ids
            or bool(nset & wanted_names)
            or bool(sset & wanted_stripped)
        )
        if not relevant:
            continue

        channels[cid] = ch
        for n in nset:
            exact_names[n].add(cid)
        for sn in sset:
            stripped_names[sn].add(cid)

    programmes = defaultdict(list)
    fresh_counts = defaultdict(int)
    has_now = defaultdict(bool)
    horizons = {}

    selected_ids = set(channels)

    for p in all_programme_elements:
        cid = (p.get("channel") or "").strip()
        if cid not in selected_ids:
            continue
        if not is_relevant_programme(p, now_utc):
            continue

        programmes[cid].append(p)
        fresh_counts[cid] += 1

        start, stop = programme_window(p)
        if start:
            start_utc = start.astimezone(timezone.utc)
            stop_utc = (stop or (start + timedelta(hours=6))).astimezone(timezone.utc)
            if start_utc <= now_utc < stop_utc:
                has_now[cid] = True
            if cid not in horizons or stop_utc > horizons[cid]:
                horizons[cid] = stop_utc

    return SourceData(
        name=name,
        priority=priority,
        url=url,
        channels=channels,
        programmes=dict(programmes),
        exact_names=dict(exact_names),
        stripped_names=dict(stripped_names),
        fresh_counts=dict(fresh_counts),
        has_now=dict(has_now),
        horizons=horizons,
        raw_channel_count=len(all_channel_elements),
        raw_programme_count=len(all_programme_elements),
    )


def load_remote_source(spec, now_utc, relevance):
    errors = []

    for url in spec["urls"]:
        try:
            raw = fetch(url, timeout=120 if spec["required"] else 35)
            data = build_source_data(
                spec["name"], spec["priority"], url, raw, now_utc, relevance
            )

            if data.raw_channel_count == 0:
                raise RuntimeError("0 canali nella fonte")

            total_fresh = sum(data.fresh_counts.values())
            if total_fresh == 0:
                raise RuntimeError("0 programmi attuali/futuri utili alla playlist")

            if spec["required"]:
                if data.raw_channel_count < 100 or data.raw_programme_count < 1000:
                    raise RuntimeError(
                        f"fonte primaria incompleta: "
                        f"{data.raw_channel_count} canali / "
                        f"{data.raw_programme_count} programmi totali"
                    )

            return data, errors

        except Exception as exc:
            errors.append(f"{url} -> {exc}")

    if spec["required"]:
        raise RuntimeError(
            f'{spec["name"]} non disponibile: ' + " | ".join(errors)
        )

    return None, errors


def load_old_epg_source(now_utc, relevance):
    if not OUT_EPG.exists():
        return None
    try:
        raw = OUT_EPG.read_bytes()
        data = build_source_data(
            "EPG precedente ancora fresco",
            5,
            str(OUT_EPG),
            raw,
            now_utc,
            relevance,
        )
        if sum(data.fresh_counts.values()) == 0:
            return None
        return data
    except Exception:
        return None


# ============================================================
# MATCHING
# ============================================================

def target_names(target: PlaylistTarget):
    values = []
    for value in (target.name, target.tvg_name):
        n = norm(value)
        if n and n not in values:
            values.append(n)
    return values


def add_candidate(bucket, source, source_id, quality, reason):
    if source_id not in source.channels:
        return
    if source.fresh_counts.get(source_id, 0) <= 0:
        return

    key = (source.name, source_id)
    candidate = Candidate(source, source_id, quality, reason)

    previous = bucket.get(key)
    if previous is None or candidate.score() > previous.score():
        bucket[key] = candidate


def candidates_for_target(target: PlaylistTarget, sources: list[SourceData]):
    bucket = {}

    n_names = target_names(target)
    stripped = {
        stripped_norm(value)
        for value in (target.name, target.tvg_name)
        if stripped_norm(value)
    }

    for source in sources:
        # 1) Mapping esplicito per nome.
        for n in n_names:
            for source_id in NAME_SOURCE_IDS.get(n, ()):
                add_candidate(
                    bucket, source, source_id, 100,
                    f"mapping-nome:{n}"
                )

        # 2) tvg-id esatto.
        if target.tvg_id:
            add_candidate(
                bucket, source, target.tvg_id, 98,
                "tvg-id-esatto"
            )

            # 3) Alias tvg-id noto.
            for source_id in ID_ALIASES.get(target.tvg_id, ()):
                add_candidate(
                    bucket, source, source_id, 96,
                    f"alias-id:{target.tvg_id}"
                )

        # 4) Nome esatto / tvg-name esatto.
        for n in n_names:
            ids = source.exact_names.get(n, set())
            for source_id in ids:
                add_candidate(
                    bucket, source, source_id, 90,
                    f"nome-esatto:{n}"
                )

        # 5) Nome ripulito, ma SOLO se univoco dentro quella fonte.
        for sn in stripped:
            if len(sn) < 4:
                continue
            ids = source.stripped_names.get(sn, set())
            if len(ids) == 1:
                source_id = next(iter(ids))
                add_candidate(
                    bucket, source, source_id, 80,
                    f"nome-ripulito:{sn}"
                )

    return sorted(bucket.values(), key=lambda c: c.score(), reverse=True)


def choose_match(targets: list[PlaylistTarget], sources: list[SourceData]):
    all_candidates = []
    for target in targets:
        all_candidates.extend(candidates_for_target(target, sources))

    if not all_candidates:
        return None

    return max(all_candidates, key=lambda c: c.score())


# ============================================================
# OUTPUT
# ============================================================

def clone_channel_for_target(source_channel, target_id, display_name):
    ch = copy.deepcopy(source_channel)
    ch.set("id", target_id)

    # Mettiamo il nome della playlist come primo display-name per rendere
    # il file facile da ispezionare, senza eliminare i nomi originali.
    if display_name:
        first = ET.Element("display-name")
        first.text = display_name
        ch.insert(0, first)

    return ch


def append_schedule(
    out_root,
    channel_ids,
    programme_keys,
    target_id,
    display_name,
    candidate,
):
    if target_id not in channel_ids:
        source_channel = candidate.source.channels[candidate.source_id]
        out_root.append(
            clone_channel_for_target(source_channel, target_id, display_name)
        )
        channel_ids.add(target_id)

    added = 0
    for p in candidate.source.programmes.get(candidate.source_id, []):
        cloned = copy.deepcopy(p)
        cloned.set("channel", target_id)

        key = programme_key(cloned, target_id)
        if key in programme_keys:
            continue

        programme_keys.add(key)
        out_root.append(cloned)
        added += 1

    return added


def append_canonical_schedule(
    out_root,
    channel_ids,
    programme_keys,
    candidate,
):
    """
    Mantiene anche l'ID canonico della fonte scelta.
    Serve per compatibilità con update_playlist.py e per evitare regressioni
    se una riga della playlist usa già quell'ID.
    """
    cid = candidate.source_id
    if cid not in channel_ids:
        out_root.append(copy.deepcopy(candidate.source.channels[cid]))
        channel_ids.add(cid)

    added = 0
    for p in candidate.source.programmes.get(cid, []):
        cloned = copy.deepcopy(p)
        key = programme_key(cloned, cid)
        if key in programme_keys:
            continue
        programme_keys.add(key)
        out_root.append(cloned)
        added += 1

    return added


def coverage_for_root(root: ET.Element, target_ids: set[str], now_utc: datetime):
    with_fresh = set()
    for p in root.findall("programme"):
        cid = (p.get("channel") or "").strip()
        if cid not in target_ids:
            continue
        if is_relevant_programme(p, now_utc):
            with_fresh.add(cid)
    return with_fresh


def main():
    now_utc = datetime.now(timezone.utc)

    print("=== EPG MASTER DEFINITIVO / PLAYLIST-AWARE ===")
    print(f"Ora UTC: {now_utc.isoformat(timespec='seconds')}")

    # ------------------------------------------------------------
    # 1. Playlist target
    # ------------------------------------------------------------
    targets, target_diagnostics = load_targets()
    for line in target_diagnostics:
        print(line)

    by_id = defaultdict(list)
    no_id_targets = []

    for t in targets:
        if t.tvg_id:
            by_id[t.tvg_id].append(t)
        else:
            no_id_targets.append(t)

    if len(by_id) < 20:
        raise RuntimeError(
            f"Playlist anomala: solo {len(by_id)} tvg-id distinti."
        )

    print(
        f"Target: {len(targets)} righe / {len(by_id)} tvg-id distinti / "
        f"{len(no_id_targets)} righe senza tvg-id"
    )

    # ------------------------------------------------------------
    # 2. Fonti EPG
    # ------------------------------------------------------------
    relevance = build_relevance(targets)

    sources = []
    failures = []

    for spec in SOURCES:
        data, errors = load_remote_source(spec, now_utc, relevance)
        if data:
            sources.append(data)
            print(
                f"{data.name}: sorgente {data.raw_channel_count} canali / "
                f"{data.raw_programme_count} programmi; utili "
                f"{len(data.channels)} canali / "
                f"{sum(data.fresh_counts.values())} programmi freschi "
                f"[{data.url}]"
            )
        else:
            failures.append((spec["name"], errors))
            print(
                f"ATTENZIONE: {spec['name']} saltata: "
                + " | ".join(errors)
            )

    old_source = load_old_epg_source(now_utc, relevance)
    if old_source:
        sources.append(old_source)
        print(
            f"Fallback vecchio EPG: {len(old_source.channels)} canali / "
            f"{sum(old_source.fresh_counts.values())} programmi ancora freschi"
        )

    if not sources:
        raise RuntimeError("Nessuna fonte EPG disponibile.")

    # ------------------------------------------------------------
    # 3. Match PER tvg-id della playlist
    # ------------------------------------------------------------
    matches = {}
    unmatched_ids = []
    source_usage = defaultdict(int)

    for target_id, group_targets in by_id.items():
        match = choose_match(group_targets, sources)

        if match is None:
            unmatched_ids.append(target_id)
            continue

        matches[target_id] = match
        source_usage[match.source.name] += 1

    print()
    print(
        f"Match con programmi freschi: {len(matches)}/{len(by_id)} tvg-id "
        f"({len(matches)/len(by_id)*100:.1f}%)"
    )

    # ------------------------------------------------------------
    # 4. Generazione EPG
    # ------------------------------------------------------------
    out_root = ET.Element(
        "tv",
        {
            "generator-info-name": "epg-altervista-playlist-aware",
            "generator-info-url": (
                "https://github.com/dadocadavero-debug/epg-altervista"
            ),
        },
    )

    output_channel_ids = set()
    programme_keys = set()
    report_lines = []
    group_stats = defaultdict(lambda: [0, 0])  # matched, total

    for target_id, group_targets in sorted(by_id.items()):
        # Nome/gruppo rappresentativo: preferenza tv_epg.m3u locale.
        representative = sorted(
            group_targets,
            key=lambda t: (0 if t.origin == "tv_epg.m3u" else 1)
        )[0]

        group_name = representative.group or "(senza gruppo)"
        group_stats[group_name][1] += 1

        match = matches.get(target_id)
        if match is None:
            report_lines.append(
                f"NO_GUIDE | {target_id} | {representative.name} | "
                f"group={group_name}"
            )
            continue

        group_stats[group_name][0] += 1

        added = append_schedule(
            out_root=out_root,
            channel_ids=output_channel_ids,
            programme_keys=programme_keys,
            target_id=target_id,
            display_name=representative.name,
            candidate=match,
        )

        # Canonico della fonte: compatibilità.
        append_canonical_schedule(
            out_root=out_root,
            channel_ids=output_channel_ids,
            programme_keys=programme_keys,
            candidate=match,
        )

        report_lines.append(
            f"OK | {target_id} | {representative.name} | "
            f"<- {match.source_id} | {match.source.name} | "
            f"{match.reason} | {added} programmi"
        )

    # ------------------------------------------------------------
    # 5. Validazioni
    # ------------------------------------------------------------
    final_programmes = out_root.findall("programme")
    final_channels = out_root.findall("channel")

    if len(final_channels) < 50:
        raise RuntimeError(
            f"EPG finale troppo piccolo: {len(final_channels)} canali."
        )

    if len(final_programmes) < 1000:
        raise RuntimeError(
            f"EPG finale troppo piccolo: {len(final_programmes)} programmi."
        )

    final_channel_ids = {
        (ch.get("id") or "").strip()
        for ch in final_channels
        if (ch.get("id") or "").strip()
    }

    # Ogni programme deve riferirsi a un <channel>.
    orphan_ids = sorted({
        (p.get("channel") or "").strip()
        for p in final_programmes
        if (p.get("channel") or "").strip() not in final_channel_ids
    })
    if orphan_ids:
        raise RuntimeError(
            "Programmi orfani per ID: " + ", ".join(orphan_ids[:20])
        )

    # Core nazionale: deve essere presente come canonico o come alias usato
    # dalla playlist.
    canonical_present = final_channel_ids & REQUIRED_SOURCE_IDS
    if len(canonical_present) < 5:
        raise RuntimeError(
            "EPG nazionale anomalo: troppo pochi ID core presenti: "
            + ", ".join(sorted(canonical_present))
        )

    # Anti-regressione sensata: confrontiamo COPERTURA FRESCA, non il numero
    # grezzo di programmi (che varia durante il giorno).
    old_coverage = set()
    if OUT_EPG.exists():
        try:
            old_root = ET.parse(OUT_EPG).getroot()
            old_coverage = coverage_for_root(
                old_root, set(by_id), now_utc
            )
        except Exception:
            old_coverage = set()

    new_coverage = set(matches)

    if len(old_coverage) >= 20:
        minimum = max(20, int(len(old_coverage) * 0.85))
        if len(new_coverage) < minimum:
            raise RuntimeError(
                f"Anti-regressione copertura: nuovo EPG {len(new_coverage)} "
                f"tvg-id con guida fresca, vecchio {len(old_coverage)}. "
                f"Minimo accettato {minimum}. Vecchio epg.xml mantenuto."
            )

    # ------------------------------------------------------------
    # 6. Report
    # ------------------------------------------------------------
    report = []
    report.append("EPG MASTER DEFINITIVO / PLAYLIST-AWARE")
    report.append(f"Generato UTC: {now_utc.isoformat(timespec='seconds')}")
    report.append(
        f"Target tvg-id: {len(by_id)} | con guida fresca: {len(matches)} | "
        f"senza guida: {len(unmatched_ids)}"
    )
    report.append(
        f"EPG finale: {len(final_channels)} canali / "
        f"{len(final_programmes)} programmi"
    )
    report.append("")
    report.append("COPERTURA PER GRUPPO")
    for group, (matched, total) in sorted(
        group_stats.items(),
        key=lambda item: (-item[1][1], item[0].lower())
    ):
        report.append(f"{group}: {matched}/{total}")
    report.append("")
    report.append("USO FONTI")
    for source_name, count in sorted(
        source_usage.items(), key=lambda item: (-item[1], item[0])
    ):
        report.append(f"{source_name}: {count} tvg-id")
    report.append("")
    report.append("MAPPING")
    report.extend(report_lines)

    if no_id_targets:
        report.append("")
        report.append("RIGHE PLAYLIST SENZA TVG-ID (EPG non collegabile senza modificare la playlist)")
        for t in no_id_targets[:200]:
            report.append(
                f"{t.origin} | {t.group or '(senza gruppo)'} | {t.name}"
            )

    if failures:
        report.append("")
        report.append("FONTI OPZIONALI NON DISPONIBILI")
        for name, errors in failures:
            report.append(f"{name}: " + " | ".join(errors))

    OUT_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    # ------------------------------------------------------------
    # 7. Scrittura atomica
    # ------------------------------------------------------------
    ET.indent(out_root, space="  ")
    tmp = OUT_EPG.with_suffix(".xml.tmp")
    ET.ElementTree(out_root).write(
        tmp, encoding="utf-8", xml_declaration=True
    )
    tmp.replace(OUT_EPG)

    # ------------------------------------------------------------
    # 8. Log leggibile
    # ------------------------------------------------------------
    print()
    print("=== RISULTATO ===")
    print(
        f"EPG finale: {len(final_channels)} canali / "
        f"{len(final_programmes)} programmi"
    )
    print(
        f"Playlist: {len(matches)}/{len(by_id)} tvg-id con guida fresca"
    )
    print("Copertura per gruppo:")
    for group, (matched, total) in sorted(
        group_stats.items(),
        key=lambda item: (-item[1][1], item[0].lower())
    )[:30]:
        print(f"  {group}: {matched}/{total}")

    print("Fonti usate:")
    for source_name, count in sorted(
        source_usage.items(), key=lambda item: (-item[1], item[0])
    ):
        print(f"  {source_name}: {count}")

    if unmatched_ids:
        print("Primi tvg-id ancora senza una guida REALE/fresca:")
        for target_id in unmatched_ids[:50]:
            representative = by_id[target_id][0]
            print(
                f"  - {target_id} | {representative.name} | "
                f"{representative.group or '(senza gruppo)'}"
            )

    if no_id_targets:
        print(
            f"ATTENZIONE: {len(no_id_targets)} righe playlist non hanno tvg-id; "
            "un file EPG da solo non può collegarle in modo affidabile."
        )

    print(f"Report completo: {OUT_REPORT}")
    print("epg.xml scritto atomicamente.")
    print("NESSUNO stream o file playlist è stato modificato.")


if __name__ == "__main__":
    main()
