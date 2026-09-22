import gzip
import urllib.request
import copy
import xml.etree.ElementTree as ET

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"

# ID della sorgente EPGShare -> ID usato nella tua M3U
replacements = {
    "20.it": "20Mediaset.it",
    "RaiSport.it": "raisport",
    "Rete.4.it": "Rete4.it",
    "Canale.5.it": "Canale5.it",
    "Italia.1.it": "Italia1.it",
    "TV8.HD.it": "Tv8.it",
    "RaiPremium.it": "raipremium.it",
    "Italia.2.it": "Italia2.it",
    "Mediaset.Extra.it": "MediasetExtra.it",
    "LA7.HD.it": "la7",
    "Rai4.it": "rai4.it",
    "Iris.it": "iris.it",
    "Rai5.it": "rai5.it",
    "RaiMovie.it": "raimovie.it",
    "27.Twentyseven.it": "Twentyseven.it",
    "LA7.CINEMA.it": "la7d",
    "La.5.it": "la5",
    "Real.Time.it": "RealTime.it",
    "Gambero.Rosso.HD.it": "GamberoRosso.it",
    "Food.Network.it": "foodnetwork.it",
    "Cine34.it": "cine34.it",
    "RTL.102.5.HD.it": "rtl102.5tv",
    "Discovery.Channel.it": "discovery",
    "Giallo.TV.it": "Giallo.it",
    "Top.Crime.it": "TopCrime.it",
    "Super!.it": "super",
    "RaiNews24.it": "rai news 24",
    "TGCom.it": "TGCom24.it",
    "SuperTennis.HD.it": "SuperTennis.it",
    "R101tv.it": "R101TV",
    "Deejay.TV.it": "DeejayTV.it",
    "Radio.Italia.TV.HD.it": "radioitaliatv",
    "Virgin.Radio.it": "VirginRadioTV.it",
    "RMC.it": "radiomontecarlotv",
    "RaiRadio2.it": "rairadio2",
    "cielo.it": "Cielo.it",
    "RaiYoyo.it": "RaiYoYo.it",
}

req = urllib.request.Request(
    SOURCE,
    headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://epgshare01.online/",
    },
)

with urllib.request.urlopen(req, timeout=60) as response:
    data = response.read()

xml = gzip.decompress(data).decode("utf-8-sig")
root = ET.fromstring(xml)

channels = list(root.findall("channel"))
programmes = list(root.findall("programme"))

channel_by_id = {c.get("id"): c for c in channels}
programmes_by_id = {}

for p in programmes:
    programmes_by_id.setdefault(p.get("channel"), []).append(p)

# Gli ID target sono alias della stessa emittente.
# Li rigeneriamo SEMPRE dalla sorgente corretta, anche se il target
# è già presente nell'XML ma non ha programmi (era il problema principale).
target_ids = set(replacements.values())

# Rimuove dall'output i programmi preesistenti degli alias target.
# Verranno ricopiati dalla sorgente canonica, evitando doppioni.
final_programmes = [
    p for p in programmes
    if p.get("channel") not in target_ids
]

added_channels = []
warnings = []

for source_id, target_id in replacements.items():
    source_channel = channel_by_id.get(source_id)

    if source_channel is None:
        warnings.append(f"SORGENTE NON TROVATA: {source_id} -> {target_id}")
        continue

    # Se il canale alias non esiste, crealo.
    if target_id not in channel_by_id:
        alias_channel = copy.deepcopy(source_channel)
        alias_channel.set("id", target_id)
        channels.append(alias_channel)
        channel_by_id[target_id] = alias_channel
        added_channels.append(target_id)

    source_programmes = programmes_by_id.get(source_id, [])

    if not source_programmes:
        warnings.append(f"NESSUN PROGRAMMA: {source_id} -> {target_id}")
        continue

    # Copia SEMPRE la programmazione della sorgente canonica sull'alias.
    for programme in source_programmes:
        alias_programme = copy.deepcopy(programme)
        alias_programme.set("channel", target_id)
        final_programmes.append(alias_programme)

    print(
        f"OK {source_id} -> {target_id}: "
        f"{len(source_programmes)} programmi"
    )

# Ricostruisce un XMLTV ordinato correttamente:
# prima tutti i <channel>, poi tutti i <programme>.
new_root = ET.Element(root.tag, root.attrib)

for child in list(root):
    if child.tag not in ("channel", "programme"):
        new_root.append(copy.deepcopy(child))

for channel in channels:
    new_root.append(channel)

for programme in final_programmes:
    new_root.append(programme)

ET.ElementTree(new_root).write(
    "epg.xml",
    encoding="utf-8",
    xml_declaration=True,
)

print()
print(f"Canali alias aggiunti: {len(added_channels)}")
print(f"Programmi totali scritti: {len(final_programmes)}")

if warnings:
    print()
    print("AVVISI:")
    for warning in warnings:
        print("-", warning)

print("EPG Altervista completo generato")
