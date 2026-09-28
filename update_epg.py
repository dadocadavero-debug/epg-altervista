#!/usr/bin/env python3
"""
EPG MASTER CUMULATIVO V5 - 2026-09-28

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

# Fonte supplementare specifica per la guida Mediaset.
# Viene usata in modo mirato per 20 Mediaset, senza sovrascrivere
# le guide già funzionanti degli altri canali.
MEDIASET_EPG_URL = "https://iptv-org.github.io/epg/guides/it/mediaset.it.xml"

# Entrambi gli ID vengono pubblicati con la stessa guida, così la playlist
# funziona indipendentemente dal fatto che usi 20.it o 20Mediaset.it.
MEDIASET20_ALIAS_IDS = ("20.it", "20Mediaset.it")
MEDIASET20_NAMES = {
    "20 mediaset",
    "mediaset 20",
    "canale 20",
    "20",
}

SOURCES = [
    {
        "name": "EPGShare IT1",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
        "required": True,
        "primary": True,
    },
    {
        "name": "EPGShare Rakuten Italia",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_RAKUTEN_IT1.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "EPGShare Rally TV",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_RALLY_TV1.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "EPGShare Tennis",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_TENNIS1.xml.gz",
        "required": False,
        "primary": False,
    },
    {
        "name": "EPGShare BE2 FAST/Sport",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_BE2.xml.gz",
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
    "IT:.Sport.Italia.be",
    "IT:.Motorsport.tv.be",
    "IT:.MOTORVISION.TV.be",
    "IT:.RACER.International.be",
    "IT:.PFL.MMA.be",
    "IT:.GLORY.Kickboxing.be",
    "IT:.TOP.Barça.be",
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
        return set(), 0, 0, {}

    try:
        root = ET.parse(path).getroot()
    except Exception:
        return set(), 0, 0, {}

    ids = {
        ch.get("id")
        for ch in root.findall("channel")
        if ch.get("id")
    }

    counts = {}
    for programme in root.findall("programme"):
        cid = (programme.get("channel") or "").strip()
        if cid:
            counts[cid] = counts.get(cid, 0) + 1

    return ids, len(ids), len(root.findall("programme")), counts


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


def programme_counts_by_channel(root):
    counts = {}
    for programme in root.findall("programme"):
        cid = (programme.get("channel") or "").strip()
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    return counts


def ensure_channel_alias(out_root, source_channel, alias_id):
    """
    Garantisce che esista <channel id="alias_id">.
    Se esiste già, lo preserva. Altrimenti clona il canale sorgente
    cambiando soltanto l'ID.
    """
    for ch in out_root.findall("channel"):
        if (ch.get("id") or "").strip() == alias_id:
            return False

    cloned = copy.deepcopy(source_channel)
    cloned.set("id", alias_id)
    out_root.append(cloned)
    return True


def hydrate_mediaset20(out_root, output_ids, programme_keys):
    """
    Integra la guida di 20 Mediaset da una fonte dedicata.

    Punto importante: il vecchio merge poteva avere un <channel> valido
    ma ZERO <programme> per quell'ID. In quel caso il player vedeva il canale
    ma non mostrava alcuna guida.

    Qui troviamo la guida reale per 20 Mediaset e la pubblichiamo sotto
    ENTRAMBI gli ID usati nel progetto: 20.it e 20Mediaset.it.
    """
    raw = fetch(MEDIASET_EPG_URL)
    root = ET.fromstring(decompress_if_needed(raw))

    channels = root.findall("channel")
    programmes = root.findall("programme")

    source_channel = None
    source_id = ""

    # Prima proviamo gli ID noti.
    for ch in channels:
        cid = (ch.get("id") or "").strip()
        if cid in MEDIASET20_ALIAS_IDS:
            source_channel = ch
            source_id = cid
            break

    # Se la fonte usa un ID differente, troviamo il canale per display-name.
    if source_channel is None:
        for ch in channels:
            names = {norm(x) for x in channel_names(ch)}
            if names & MEDIASET20_NAMES:
                source_channel = ch
                source_id = (ch.get("id") or "").strip()
                break

    if source_channel is None or not source_id:
        raise RuntimeError(
            "Fonte Mediaset disponibile ma canale 20 Mediaset non trovato."
        )

    source_programmes = [
        p for p in programmes
        if (p.get("channel") or "").strip() == source_id
    ]

    if not source_programmes:
        raise RuntimeError(
            f"Fonte Mediaset: trovato {source_id}, ma senza programmi."
        )

    aliases_added = 0
    programmes_added = 0

    for alias_id in MEDIASET20_ALIAS_IDS:
        if ensure_channel_alias(out_root, source_channel, alias_id):
            output_ids.add(alias_id)
            aliases_added += 1

        for source_programme in source_programmes:
            cloned = copy.deepcopy(source_programme)
            cloned.set("channel", alias_id)

            key = programme_key(cloned)
            if key in programme_keys:
                continue

            programme_keys.add(key)
            out_root.append(cloned)
            programmes_added += 1

    return {
        "source_id": source_id,
        "source_programmes": len(source_programmes),
        "aliases_added": aliases_added,
        "programmes_added": programmes_added,
    }


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
    playlist_tvg_ids = set(target_ids)

    old_ids, old_channel_count, old_programme_count, old_programme_counts = old_epg_info(OUT_EPG)
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
    output_name_to_ids = {}
    programme_keys = set()
    programme_count_by_id = {}

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
        channel_names_by_id = {}

        for ch in channels:
            cid = (ch.get("id") or "").strip()
            if not cid:
                continue

            source_channel_by_id[cid] = ch

            names = channel_names(ch)
            normalized = {norm(x) for x in names if norm(x)}
            stripped = {stripped_norm(x) for x in names if stripped_norm(x)}
            channel_names_by_id[cid] = (normalized, stripped)

            if source["primary"]:
                selected_ids.add(cid)
                continue

            # ID già noto/necessario: includilo sempre come candidato.
            if cid in target_ids:
                selected_ids.add(cid)
                continue

            # Altrimenti selezioniamo solo canali che corrispondono davvero
            # a un nome presente nella playlist Altervista.
            if (normalized & target_names) or (stripped & target_stripped):
                selected_ids.add(cid)

        # Mappa ID sorgente -> ID destinazione programmi.
        # La novità V4 è che una fonte secondaria può RIEMPIRE una guida vuota
        # già creata da una fonte più prioritaria, invece di essere scartata.
        programme_target = {}
        actually_added = set()

        for cid in selected_ids:
            ch = source_channel_by_id.get(cid)
            if ch is None:
                continue

            normalized, stripped = channel_names_by_id.get(cid, (set(), set()))

            if cid in output_ids:
                # Stesso ID già presente.
                # Se non ha ancora programmi, permettiamo alla fonte corrente
                # di fornire la guida.
                if programme_count_by_id.get(cid, 0) == 0:
                    programme_target[cid] = cid
                continue

            # Se una fonte usa un ID diverso ma il nome coincide con un canale
            # già presente, possiamo usare la sua guida per riempire SOLO
            # un canale esistente rimasto a zero programmi.
            matching_existing_ids = set()
            for n in normalized:
                matching_existing_ids |= output_name_to_ids.get(n, set())

            empty_existing_ids = [
                existing_id
                for existing_id in matching_existing_ids
                if programme_count_by_id.get(existing_id, 0) == 0
            ]

            if len(empty_existing_ids) == 1:
                programme_target[cid] = empty_existing_ids[0]
                continue

            # Nessun conflitto utile: aggiungiamo il canale come nuovo ID.
            out_root.append(copy.deepcopy(ch))
            output_ids.add(cid)
            actually_added.add(cid)
            programme_target[cid] = cid
            programme_count_by_id.setdefault(cid, 0)

            for display_name in channel_names(ch):
                n = norm(display_name)
                if n:
                    output_normalized_names.add(n)
                    output_name_to_ids.setdefault(n, set()).add(cid)

        # Programmi:
        # - primaria: normali;
        # - secondarie: possono riempire ID già presenti ma ancora SENZA guida;
        # - se un ID ha già programmi da una fonte prioritaria, non li sovrapponiamo.
        added_programmes = 0
        for programme in programmes:
            source_cid = (programme.get("channel") or "").strip()
            target_cid = programme_target.get(source_cid)
            if not target_cid:
                continue

            # Per una sorgente secondaria smettiamo di riempire se il target
            # aveva già una guida prima di questa fonte.
            cloned = copy.deepcopy(programme)
            if target_cid != source_cid:
                cloned.set("channel", target_cid)

            key = programme_key(cloned)
            if key in programme_keys:
                continue

            programme_keys.add(key)
            out_root.append(cloned)
            programme_count_by_id[target_cid] = programme_count_by_id.get(target_cid, 0) + 1
            added_programmes += 1

        # Ricostruisce/aggiorna l'indice nomi dei canali output.
        # Serve alle fonti successive per riempire guide vuote usando anche
        # un ID differente ma lo stesso display-name.
        for ch in out_root.findall("channel"):
            cid = (ch.get("id") or "").strip()
            if not cid:
                continue
            output_ids.add(cid)
            programme_count_by_id.setdefault(cid, 0)
            for display_name in channel_names(ch):
                n = norm(display_name)
                if n:
                    output_normalized_names.add(n)
                    output_name_to_ids.setdefault(n, set()).add(cid)

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
    # 3B. INTEGRAZIONE MIRATA MEDIASET 20
    # ------------------------------------------------------------
    # Non sostituisce le guide Mediaset già funzionanti:
    # aggiunge soltanto la guida di 20 Mediaset sotto entrambi gli alias ID.
    mediaset20_stats = hydrate_mediaset20(
        out_root,
        output_ids,
        programme_keys,
    )

    print(
        "20 Mediaset: "
        f"fonte={mediaset20_stats['source_id']} / "
        f"{mediaset20_stats['source_programmes']} programmi sorgente -> "
        f"{mediaset20_stats['programmes_added']} programmi alias aggiunti"
    )

    # Riallinea i conteggi dopo le integrazioni mirate.
    programme_count_by_id = programme_counts_by_channel(out_root)

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

    # Anti-regressione PER CANALE:
    # se una guida presente nel vecchio EPG per un canale realmente usato
    # dalla playlist (o per uno degli ID sport/FAST protetti) sparisce del tutto,
    # NON pubblichiamo il nuovo EPG.
    protected_guide_ids = playlist_tvg_ids | FORCE_SECONDARY_IDS
    disappeared_guides = sorted(
        cid
        for cid in protected_guide_ids
        if old_programme_counts.get(cid, 0) > 0
        and programme_count_by_id.get(cid, 0) == 0
    )

    if disappeared_guides:
        raise RuntimeError(
            "Anti-regressione guide: sono sparite guide che prima esistevano per: "
            + ", ".join(disappeared_guides[:20])
            + (f" (+{len(disappeared_guides) - 20} altri)" if len(disappeared_guides) > 20 else "")
            + ". Il vecchio epg.xml viene mantenuto."
        )

    # Validazione specifica Mediaset 20:
    # non pubblichiamo un nuovo EPG se uno dei due ID resta senza programmi.
    final_programme_counts = programme_counts_by_channel(out_root)
    mediaset20_missing = [
        cid for cid in MEDIASET20_ALIAS_IDS
        if final_programme_counts.get(cid, 0) == 0
    ]
    if mediaset20_missing:
        raise RuntimeError(
            "Guida 20 Mediaset ancora assente per: "
            + ", ".join(mediaset20_missing)
            + ". Il vecchio epg.xml viene mantenuto."
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
    final_programme_counts = programme_counts_by_channel(out_root)
    print(
        "20 Mediaset guide: "
        + ", ".join(
            f"{cid}={final_programme_counts.get(cid, 0)} programmi"
            for cid in MEDIASET20_ALIAS_IDS
        )
    )

    sport_with_guide = {
        cid: final_programme_counts.get(cid, 0)
        for cid in sorted(FORCE_SECONDARY_IDS)
        if final_programme_counts.get(cid, 0) > 0
    }
    print(
        f"Guide sport/FAST protette presenti: {len(sport_with_guide)}/"
        f"{len(FORCE_SECONDARY_IDS)}"
    )
    for cid, count in sport_with_guide.items():
        print(f"  SPORT/FAST | {cid} | {count} programmi")

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
