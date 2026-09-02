import gzip
import urllib.request
from pathlib import Path

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"

replacements = {
    "Rete.4.it": "Rete4.it",
    "Canale.5.it": "Canale5.it",
    "Italia.1.it": "Italia1.it",
    "Real.Time.it": "RealTime.it",
    "LA7.HD.it": "la7",
    "TV8.HD.it": "Tv8.it",
}

urllib.request.urlretrieve(SOURCE, "source.xml.gz")

with gzip.open("source.xml.gz", "rt", encoding="utf-8-sig") as f:
    xml = f.read()

for epg_id, altervista_id in replacements.items():
    xml = xml.replace(
        f'id="{epg_id}"',
        f'id="{altervista_id}"'
    )
    xml = xml.replace(
        f'channel="{epg_id}"',
        f'channel="{altervista_id}"'
    )

Path("epg.xml").write_text(xml, encoding="utf-8")
print("EPG Altervista generato correttamente")
