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

xml = gzip.decompress(compressed).decode("utf-8-sig")

for source_id, target_id in replacements.items():
    xml = xml.replace(f'id="{source_id}"', f'id="{target_id}"')
    xml = xml.replace(f'channel="{source_id}"', f'channel="{target_id}"')

Path("epg.xml").write_text(xml, encoding="utf-8")

print("EPG Altervista generato correttamente")
