"""Compact real-place topology, with explicitly synthetic operating assumptions."""

NODES = [
    ("oracle", "Oracle Park", 37.7786, -122.3893, "walk"),
    ("sf_caltrain", "San Francisco · 4th & King", 37.7764, -122.3943, "Caltrain"),
    ("king_muni", "4th & King · N/Judah", 37.7761, -122.3935, "Muni Metro"),
    ("mission_rock", "Mission Rock · T/Third", 37.7725, -122.3895, "Muni Metro"),
    ("chase", "Chase Center", 37.768, -122.3877, "walk"),
    ("ucsf", "UCSF/Chase Center · T/Third", 37.7679, -122.3892, "Muni Metro"),
    ("yerba", "Yerba Buena/Moscone · T/Third", 37.7815, -122.3993, "Muni Metro"),
    ("union", "Union Square/Market · T/Third", 37.7853, -122.4075, "Muni Metro"),
    ("powell", "Powell Street · BART", 37.7845, -122.4078, "BART"),
    ("emb_muni", "Embarcadero · Muni", 37.793, -122.3965, "Muni Metro"),
    ("emb", "Embarcadero · BART", 37.7929, -122.397, "BART"),
    ("mont", "Montgomery Street · BART", 37.7894, -122.401, "BART"),
    ("civic", "Civic Center · BART", 37.7797, -122.4141, "BART"),
    ("16th", "16th Street Mission · BART", 37.765, -122.4197, "BART"),
    ("balboa", "Balboa Park · BART", 37.7219, -122.4474, "BART"),
    ("millbrae", "Millbrae · BART", 37.5998, -122.3867, "BART"),
    ("millbrae_caltrain", "Millbrae · Caltrain", 37.6001, -122.3861, "Caltrain"),
    ("22nd", "22nd Street · Caltrain", 37.7577, -122.3925, "Caltrain"),
    ("bayshore", "Bayshore · Caltrain", 37.7095, -122.4017, "Caltrain"),
    ("townsend", "16th/3rd · 22 bus", 37.7666, -122.3892, "Muni Bus"),
    ("mission_bus", "16th/Mission · bus", 37.7651, -122.4195, "Muni Bus"),
]


def get_network():
    nodes = [
        dict(id=i, name=n, lat=lat, lon=lon, operator=o) for i, n, lat, lon, o in NODES
    ]
    edges = []

    def link(a, b, operator, service, travel, headway, capacity):
        for source, target in [(a, b), (b, a)]:
            edges.append(
                dict(
                    id=f"{source}-{target}",
                    source=source,
                    target=target,
                    operator=operator,
                    service=service,
                    travel_minutes=travel,
                    headway_minutes=headway,
                    capacity=capacity,
                    provenance="synthetic operations; real connection",
                )
            )

    link("oracle", "king_muni", "walk", "walk", 5, 5, 10000)
    link("oracle", "sf_caltrain", "walk", "walk", 5, 5, 10000)
    link("chase", "ucsf", "walk", "walk", 5, 5, 10000)
    link("ucsf", "mission_rock", "Muni Metro", "T", 5, 10, 120)
    link("mission_rock", "yerba", "Muni Metro", "T", 10, 10, 120)
    link("yerba", "union", "Muni Metro", "T", 5, 10, 120)
    link("union", "powell", "walk", "walk", 5, 5, 10000)
    link("king_muni", "emb_muni", "Muni Metro", "N", 15, 10, 120)
    link("emb_muni", "emb", "walk", "walk", 5, 5, 10000)
    link("emb", "mont", "BART", "BART", 5, 15, 240)
    link("mont", "powell", "BART", "BART", 5, 15, 240)
    link("powell", "civic", "BART", "BART", 5, 15, 240)
    link("civic", "16th", "BART", "BART", 5, 15, 240)
    link("16th", "balboa", "BART", "BART", 10, 15, 240)
    link("balboa", "millbrae", "BART", "BART", 25, 15, 240)
    link("millbrae", "millbrae_caltrain", "walk", "walk", 5, 5, 10000)
    link("sf_caltrain", "22nd", "Caltrain", "Caltrain", 5, 30, 180)
    link("22nd", "bayshore", "Caltrain", "Caltrain", 10, 30, 180)
    link("bayshore", "millbrae_caltrain", "Caltrain", "Caltrain", 20, 30, 180)
    link("sf_caltrain", "townsend", "walk", "walk", 15, 5, 10000)
    link("ucsf", "townsend", "walk", "walk", 5, 5, 10000)
    link("townsend", "mission_bus", "Muni Bus", "22", 15, 15, 55)
    link("mission_bus", "16th", "walk", "walk", 5, 5, 10000)
    return dict(
        nodes=nodes,
        edges=edges,
        provenance={
            "places": "Approximate public station coordinates; selected actual transfer connections",
            "operations": "Fully synthetic 5-minute interval capacities, headways, travel times and demand. Segment capacity abstraction, not a full vehicle block schedule.",
            "generated_events": True,
        },
    )
