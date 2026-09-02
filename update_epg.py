import gzip
import urllib.request
import copy
import xml.etree.ElementTree as ET

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"

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
        "Referer": "https://epgshare01.online/"
    }
)

with urllib.request.urlopen(req, timeout=60) as response:
    data = response.read()

xml = gzip.decompress(data).decode("utf-8-sig")
root = ET.fromstring(xml)

channels = {c.get("id"): c for c in root.findall("channel")}
programmes = {}

for p in root.findall("programme"):
    programmes.setdefault(p.get("channel"), []).append(p)

existing = {c.get("id") for c in root.findall("channel")}

for source_id, target_id in replacements.items():
    if source_id not in channels or target_id in existing:
        continue

    channel = copy.deepcopy(channels[source_id])
    channel.set("id", target_id)
    root.append(channel)
    existing.add(target_id)

    for programme in programmes.get(source_id, []):
        new_programme = copy.deepcopy(programme)
        new_programme.set("channel", target_id)
        root.append(new_programme)

ET.ElementTree(root).write(
    "epg.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("EPG Altervista completo generato")
