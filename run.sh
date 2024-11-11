# script to process collision data.
source venv/bin/activate
python src/01-download-tfl-data.py
python src/02-filter-data.py
python src/03-build-junctions-graph.py
python src/04-map-collisions-to-graph.py