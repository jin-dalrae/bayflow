# BayFlow geographic reference data

These are imported agency GTFS snapshots, not real-time observations. The overlay includes 3,238 served Muni stop records, 50 BART parent stations, 68 Muni routes (58 bus, 7 tram/Metro, 3 cable car) and 14 BART directional/service route records (including two bridge-bus records). It includes all route shape variants referenced by trips in those feeds. Platform/directional Muni stops are distinct records, not 3,238 unique stations.

Retrieved October 11, 2026. The downloaded SFMTA calendar ends August 28, 2026; the downloaded BART feed ends August 30, 2026. The publishers' current download URLs returned these snapshots. Do not use them as current service predictions. Feed checksums, retrieval timestamps, original identifiers, transformation and license links are embedded in transit-reference.json.

Sources:
- SFMTA: https://www.sfmta.com/reports/gtfs-transit-data
- SFMTA download: https://muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip
- BART: https://www.bart.gov/schedules/developers/gtfs
- BART download: https://www.bart.gov/dev/schedules/google_transit.zip
- BART terms: https://www.bart.gov/schedules/developers/developer-license-agreement
- Street tiles: OpenStreetMap contributors, https://www.openstreetmap.org/copyright

Agency data retains its provider's terms and is excluded from BayFlow's MIT software license. No agency logos or official system-map artwork are used. All geometry is independently rendered from GTFS; original route data is preserved separately from the synthetic simulation. Shape display is simplified by approximately four meters. BART platforms are grouped by parent station. Routes/stops are included if present in these snapshots; service calendars are not represented as today's timetable. Map route colors are display styling.

## SFMTA required derivative notice

Reproduced with permission granted by the City and County of San Francisco. The information has been provided by means of a nonexclusive, limited, and revocable license granted by the City and County of San Francisco.

The City and County of San Francisco does not guarantee the accuracy, adequacy, completeness or usefulness of any information. The City and County of San Francisco provides this information "as is," without warranty of any kind, express or implied, including but not limited to warranties of merchantability or fitness for a particular purpose, and assumes no responsibility for anyone's use of the information.

SFMTA and BART data is provided as available, without warranties. SFMTA, BART and their employees, officers, directors and agents are not liable for damages arising from its use. BayFlow is an independent experimental prototype, not an official transit-agency product. See the linked agency agreements for the complete applicable terms.

## Rebuild

Download the two ZIP files from the source URLs above, then run from the repository root:

    .venv/bin/python scripts/build_map_reference.py --muni /path/muni.zip --bart /path/bart.zip

The 21-node operational simulator remains a compact, synthetic corridor model. The wider geographic reference network is visible and searchable, but its remaining stops do not receive simulated demand or operational decisions. Highlighted Muni/BART vehicles follow matched GTFS shape segments where available. Caltrain geometry is a simplified connection because its full GTFS feed is not imported.
