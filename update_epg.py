#!/usr/bin/env python3
"""
EPG MASTER CUMULATIVO - 2026-09-26

Obiettivo:
- NON tocca update_playlist.py né gli stream.
- Mantiene EPGShare IT1 come base/priorità assoluta.
- Aggiunge guide pertinenti da più fonti FAST/streaming.
- Non aggiunge alla cieca migliaia di canali estranei: le fonti secondarie
  vengono filtrate usando la playlist Altervista corrente, gli ID già presenti
  nel vecchio epg.xml e alcuni ID extra già noti.
- Se una fonte secondaria fallisce, continua con le altre.
- Se la fonte primaria o le validazioni fondamentali falliscono, NON
  sovrascrive il vecchio epg.xml.
- Scrittura atomica.
"""

import copy
import gzip
import io
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT_EPG = Path("epg.xml")
M3U_URL = "https://inthemix.altervista.org/tv.m3u"

SOURCES = [
    {
        "name": "EPGShare IT1",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
        "required": True,
        "primary": True,
    },
    {
        "name": "EPGShare Rakuten",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_RAKUTEN1.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "Samsung TV Plus Italia",
        "url": "https://i.mjh.nz/SamsungTVPlus/it.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "Pluto TV Italia",
        "url": "https://i.mjh.nz/PlutoTV/it.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "EPGShare Plex",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz",
        "required": False,
        "primary": False,
    },
]

# ID che erano già usati nel progetto per canali sport/FAST.
# Li preserviamo anche se il nome della fonte non coincide perfettamente
# con il nome visualizzato nella M3U.
FORCE_SECONDARY_IDS = {
    "IT:.FIFA+.be",
    "IT:.INTER.24/7.be",
    "IT:.Juventus.Play.be",
    "IT:.Motoretrò.be",
    "IT:.Rally.TV.FAST+.be",
    "IT:.Red.Bull.TV.be",
    "IT:.Tennis+.be",
}

REQUIRED_CORE_IDS = {
    "Rai1.it",
    "Rai2.it",
    "Rai3.it",
    "Rete.4.it",
    "Canale.5.it",
    "Italia.1.it",
}

TECH_WORDS = {
    "hd", "sd", "hls", "dash", "hbbtv", "raiway", "akamai", "backup",
    "fps", "europa", "900p", "720p", "1080p", "4k", "uhd",
    "tv", "italia",
}

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    ),
    "Accept": "*/*",
}


def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def decompress_if_needed(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode().lower()
    value = value.replace("+", " plus ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def stripped_norm(value: str) -> str:
    tokens = [
        token
        for token in norm(value).split()
        if token not in TECH_WORDS and not re.fullmatch(r"\d+p", token)
    ]
    return " ".join(tokens)


def get_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf)
    return m.group(1).strip() if m else ""


def parse_playlist_targets(m3u_text: str):
    extinf_lines = [line for line in m3u_text.splitlines() if line.startswith("#EXTINF")]
    if len(extinf_lines) < 50:
        raise RuntimeError(
            f"Playlist Altervista incompleta: solo {len(extinf_lines)} righe EXTINF."
        )

    ids = set()
    names = set()
    stripped_names = set()

    for line in extinf_lines:
        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
        tvg_id = get_attr(line, "tvg-id")
        tvg_name = get_attr(line, "tvg-name")

        if tvg_id:
            ids.add(tvg_id)

        for candidate in (name, tvg_name):
            if not candidate:
                continue
            n = norm(candidate)
            sn = stripped_norm(candidate)
            if n:
                names.add(n)
            if sn:
                stripped_names.add(sn)

    return ids, names, stripped_names, len(extinf_lines)


def old_epg_info(path: Path):
    if not path.exists():
        return set(), 0, 0

    try:
        root = ET.parse(path).getroot()
    except Exception:
        return set(), 0, 0

    ids = {
        ch.get("id")
        for ch in root.findall("channel")
        if ch.get("id")
    }
    return ids, len(ids), len(root.findall("programme"))


def channel_names(channel_el):
    result = []
    for dn in channel_el.findall("display-name"):
        if dn.text and dn.text.strip():
            result.append(dn.text.strip())
    return result


def programme_key(programme):
    # Dedup conservativo: stesso canale + stesso intervallo + stesso titolo.
    title = programme.findtext("title") or ""
    return (
        programme.get("channel") or "",
        programme.get("start") or "",
        programme.get("stop") or "",
        norm(title),
    )


def parse_source(source):
    raw = fetch(source["url"])
    xml = decompress_if_needed(raw)
    root = ET.fromstring(xml)

    channels = root.findall("channel")
    programmes = root.findall("programme")

    if source["required"]:
        if len(channels) < 100 or len(programmes) < 1000:
            raise RuntimeError(
                f'{source["name"]} sembra incompleto: '
                f"{len(channels)} canali / {len(programmes)} programmi."
            )
    elif len(channels) == 0:
        raise RuntimeError(f'{source["name"]} non contiene canali.')

    return root


def main():
    print("=== EPG MASTER CUMULATIVO ===")

    # ------------------------------------------------------------
    # 1. Target reali: playlist Altervista + ID già presenti nel vecchio EPG
    # ------------------------------------------------------------
    m3u = fetch(M3U_URL).decode("utf-8", errors="replace")
    target_ids, target_names, target_stripped, playlist_count = parse_playlist_targets(m3u)

    old_ids, old_channel_count, old_programme_count = old_epg_info(OUT_EPG)
    target_ids |= old_ids
    target_ids |= FORCE_SECONDARY_IDS

    print(f"Playlist Altervista: {playlist_count} canali")
    print(
        f"EPG precedente: {old_channel_count} canali / "
        f"{old_programme_count} programmi"
    )

    # ------------------------------------------------------------
    # 2. Output XMLTV
    # ------------------------------------------------------------
    out_root = ET.Element("tv", {
        "generator-info-name": "epg-altervista-master",
        "generator-info-url": "https://github.com/dadocadavero-debug/epg-altervista",
    })

    output_ids = set()
    output_normalized_names = set()
    programme_keys = set()

    source_stats = []
    optional_failures = []
    primary_channel_count = 0
    primary_programme_count = 0

    # ------------------------------------------------------------
    # 3. Merge con priorità.
    #    IT1 entra interamente.
    #    Le secondarie entrano solo se utili alla playlist/progetto.
    # ------------------------------------------------------------
    for source in SOURCES:
        try:
            root = parse_source(source)
        except Exception as exc:
            if source["required"]:
                raise
            optional_failures.append(f'{source["name"]}: {exc}')
            print(f'ATTENZIONE: fonte opzionale saltata: {source["name"]}: {exc}')
            continue

        channels = root.findall("channel")
        programmes = root.findall("programme")

        if source["primary"]:
            primary_channel_count = len(channels)
            primary_programme_count = len(programmes)

        source_channel_by_id = {}
        selected_ids = set()

        for ch in channels:
            cid = (ch.get("id") or "").strip()
            if not cid:
                continue
            source_channel_by_id[cid] = ch

            names = channel_names(ch)
            normalized = {norm(x) for x in names if norm(x)}
            stripped = {stripped_norm(x) for x in names if stripped_norm(x)}

            if source["primary"]:
                selected_ids.add(cid)
                continue

            # Priorità massima agli ID già noti / già usati.
            if cid in target_ids:
                selected_ids.add(cid)
                continue

            exact_name_match = bool(normalized & target_names)
            stripped_name_match = bool(stripped & target_stripped)

            # Non introduciamo un secondo canale con lo stesso nome di uno già
            # presente da una fonte più prioritaria, a meno che l'ID sia
            # esplicitamente richiesto.
            conflicts = bool(normalized & output_normalized_names)

            if exact_name_match and not conflicts:
                selected_ids.add(cid)
            elif stripped_name_match and not conflicts:
                selected_ids.add(cid)

        # Canali: l'ID già presente vince sempre (fonte precedente/prioritaria).
        actually_added = set()
        for cid in selected_ids:
            if cid in output_ids:
                continue
            ch = source_channel_by_id.get(cid)
            if ch is None:
                continue

            out_root.append(copy.deepcopy(ch))
            output_ids.add(cid)
            actually_added.add(cid)

            for display_name in channel_names(ch):
                n = norm(display_name)
                if n:
                    output_normalized_names.add(n)

        # Programmi: solo per ID effettivamente aggiunti da questa fonte.
        # Se un ID era già presente da una fonte precedente, la fonte precedente
        # resta proprietaria della sua guida: niente schedule sovrapposti.
        added_programmes = 0
        for programme in programmes:
            cid = (programme.get("channel") or "").strip()
            if cid not in actually_added:
                continue

            key = programme_key(programme)
            if key in programme_keys:
                continue

            programme_keys.add(key)
            out_root.append(copy.deepcopy(programme))
            added_programmes += 1

        source_stats.append(
            (
                source["name"],
                len(channels),
                len(programmes),
                len(actually_added),
                added_programmes,
            )
        )

        print(
            f'{source["name"]}: sorgente {len(channels)} canali / '
            f"{len(programmes)} programmi -> aggiunti "
            f"{len(actually_added)} canali / {added_programmes} programmi"
        )

        # libera memoria tra una fonte e l'altra
        del root

    # ------------------------------------------------------------
    # 4. Validazioni anti-regressione
    # ------------------------------------------------------------
    final_channels = len(output_ids)
    final_programmes = len(programme_keys)

    missing_core = sorted(REQUIRED_CORE_IDS - output_ids)
    if missing_core:
        raise RuntimeError(
            "EPG finale privo di ID fondamentali: " + ", ".join(missing_core)
        )

    if final_channels < 100 or final_programmes < 1000:
        raise RuntimeError(
            f"EPG finale anomalo: {final_channels} canali / "
            f"{final_programmes} programmi."
        )

    # Anti-regressione corretta:
    # NON confrontiamo il numero di programmi col vecchio epg.xml perché la
    # finestra temporale delle guide cambia durante la giornata e tra un run e
    # l'altro. Il vecchio file può quindi avere più programmi pur essendo meno
    # aggiornato.
    #
    # Confrontiamo invece il risultato con la fonte primaria DEL RUN CORRENTE:
    # il merge finale non deve perdere canali/programmi già presenti in IT1.
    if primary_channel_count < 100 or primary_programme_count < 1000:
        raise RuntimeError(
            f"Fonte primaria corrente anomala: {primary_channel_count} canali / "
            f"{primary_programme_count} programmi. Il vecchio epg.xml viene mantenuto."
        )

    if final_channels < primary_channel_count:
        raise RuntimeError(
            f"Anti-regressione: EPG finale con {final_channels} canali, "
            f"meno dei {primary_channel_count} della fonte primaria corrente. "
            "Il vecchio epg.xml viene mantenuto."
        )

    if final_programmes < primary_programme_count:
        raise RuntimeError(
            f"Anti-regressione: EPG finale con {final_programmes} programmi, "
            f"meno dei {primary_programme_count} della fonte primaria corrente. "
            "Il vecchio epg.xml viene mantenuto."
        )

    # ------------------------------------------------------------
    # 5. Report dei canali Altervista che ancora non trovano nessun candidato
    #    per nome/ID nell'EPG finale.
    # ------------------------------------------------------------
    # Ricostruisce un indice nomi finale.
    final_names = set()
    final_stripped = set()
    for ch in out_root.findall("channel"):
        for dn in channel_names(ch):
            n = norm(dn)
            sn = stripped_norm(dn)
            if n:
                final_names.add(n)
            if sn:
                final_stripped.add(sn)

    unmatched = []
    for line in m3u.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
        cid = get_attr(line, "tvg-id")
        n = norm(name)
        sn = stripped_norm(name)

        if (
            (cid and cid in output_ids)
            or (n and n in final_names)
            or (sn and sn in final_stripped)
        ):
            continue
        unmatched.append(name)

    # ------------------------------------------------------------
    # 6. Scrittura atomica
    # ------------------------------------------------------------
    ET.indent(out_root, space="  ")
    tree = ET.ElementTree(out_root)

    tmp = OUT_EPG.with_suffix(".xml.tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    tmp.replace(OUT_EPG)

    print()
    print("=== RISULTATO ===")
    print(f"EPG finale: {final_channels} canali / {final_programmes} programmi")
    print(
        f"Fonte primaria corrente: {primary_channel_count} canali / "
        f"{primary_programme_count} programmi"
    )
    print(f"Canali Altervista ancora senza candidato EPG: {len(unmatched)}")

    if unmatched:
        print("Primi canali ancora senza EPG:")
        for name in unmatched[:50]:
            print(f"  - {name}")

    if optional_failures:
        print("Fonti opzionali non disponibili in questa esecuzione:")
        for failure in optional_failures:
            print(f"  - {failure}")

    print("epg.xml aggiornato atomicamente.")
    print("update_playlist.py e gli stream NON sono stati modificati.")


if __name__ == "__main__":
    main()
