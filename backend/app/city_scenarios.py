"""Immutable artificial experiment profiles; these are scenario inputs, never harness knobs."""

from dataclasses import asdict, dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class CityScenario:
    id: str
    title: str
    description: str
    demand_multiplier: float = 1.0
    acceptance_override: float | None = None
    standard_disruptions: bool = True
    bus_gap_route: str | None = None
    bus_gap_start: int = 0
    bus_gap_end: int = 0
    bart_delay_start: int = 0
    bart_delay_end: int = 0
    bart_delay_minutes: int = 0
    stadium_start: int = 0
    stadium_end: int = 0
    stadium_multiplier: int = 1

    def metadata(self):
        return dict(
            asdict(self),
            provenance="Fully synthetic experiment profile on observed GTFS connectivity; no actual incident, live availability, crowd count or historical ridership claim",
            timeline=profile_timeline(self),
        )


CITY_SCENARIOS = MappingProxyType(
    {
        "standard": CityScenario(
            "standard",
            "Standard commute",
            "Original fixed synthetic commute experiment, including route22 service gap and downtown BART delay.",
        ),
        "bus_driver_shortage": CityScenario(
            "bus_driver_shortage",
            "Route 38 driver shortage",
            "Half of scheduled route38 departures are unavailable from minute30 to150. Fixed standby vehicle/driver pools remain available to every harness.",
            bus_gap_route="38",
            bus_gap_start=30,
            bus_gap_end=150,
        ),
        "bart_interruption": CityScenario(
            "bart_interruption",
            "Downtown BART interruption",
            "Departures from Embarcadero, Montgomery and Powell take eight additional minutes from minute30 to120; valid GTFS connections remain unchanged.",
            bart_delay_start=30,
            bart_delay_end=120,
            bart_delay_minutes=8,
        ),
        "stadium_exit": CityScenario(
            "stadium_exit",
            "Fictional stadium exit",
            "Mission Bay-origin residential OD batches from minute90 through120 contain three times their otherwise seeded rider counts. Represents a fictional crowd egress, not an actual event.",
            stadium_start=90,
            stadium_end=121,
            stadium_multiplier=3,
        ),
        "low_compliance": CityScenario(
            "low_compliance",
            "Low voluntary guidance uptake",
            "Same seeded demand and disruptions as standard; voluntary alternative-route acceptance probability is fixed at10%.",
            acceptance_override=0.10,
        ),
        "balanced_control": CityScenario(
            "balanced_control",
            "Balanced low-demand control",
            "Half-scale synthetic demand and no driver/BART disruptions. Physical standby resources and evaluator are unchanged.",
            demand_multiplier=0.5,
            standard_disruptions=False,
        ),
    }
)


def get_city_scenario(profile="standard"):
    try:
        return CITY_SCENARIOS[profile]
    except (KeyError, TypeError):
        raise ValueError(f"Unknown city profile: {profile}") from None


def get_city_profiles():
    return [profile.metadata() for profile in CITY_SCENARIOS.values()]


def profile_timeline(profile):
    rows = []
    if profile.standard_disruptions:
        rows.extend(
            [
                dict(
                    type="driver_shortage",
                    label="Synthetic route22 service gap",
                    start_minute=30,
                    end_minute=75,
                    route="22",
                ),
                dict(
                    type="delay",
                    label="Synthetic downtown BART delay",
                    start_minute=45,
                    end_minute=75,
                    delay_minutes=3,
                ),
            ]
        )
    if profile.bus_gap_route:
        rows.append(
            dict(
                type="driver_shortage",
                label="Synthetic route38 driver shortage · alternate scheduled trips canceled",
                start_minute=profile.bus_gap_start,
                end_minute=profile.bus_gap_end,
                route=profile.bus_gap_route,
                scheduled_service_fraction=0.5,
            )
        )
    if profile.bart_delay_minutes:
        rows.append(
            dict(
                type="delay",
                label="Synthetic downtown BART interruption · +8min travel",
                start_minute=profile.bart_delay_start,
                end_minute=profile.bart_delay_end,
                delay_minutes=profile.bart_delay_minutes,
            )
        )
    if profile.stadium_multiplier > 1:
        rows.append(
            dict(
                type="surge",
                label="Fictional Mission Bay stadium exit · seeded OD counts ×3",
                start_minute=profile.stadium_start,
                end_minute=profile.stadium_end,
                demand_multiplier=profile.stadium_multiplier,
            )
        )
    if profile.acceptance_override is not None:
        rows.append(
            dict(
                type="compliance",
                label="Synthetic voluntary guidance uptake · 10%",
                start_minute=0,
                end_minute=1441,
                acceptance_rate=profile.acceptance_override,
            )
        )
    return rows


def active_profile_events(profile, minute):
    # Keep the complete original standard payload byte-for-byte compatible.
    if profile.id == "standard":
        return []
    return [
        dict(event, minute=minute, synthetic=True)
        for event in profile_timeline(profile)
        if event["start_minute"] <= minute < event["end_minute"]
    ]
