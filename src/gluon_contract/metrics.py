# SPDX-License-Identifier: MIT

"""Prometheus text-format parsing for the metrics checks (RUST-1.7)."""

from dataclasses import dataclass

from prometheus_client.parser import text_string_to_metric_families


@dataclass(frozen=True, slots=True)
class MetricShape:
    """What the dashboards depend on: type, label names, histogram buckets."""

    type: str
    labels: frozenset[str]
    buckets: tuple[float, ...]


def _name(family_name: str, family_type: str) -> str:
    """The exposed name: the parser drops `_total` from counters; put it back."""
    return family_name + "_total" if family_type == "counter" else family_name


def metric_shapes(text: str) -> dict[str, MetricShape]:
    """Every family in a scrape, by its exposed name."""
    shapes: dict[str, MetricShape] = {}
    for family in text_string_to_metric_families(text):
        labels = frozenset(
            name for sample in family.samples for name in sample.labels if name != "le"
        )
        buckets = sorted(
            {float(sample.labels["le"]) for sample in family.samples if "le" in sample.labels}
        )
        shapes[_name(family.name, family.type)] = MetricShape(family.type, labels, tuple(buckets))
    return shapes


def samples(text: str, name: str) -> list[tuple[dict[str, str], float]]:
    """The samples named exactly `name` (e.g. `users_logins_total`), labels and value."""
    return [
        (dict(sample.labels), sample.value)
        for family in text_string_to_metric_families(text)
        for sample in family.samples
        if sample.name == name
    ]
