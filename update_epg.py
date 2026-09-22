import gzip
import urllib.request
import copy
import xml.etree.ElementTree as ET

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"

# Sorgente EPGShare -> alias compatibile con la playlist.
# Manteniamo anche gli alias storici già usati nella tua M3U,
# così gli aggiornamenti futuri non richiedono modifiche manuali.
ALIASES = {
    "20.it": ["20Mediaset.it"],
    "RaiSport.it": ["raisport"],
    "Rete.4.it": ["Rete4.it"],
    "Canale.5.it": ["Canale5.it"],
    "Italia.1.it": ["Italia1.it"],
    "TV8.HD.it": ["Tv8.it"],
    "RaiPremium.it": ["raipremium.it"],
    "Italia.2.it": ["Italia2.it"],
    "Mediaset.Extra.it": ["MediasetExtra.it"],
    "LA7.HD.it": ["la7"],
    "Rai4.it": ["rai4.it"],
    "Iris.it": ["iris.it"],
    "Rai5.it": ["rai5.it"],
    "RaiMovie.it": ["raimovie.it"],
    "27.Twentyseven.it": ["Twentyseven.it"],
    "LA7.CINEMA.it": ["la7d"],
    "La.5.it": ["la5"],
    "Real.Time.it": ["RealTime.it"],
    "Gambero.Rosso.HD.it": ["GamberoRosso.it"],
    "Food.Network.it": ["foodnetwork.it"],
    "Cine34.it": ["cine34.it"],
    "RTL.102.5.HD.it": ["rtl102.5tv"],
    "Discovery.Channel.it": ["discovery"],
    "Giallo.TV.it": ["Giallo.it"],
    "Top.Crime.it": ["TopCrime.it"],
    "Super!.it": ["super"],
    "RaiNews24.it": ["rai news 24"],
    "TGCom.it": ["TGCom24.it"],
    "SuperTennis.HD.it": ["SuperTennis.it"],
    "R101tv.it": ["R101TV"],
    "Deejay.TV.it": ["DeejayTV.it"],
    "Radio.Italia.TV.HD.it": ["radioitaliatv"],
    "Virgin.Radio.it": ["VirginRadioTV.it"],
    "RMC.it": ["radiomontecarlotv"],
    "RaiRadio2.it": ["rairadio2"],
    "cielo.it": ["Cielo.it"],
    "RaiYoyo.it": ["RaiYoYo.it"],

    # Nuovi alias
    "Motor.Trend.it": ["turbo"],

    # Alias semplici e stabili per i feed GF
    "GF.VIP.-.Regia.1.it": ["GFVIPRegia1"],
    "GF.VIP.-.Regia.2.it": ["GFVIPRegia2"],
    "GF.VIP.-.Un’ora.fa.it": ["GFVIPUnOraFa"],
}


CHECK_IDS = [
    "Rai4.it", "Rai5.it", "RaiMovie.it", "RaiPremium.it",
    "RaiRadio2.it", "TV8.HD.it", "20.it", "27.Twentyseven.it",
    "Cine34.it", "Real.Time.it", "Food.Network.it",
    "Discovery.Channel.it", "Giallo.TV.it", "K2.it", "Frisbee.it",
    "DMAX.it", "HGTV.it", "Motor.Trend.it", "QVC.it", "Fashion.TV.it",
    "GF.VIP.-.Regia.1.it", "GF.VIP.-.Regia.2.it",
    "GF.VIP.-.Un’ora.fa.it",
]

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

all_target_ids = {target for targets in ALIASES.values() for target in targets}

# Rimuove i programmi vecchi degli alias: verranno rigenerati
# dalla sorgente canonica ad ogni esecuzione.
final_programmes = [
    p for p in programmes
    if p.get("channel") not in all_target_ids
]

warnings = []
stats = []

for source_id, target_ids in ALIASES.items():
    source_channel = channel_by_id.get(source_id)
    source_programmes = programmes_by_id.get(source_id, [])

    if source_channel is None:
        warnings.append(f"SORGENTE NON TROVATA: {source_id}")
        continue

    if not source_programmes:
        warnings.append(f"NESSUN PROGRAMMA: {source_id}")
        continue

    for target_id in target_ids:
        if target_id not in channel_by_id:
            alias_channel = copy.deepcopy(source_channel)
            alias_channel.set("id", target_id)
            channels.append(alias_channel)
            channel_by_id[target_id] = alias_channel

        for programme in source_programmes:
            alias_programme = copy.deepcopy(programme)
            alias_programme.set("channel", target_id)
            final_programmes.append(alias_programme)

        stats.append((source_id, target_id, len(source_programmes)))
        print(f"OK {source_id} -> {target_id}: {len(source_programmes)} programmi")

# Ricostruzione XMLTV ordinata: prima channel, poi programme.
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

# Report utile per controllare automaticamente cosa manca.
with open("epg_audit.txt", "w", encoding="utf-8") as f:
    f.write("EPG ALTERVISTA - REPORT AUTOMATICO\n\n")
    for source_id, target_id, count in stats:
        f.write(f"OK {source_id} -> {target_id}: {count} programmi\n")
    if warnings:
        f.write("\nAVVISI\n")
        for warning in warnings:
            f.write(warning + "\n")

print()
print(f"Programmi totali scritti: {len(final_programmes)}")
if warnings:
    print("AVVISI:")
    for warning in warnings:
        print("-", warning)
print("EPG Altervista completo generato")
