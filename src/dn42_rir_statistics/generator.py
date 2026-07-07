from __future__ import annotations

import hashlib
import ipaddress
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .registry import RegistryObject, iter_registry_objects, load_registry_names


DEFAULT_UNKNOWN_COUNTRY = "zz"
DEFAULT_UNKNOWN_DATE = "00000000"
UTC_OFFSET = "+0000"
RESOURCE_TYPES = ("asn", "ipv4", "ipv6")

DATE_RE = re.compile(r"(?P<year>\d{4})[-/]?(?P<month>\d{2})[-/]?(?P<day>\d{2})")
ASN_RE = re.compile(r"^as(?P<number>\d+)$", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class StatisticRecord:
    registry: str
    country: str
    resource_type: str
    start: str
    value: str
    allocation_date: str
    status: str

    def line(self) -> str:
        return "|".join(
            (
                self.registry,
                self.country,
                self.resource_type,
                self.start,
                self.value,
                self.allocation_date,
                self.status,
            )
        )


@dataclass
class GenerationResult:
    output_root: Path
    generation_date: str
    registries: list[str]
    record_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    checked_files: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def format_date(value: date | str | None = None) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    normalized = value.replace("-", "")
    if len(normalized) != 8 or not normalized.isdigit():
        raise ValueError(f"invalid date: {value!r}")
    return normalized


def generate_statistics(
    registry_root: Path,
    output_root: Path,
    generation_date: date | str | None = None,
) -> GenerationResult:
    generation_date_text = format_date(generation_date)
    output_root = output_root.resolve()
    stats_root = output_root / "stats"
    stats_root.mkdir(parents=True, exist_ok=True)

    declared_registries = load_registry_names(registry_root)
    records, warnings = collect_records(registry_root, declared_registries)

    registry_names = sorted(declared_registries | set(records))
    record_counts: dict[str, int] = {}

    for registry in registry_names:
        registry_records = sorted(records.get(registry, []))
        registry_dir = stats_root / registry
        registry_dir.mkdir(parents=True, exist_ok=True)
        content = render_statistics_file(registry, registry_records, generation_date_text)

        dated_name = f"delegated-{registry}-{generation_date_text}"
        latest_name = f"delegated-{registry}-latest"
        dated_path = registry_dir / dated_name
        latest_path = registry_dir / latest_name

        dated_path.write_text(content, encoding="ascii")
        shutil.copyfile(dated_path, latest_path)
        write_md5_file(dated_path)
        write_md5_file(latest_path)
        record_counts[registry] = len(registry_records)

    return GenerationResult(
        output_root=output_root,
        generation_date=generation_date_text,
        registries=registry_names,
        record_counts=record_counts,
        warnings=warnings,
    )


def collect_records(
    registry_root: Path,
    declared_registries: set[str] | None = None,
) -> tuple[dict[str, list[StatisticRecord]], list[str]]:
    declared_registries = declared_registries or set()
    records: dict[str, list[StatisticRecord]] = defaultdict(list)
    warnings: list[str] = []

    for registry_object in iter_registry_objects(registry_root):
        source = registry_object.first("source").strip().lower()
        if not source:
            warnings.append(f"{registry_object.path}: missing source")
            continue
        if declared_registries and source not in declared_registries:
            warnings.append(f"{registry_object.path}: unknown source {source!r}")
            continue

        parsed_records = records_from_object(registry_object, source, warnings)
        records[source].extend(parsed_records)

    return dict(records), warnings


def records_from_object(
    registry_object: RegistryObject,
    registry: str,
    warnings: list[str],
) -> list[StatisticRecord]:
    country = normalize_country(registry_object.first("country"))
    allocation_date = normalize_date(registry_object)
    status = normalize_status(registry_object)

    if registry_object.object_type == "aut-num":
        value = registry_object.first("aut-num")
        match = ASN_RE.match(value.strip())
        if not match:
            warnings.append(f"{registry_object.path}: invalid aut-num {value!r}")
            return []
        return [
            StatisticRecord(
                registry=registry,
                country=country,
                resource_type="asn",
                start=match.group("number"),
                value="1",
                allocation_date=allocation_date,
                status="assigned",
            )
        ]

    if registry_object.object_type == "inetnum":
        return ipv4_records_from_object(
            registry_object,
            registry,
            country,
            allocation_date,
            status,
            warnings,
        )

    if registry_object.object_type == "inet6num":
        return ipv6_records_from_object(
            registry_object,
            registry,
            country,
            allocation_date,
            status,
            warnings,
        )

    return []


def ipv4_records_from_object(
    registry_object: RegistryObject,
    registry: str,
    country: str,
    allocation_date: str,
    status: str,
    warnings: list[str],
) -> list[StatisticRecord]:
    inetnum = registry_object.first("inetnum")
    if inetnum:
        try:
            start, count = ipv4_range_start_and_count(inetnum)
            return [
                StatisticRecord(
                    registry=registry,
                    country=country,
                    resource_type="ipv4",
                    start=start,
                    value=str(count),
                    allocation_date=allocation_date,
                    status=status,
                )
            ]
        except ValueError as error:
            warnings.append(f"{registry_object.path}: {error}")

    records: list[StatisticRecord] = []
    for cidr in registry_object.all("cidr"):
        try:
            network = ipaddress.ip_network(cidr.strip(), strict=False)
        except ValueError as error:
            warnings.append(f"{registry_object.path}: invalid ipv4 cidr {cidr!r}: {error}")
            continue
        if network.version != 4:
            warnings.append(f"{registry_object.path}: cidr is not ipv4: {cidr!r}")
            continue
        records.append(
            StatisticRecord(
                registry=registry,
                country=country,
                resource_type="ipv4",
                start=str(network.network_address),
                value=str(network.num_addresses),
                allocation_date=allocation_date,
                status=status,
            )
        )
    return records


def ipv6_records_from_object(
    registry_object: RegistryObject,
    registry: str,
    country: str,
    allocation_date: str,
    status: str,
    warnings: list[str],
) -> list[StatisticRecord]:
    records: list[StatisticRecord] = []

    for cidr in registry_object.all("cidr"):
        try:
            network = ipaddress.ip_network(cidr.strip(), strict=False)
        except ValueError as error:
            warnings.append(f"{registry_object.path}: invalid ipv6 cidr {cidr!r}: {error}")
            continue
        if network.version != 6:
            warnings.append(f"{registry_object.path}: cidr is not ipv6: {cidr!r}")
            continue
        records.append(
            StatisticRecord(
                registry=registry,
                country=country,
                resource_type="ipv6",
                start=str(network.network_address),
                value=str(network.prefixlen),
                allocation_date=allocation_date,
                status=status,
            )
        )

    if records:
        return records

    inet6num = registry_object.first("inet6num")
    if not inet6num:
        warnings.append(f"{registry_object.path}: missing inet6num")
        return []

    try:
        network = ipv6_range_to_single_network(inet6num)
    except ValueError as error:
        warnings.append(f"{registry_object.path}: {error}")
        return []

    return [
        StatisticRecord(
            registry=registry,
            country=country,
            resource_type="ipv6",
            start=str(network.network_address),
            value=str(network.prefixlen),
            allocation_date=allocation_date,
            status=status,
        )
    ]


def ipv4_range_start_and_count(value: str) -> tuple[str, int]:
    if "-" in value:
        start_text, end_text = [part.strip() for part in value.split("-", 1)]
        start = ipaddress.ip_address(start_text)
        end = ipaddress.ip_address(end_text)
        if start.version != 4 or end.version != 4:
            raise ValueError(f"inetnum is not ipv4: {value!r}")
        if int(end) < int(start):
            raise ValueError(f"inetnum end is before start: {value!r}")
        return str(start), int(end) - int(start) + 1

    network = ipaddress.ip_network(value.strip(), strict=False)
    if network.version != 4:
        raise ValueError(f"inetnum is not ipv4: {value!r}")
    return str(network.network_address), network.num_addresses


def ipv6_range_to_single_network(value: str) -> ipaddress.IPv6Network:
    if "-" not in value:
        network = ipaddress.ip_network(value.strip(), strict=False)
        if network.version != 6:
            raise ValueError(f"inet6num is not ipv6: {value!r}")
        return network

    start_text, end_text = [part.strip() for part in value.split("-", 1)]
    start = ipaddress.ip_address(start_text)
    end = ipaddress.ip_address(end_text)
    if start.version != 6 or end.version != 6:
        raise ValueError(f"inet6num is not ipv6: {value!r}")
    networks = list(ipaddress.summarize_address_range(start, end))
    if len(networks) != 1:
        raise ValueError(f"inet6num cannot be represented as one prefix: {value!r}")
    return networks[0]


def normalize_country(value: str) -> str:
    value = value.strip().lower()
    if len(value) == 2 and value.isalpha():
        return value
    return DEFAULT_UNKNOWN_COUNTRY


def normalize_date(registry_object: RegistryObject) -> str:
    for key in ("created", "last-modified", "changed"):
        for value in registry_object.all(key):
            match = DATE_RE.search(value)
            if match:
                return (
                    f"{match.group('year')}"
                    f"{match.group('month')}"
                    f"{match.group('day')}"
                )
    return DEFAULT_UNKNOWN_DATE


def normalize_status(registry_object: RegistryObject) -> str:
    value = registry_object.first("status").strip().lower()
    if not value:
        return "assigned"
    if "available" in value:
        return "available"
    if "reserved" in value:
        return "reserved"
    if "allocated" in value:
        return "allocated"
    if "assigned" in value:
        return "assigned"
    return value.split()[0]


def render_statistics_file(
    registry: str,
    records: list[StatisticRecord],
    generation_date: str,
) -> str:
    counter = Counter(record.resource_type for record in records)
    lines = [
        "|".join(
            (
                "2",
                registry,
                generation_date,
                str(len(records)),
                generation_date,
                generation_date,
                UTC_OFFSET,
            )
        )
    ]

    for resource_type in RESOURCE_TYPES:
        count = counter.get(resource_type, 0)
        if count:
            lines.append(f"{registry}|*|{resource_type}|*|{count}|summary")

    lines.extend(record.line() for record in records)
    content = "\n".join(lines) + "\n"
    if content != content.lower():
        raise ValueError(f"generated content for {registry} is not lowercase")
    return content


def write_md5_file(path: Path) -> None:
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    checksum_path = path.with_name(f"{path.name}.md5")
    checksum_path.write_text(f"md5 ({path.name}) = {digest}\n", encoding="ascii")


def validate_output(output_root: Path) -> ValidationResult:
    result = ValidationResult()
    stats_root = output_root / "stats"
    if not stats_root.is_dir():
        result.errors.append(f"{stats_root}: missing stats directory")
        return result

    for path in sorted(stats_root.glob("*/delegated-*")):
        if path.suffix == ".md5" or path.name.endswith(".md5"):
            continue
        if not path.is_file():
            continue
        result.checked_files += 1
        validate_statistics_file(path, result)

    if result.checked_files == 0:
        result.errors.append(f"{stats_root}: no delegated files found")
    return result


def validate_statistics_file(path: Path, result: ValidationResult) -> None:
    content = path.read_text(encoding="ascii")
    if content != content.lower():
        result.errors.append(f"{path}: content is not lowercase")
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        result.errors.append(f"{path}: empty file")
        return

    version = lines[0].split("|")
    if len(version) != 7 or version[0] != "2":
        result.errors.append(f"{path}: invalid version line")
        return

    registry = version[1]
    if path.parent.name != registry:
        result.errors.append(f"{path}: registry does not match directory")
    if not path.name.startswith(f"delegated-{registry}-"):
        result.errors.append(f"{path}: file name does not match registry")

    summary_counts: dict[str, int] = {}
    records: list[list[str]] = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) == 6 and parts[1] == "*" and parts[3] == "*" and parts[5] == "summary":
            summary_counts[parts[2]] = int(parts[4])
            continue
        if len(parts) < 7:
            result.errors.append(f"{path}: invalid record line {line!r}")
            continue
        records.append(parts)

    expected_count = int(version[3])
    if len(records) != expected_count:
        result.errors.append(
            f"{path}: version record count {expected_count} != {len(records)}"
        )

    actual_counts = Counter(record[2] for record in records)
    for resource_type, count in actual_counts.items():
        if summary_counts.get(resource_type) != count:
            result.errors.append(
                f"{path}: summary count for {resource_type} is not {count}"
            )
    for resource_type in summary_counts:
        if resource_type not in actual_counts:
            result.errors.append(f"{path}: summary for absent type {resource_type}")

    for record in records:
        if record[0] != registry:
            result.errors.append(f"{path}: record registry mismatch {record!r}")
        if record[2] not in RESOURCE_TYPES:
            result.errors.append(f"{path}: invalid resource type {record[2]!r}")
