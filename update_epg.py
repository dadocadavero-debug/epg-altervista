import gzip
import urllib.request
import copy
import xml.etree.ElementTree as ET

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"

# EPGShare ID -> tvg-id usato dalla playlist Altervista
MAPPING = {
    "Rete.4.it": "Rete4.it",
    "Canale.5.it": "Canale5.it",
    "Italia.1.it": "Italia1.it",
    "TV8.HD.it": "Tv8.it",
    "LA7.HD.it": "la7",
    "Rai4.it": "rai4.it",
    "Rai5.it": "rai5.it",
    "RaiMovie.it": "raimovie.it",
    "RaiPremium.it": "raipremium.it",
    "Real.Time.it": "RealTime.it",
    "Food.Network.it": "foodnetwork.it",
    "Giallo.TV.it": "Giallo.it",
    "Italia.2.it": "Italia2.it",
    "Mediaset.Extra.it": "MediasetExtra.it",
    "27.Twentyseven.it": "Twentyseven.it",
    "La.5.it": "la5",
    "Top.Crime.it": "TopCrime.it",
    "Cine34.it": "cine34.it",
    "RaiYoyo.it": "RaiYoYo.it",
    "RaiNews24.it": "rai news 24",
    "SuperTennis.HD.it": "SuperTennis.it",
    "RaiRadio2.it": "rairadio2",
    "cielo.it": "Cielo.it",
    "20.it": "20Mediaset.it",
    "RaiSport.it": "raisport",
    "Gambero.Rosso.HD.it": "GamberoRosso.it",
    "Discovery.Channel.it": "discovery",
    "RTL.102.5.HD.it": "rtl102.5tv",
    "TGCom.it": "TGCom24.it",
    "R101tv.it": "R101TV",
    "Deejay.TV.it": "DeejayTV.it",
    "Radio.Italia.TV.HD.it": "radioitaliatv",
    "Virgin.Radio.it": "VirginRadioTV.it",
    "RMC.it": "radiomontecarlotv",
}

req = urllib.request.Request(
    SOURCE,
    headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://epgshare01.online/"
    }
)

with urllib.request.urlopen(req, timeout=60) as response:
    compressed = response.read()

root = ET.fromstring(gzip.decompress(compressed))

channels = root.findall("channel")
programmes = root.findall("programme")
other = [x for x in list(root) if x.tag not in ("channel", "programme")]

channel_by_id = {c.get("id"): c for c in channels}
programmes_by_id = {}
for p in programmes:
    programmes_by_id.setdefault(p.get("channel"), []).append(p)

# Ricostruiamo l'XML in ordine corretto:
# prima TUTTI i channel, poi TUTTI i programme.
new_root = ET.Element(root.tag, root.attrib)

for item in other:
    new_root.append(copy.deepcopy(item))

existing_ids = set()

# Canali originali
for ch in channels:
    new_root.append(copy.deepcopy(ch))
    existing_ids.add(ch.get("id"))

# Alias Altervista PRIMA dei programme
for source_id, target_id in MAPPING.items():
    src = channel_by_id.get(source_id)
    if src is None or target_id in existing_ids:
        continue
    alias = copy.deepcopy(src)
    alias.set("id", target_id)
    new_root.append(alias)
    existing_ids.add(target_id)

# Programmi originali
for p in programmes:
    new_root.append(copy.deepcopy(p))

# Programmi duplicati con ID Altervista
for source_id, target_id in MAPPING.items():
    if source_id not in channel_by_id:
        continue
    for p in programmes_by_id.get(source_id, []):
        alias_p = copy.deepcopy(p)
        alias_p.set("channel", target_id)
        new_root.append(alias_p)

ET.ElementTree(new_root).write(
    "epg.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("EPG Altervista generato con channel alias prima dei programme")
