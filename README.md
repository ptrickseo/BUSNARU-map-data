# BUSNARU map data / 버스나루 지도 데이터

This repository distributes only regional offline pedestrian databases derived from OpenStreetMap and the scripts needed to reproduce them. It does not contain private app source, account data, credentials or KTDB data.

© OpenStreetMap contributors. Database: [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). [Attribution and copyright](https://www.openstreetmap.org/copyright).

Source: regional non-military extracts at https://tiles.osm.kr/download/. Each ZIP includes source URL, source checksum, database checksum, counts and license notice. Coverage is incomplete and paths have not been field verified. Verify local signs, crossing rules, accessibility and conditions.

## Releases
Eight regional packages: Seoul, Incheon, Gyeonggi, Gangwon, Chungcheong, Jeolla, Gyeongsang, Jeju. Publication requires all eight regional integrity and sample path checks to pass.

Reproduce with Python 3.12, osmium and scripts under `scripts/`. See the workflow for commands.
