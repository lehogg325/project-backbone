PYTHON     := python3
SCRIPTS    := scripts
PUBLIC     := public

# ── Output targets ───────────────────────────────────────────────────────────

CABLES        := $(PUBLIC)/cables.geojson $(PUBLIC)/landing-points.geojson
PEERINGDB     := $(PUBLIC)/data-centers.geojson $(PUBLIC)/ixps.geojson
CDN           := $(PUBLIC)/cdn-edge-locations.geojson
DNS           := $(PUBLIC)/dns-root-instances.geojson $(PUBLIC)/dns-resolvers.geojson
GEO           := $(PUBLIC)/borders.geojson $(PUBLIC)/lakes.geojson $(PUBLIC)/rivers.geojson
OCEAN         := $(PUBLIC)/ocean.geojson $(PUBLIC)/marine-labels.geojson
SATELLITES    := $(PUBLIC)/starlink-tle.json $(PUBLIC)/oneweb-tle.json \
                 $(PUBLIC)/kuiper-tle.json $(PUBLIC)/geo-commsats-tle.json \
                 $(PUBLIC)/iss-tle.json $(PUBLIC)/ground-stations.geojson
FIBER         := $(PUBLIC)/fiber-routes-verified.geojson $(PUBLIC)/fiber-routes-estimated.geojson
BACKBONE      := $(PUBLIC)/backbone.geojson
CELL_TOWERS   := $(PUBLIC)/cell_towers.geojson

ALL_TARGETS := $(CABLES) $(PEERINGDB) $(CDN) $(DNS) $(GEO) $(OCEAN) \
               $(SATELLITES) $(FIBER) $(BACKBONE)

# ── Phony targets ─────────────────────────────────────────────────────────────

.PHONY: all satellites geo cell-towers clean help

## all: fetch all data (excludes cell-towers, which requires a manual CSV)
all: $(ALL_TARGETS)

## satellites: update TLE files and ground stations
satellites: $(SATELLITES)

## geo: fetch geographic layers (borders, lakes, rivers, ocean)
geo: $(GEO) $(OCEAN)

## cell-towers: process OpenCelliD CSV  (usage: make cell-towers CSV=path/to/cell_towers.csv)
cell-towers:
ifndef CSV
	$(error CSV is not set. Usage: make cell-towers CSV=path/to/cell_towers.csv)
endif
	$(PYTHON) $(SCRIPTS)/process_celltowers.py $(CSV)

## clean: remove the scripts cache directory
clean:
	rm -rf $(SCRIPTS)/.cache

## help: show this help
help:
	@grep -E '^## ' Makefile | sed 's/^## /  /'

# ── Individual script rules ───────────────────────────────────────────────────

$(CABLES): $(SCRIPTS)/fetch_cables.py
	$(PYTHON) $<

$(PEERINGDB): $(SCRIPTS)/fetch_peeringdb.py
	$(PYTHON) $<

$(CDN): $(SCRIPTS)/fetch_cdn_locations.py
	$(PYTHON) $<

$(DNS): $(SCRIPTS)/fetch_dns_infrastructure.py
	$(PYTHON) $<

$(GEO): $(SCRIPTS)/fetch_geo.py
	$(PYTHON) $<

$(OCEAN): $(SCRIPTS)/fetch_ocean.py
	$(PYTHON) $<

$(SATELLITES): $(SCRIPTS)/fetch_satellite_data.py
	$(PYTHON) $<

# fiber depends on peeringdb (ixps + data-centers) and cables (landing-points)
$(FIBER): $(SCRIPTS)/fetch_terrestrial_fiber.py $(PEERINGDB) $(CABLES)
	$(PYTHON) $<

# backbone depends on peeringdb (ixps + data-centers)
$(BACKBONE): $(SCRIPTS)/generate_backbone.py $(PEERINGDB)
	$(PYTHON) $<
