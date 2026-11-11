"""Safe parsing and normalization of Artisan .alog roast profiles."""

from __future__ import annotations

import ast
import math
import os
import re
from typing import Any

ROR_WINDOW_SECONDS = 30.0
EVENT_SPECS = (
    ("charge", "Charge", "CHG", 0, "CHARGE"),
    ("turningPoint", "Turning Point", "TP", None, "TP"),
    ("dryEnd", "Dry End", "DE", 1, "DRY"),
    ("firstCrack", "First Crack Start", "FC", 2, "FCs"),
    ("drop", "Drop", "DROP", 6, "DROP"),
)


class RoastParseError(ValueError):
    """An expected, user-safe parse or validation failure."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _to_celsius(value: float | None, source_unit: str) -> float | None:
    if value is None:
        return None
    return (value - 32.0) * 5.0 / 9.0 if source_unit == "F" else value


def _display_name(filename: str) -> str:
    stem = os.path.basename(filename)
    if stem.lower().endswith(".alog"):
        stem = stem[:-5]
    return re.sub(r"\s+", " ", stem.replace("_", " ")).strip() or "Untitled profile"


def _bean_name(filename: str) -> str:
    """Group solely by the filename, ignoring Artisan's editable bean metadata."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"^\d{2,4}-\d{2}-\d{2}[_\s]+", "", stem)
    stem = re.sub(r"[_\s-]*batch[_\s-]*#?\d+(?:[_\s-]*glitch)?$", "", stem, flags=re.I)
    return " ".join(stem.replace("_", " ").split()) or "Unknown bean"


def _list(data: dict[str, Any], key: str, *, required: bool = False) -> list[Any]:
    value = data.get(key)
    if isinstance(value, (list, tuple)):
        return list(value)
    if required:
        raise RoastParseError(f"Missing or invalid {key} array.")
    return []


def _event_from_index(
    index_value: Any,
    raw_times: list[float | None],
    values: list[float | None],
) -> tuple[float | None, float | None]:
    if isinstance(index_value, bool) or not isinstance(index_value, int):
        return None, None
    if index_value < 0 or index_value >= len(raw_times):
        return None, None
    return raw_times[index_value], values[index_value] if index_value < len(values) else None


def _clean_main_series(
    times: list[Any], et_values: list[Any], bt_values: list[Any], source_unit: str
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    length = min(len(times), len(et_values), len(bt_values))
    if length == 0:
        raise RoastParseError("The main temperature arrays are empty.")
    clean_times = [_number(value) for value in times[:length]]
    clean_et = [_to_celsius(_number(value), source_unit) for value in et_values[:length]]
    clean_bt = [_to_celsius(_number(value), source_unit) for value in bt_values[:length]]
    if not any(t is not None and bt is not None for t, bt in zip(clean_times, clean_bt)):
        raise RoastParseError("The profile has no usable bean-temperature samples.")
    if not any(t is not None and et is not None for t, et in zip(clean_times, clean_et)):
        raise RoastParseError("The profile has no usable exhaust-temperature samples.")
    return clean_times, clean_et, clean_bt


def _build_series(
    times: list[float | None],
    values: list[float | None],
    charge_raw: float,
    drop_elapsed: float | None,
) -> list[list[float | None]]:
    result: list[list[float | None]] = []
    for raw_time, value in zip(times, values):
        if raw_time is None:
            continue
        elapsed = raw_time - charge_raw
        if elapsed < -1e-6:
            continue
        if drop_elapsed is not None and elapsed > drop_elapsed + 1e-6:
            continue
        result.append([round(max(0.0, elapsed), 4), None if value is None else round(value, 4)])
    return result


def _calculate_ror(bt_series: list[list[float | None]]) -> list[list[float | None]]:
    """Return a centered 30-second least-squares BT slope in degrees/minute."""
    half_window = ROR_WINDOW_SECONDS / 2.0
    result: list[list[float | None]] = []
    left = 0
    right = 0
    count = len(bt_series)
    for index, (center_time, _center_value) in enumerate(bt_series):
        assert center_time is not None
        while left < count and bt_series[left][0] is not None and bt_series[left][0] < center_time - half_window:
            left += 1
        if right < index:
            right = index
        while right < count and bt_series[right][0] is not None and bt_series[right][0] <= center_time + half_window:
            right += 1
        points = [
            (float(t), float(v))
            for t, v in bt_series[left:right]
            if t is not None and v is not None
        ]
        slope: float | None = None
        if len(points) >= 3:
            mean_t = sum(t for t, _ in points) / len(points)
            mean_v = sum(v for _, v in points) / len(points)
            denominator = sum((t - mean_t) ** 2 for t, _ in points)
            if denominator > 0:
                slope = 60.0 * sum((t - mean_t) * (v - mean_v) for t, v in points) / denominator
        result.append([round(center_time, 4), None if slope is None else round(slope, 4)])
    return result


def _extra_series(
    data: dict[str, Any], charge_raw: float, drop_elapsed: float | None
) -> tuple[list[list[float | None]], list[list[float | None]], list[str]]:
    warnings: list[str] = []
    devices = _list(data, "devices")
    extra_devices = _list(data, "extradevices")
    extra_times = _list(data, "extratimex")
    extra_one = _list(data, "extratemp1")
    extra_two = _list(data, "extratemp2")

    device_index = next(
        (i - 1 for i, name in enumerate(devices[1:], start=1) if "heater/fan" in str(name).lower()),
        None,
    )
    if device_index is None:
        device_index = next(
            (i for i, name in enumerate(extra_devices) if "heater/fan" in str(name).lower()),
            None,
        )
    if device_index is None and extra_times and extra_one and extra_two:
        device_index = 0

    if device_index is None or not all(
        device_index < len(group) for group in (extra_times, extra_one, extra_two)
    ):
        warnings.append("Heater and air channels were not found.")
        return [], [], warnings

    times_raw = extra_times[device_index]
    heat_raw = extra_one[device_index]
    air_raw = extra_two[device_index]
    if not all(isinstance(value, (list, tuple)) for value in (times_raw, heat_raw, air_raw)):
        warnings.append("Heater and air channels are invalid.")
        return [], [], warnings

    length = min(len(times_raw), len(heat_raw), len(air_raw))
    times = [_number(value) for value in list(times_raw)[:length]]
    heat = [_number(value) for value in list(heat_raw)[:length]]
    air = [_number(value) for value in list(air_raw)[:length]]
    heat_series = _build_series(times, heat, charge_raw, drop_elapsed)
    air_series = _build_series(times, air, charge_raw, drop_elapsed)
    if not any(value is not None for _, value in heat_series):
        warnings.append("Heater channel has no usable samples.")
        heat_series = []
    if not any(value is not None for _, value in air_series):
        warnings.append("Air channel has no usable samples.")
        air_series = []
    return heat_series, air_series, warnings


def _phase(seconds: float | None, total: float | None) -> dict[str, float | None]:
    if seconds is None or seconds < 0:
        return {"seconds": None, "percent": None}
    percent = None if total is None or total <= 0 else round(seconds / total * 100.0, 1)
    return {"seconds": round(seconds, 4), "percent": percent}


def parse_alog(text: str, filename: str, profile_id: str = "") -> dict[str, Any]:
    """Parse one .alog string and return the normalized browser payload."""
    if not filename.lower().endswith(".alog"):
        raise RoastParseError("Only .alog files are supported.")
    try:
        data = ast.literal_eval(text)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        raise RoastParseError("The file is not a valid Artisan .alog profile.") from exc
    if not isinstance(data, dict):
        raise RoastParseError("The .alog top-level value must be a dictionary.")

    source_unit = str(data.get("mode", "C")).upper()
    if source_unit not in {"C", "F"}:
        source_unit = "C"
    warnings: list[str] = []
    if source_unit == "F":
        warnings.append("Fahrenheit temperatures were converted to Celsius.")

    raw_times, et_values, bt_values = _clean_main_series(
        _list(data, "timex", required=True),
        _list(data, "temp1", required=True),
        _list(data, "temp2", required=True),
        source_unit,
    )
    timeindex = _list(data, "timeindex")
    computed = data.get("computed") if isinstance(data.get("computed"), dict) else {}

    charge_index = timeindex[0] if timeindex else None
    charge_raw, charge_bt_index = _event_from_index(charge_index, raw_times, bt_values)
    _, charge_et_index = _event_from_index(charge_index, raw_times, et_values)
    if charge_raw is None:
        first_valid = next((time for time in raw_times if time is not None), None)
        if first_valid is None:
            raise RoastParseError("The profile has no valid timestamps.")
        charge_raw = first_valid
        warnings.append("Charge event was missing; the first sample was used as time zero.")

    def event_elapsed(index_position: int | None, prefix: str) -> float | None:
        if prefix == "CHARGE":
            return 0.0
        computed_time = _number(computed.get(f"{prefix}_time"))
        if computed_time is not None and computed_time > 0:
            return computed_time
        if index_position is not None and index_position < len(timeindex):
            # Artisan uses index 0 as the missing-event sentinel outside Charge.
            if timeindex[index_position] == 0:
                return None
            raw, _ = _event_from_index(timeindex[index_position], raw_times, bt_values)
            if raw is not None:
                elapsed = raw - charge_raw
                return elapsed if elapsed >= 0 else None
        return None

    drop_elapsed = event_elapsed(6, "DROP")
    if drop_elapsed is None:
        warnings.append("Drop event is missing; curves continue to the recording end.")

    events: list[dict[str, Any]] = []
    event_times: dict[str, float | None] = {}
    for key, name, abbreviation, index_position, prefix in EVENT_SPECS:
        elapsed = event_elapsed(index_position, prefix)
        event_times[key] = elapsed
        if elapsed is None:
            if key not in {"charge", "drop"}:
                warnings.append(f"{name} event is missing.")
            continue

        bt = _to_celsius(_number(computed.get(f"{prefix}_BT")), source_unit)
        et = _to_celsius(_number(computed.get(f"{prefix}_ET")), source_unit)
        if key == "charge":
            bt = bt if bt is not None else charge_bt_index
            et = et if et is not None else charge_et_index
        elif index_position is not None and index_position < len(timeindex):
            _, indexed_bt = _event_from_index(timeindex[index_position], raw_times, bt_values)
            _, indexed_et = _event_from_index(timeindex[index_position], raw_times, et_values)
            bt = bt if bt is not None else indexed_bt
            et = et if et is not None else indexed_et
        elif key == "turningPoint" and bt is None:
            tp_index = computed.get("TP_idx")
            _, bt = _event_from_index(tp_index, raw_times, bt_values)
            _, et_index = _event_from_index(tp_index, raw_times, et_values)
            et = et if et is not None else et_index

        events.append(
            {
                "key": key,
                "name": name,
                "abbreviation": abbreviation,
                "time": round(elapsed, 4),
                "bt": None if bt is None else round(bt, 4),
                "et": None if et is None else round(et, 4),
            }
        )

    bt_series = _build_series(raw_times, bt_values, charge_raw, drop_elapsed)
    et_series = _build_series(raw_times, et_values, charge_raw, drop_elapsed)
    if not bt_series or not et_series:
        raise RoastParseError("No usable samples remain after Charge alignment.")
    heat_series, air_series, extra_warnings = _extra_series(data, charge_raw, drop_elapsed)
    warnings.extend(extra_warnings)

    dry = event_times.get("dryEnd")
    first_crack = event_times.get("firstCrack")
    drop = event_times.get("drop")
    total = drop if drop is not None and drop > 0 else None
    drying = dry if dry is not None and dry >= 0 else None
    browning = first_crack - dry if first_crack is not None and dry is not None and first_crack >= dry else None
    development = drop - first_crack if drop is not None and first_crack is not None and drop >= first_crack else None

    weight = _list(data, "weight")
    green_weight = _number(weight[0]) if len(weight) > 0 else None
    final_weight = _number(weight[1]) if len(weight) > 1 else None
    if green_weight is None:
        green_weight = _number(computed.get("weightin"))
    if final_weight is None:
        final_weight = _number(computed.get("weightout"))
    weight_unit = str(weight[2]).strip() if len(weight) > 2 and weight[2] is not None else ""
    if green_weight is not None and green_weight <= 0:
        green_weight = None
    if final_weight is not None and final_weight < 0:
        final_weight = None
    weight_loss = None
    if green_weight is not None and final_weight is not None:
        calculated_loss = (green_weight - final_weight) / green_weight * 100.0
        if calculated_loss >= 0:
            weight_loss = calculated_loss
    if weight_loss is None:
        computed_loss = _number(computed.get("weight_loss"))
        if computed_loss is not None and computed_loss >= 0:
            weight_loss = computed_loss

    density_data = _list(data, "density")
    density_green = _number(density_data[0]) if len(density_data) > 0 else None
    if density_green is not None and density_green <= 0:
        density_green = None

    return {
        "id": profile_id,
        "filename": os.path.basename(filename),
        "displayName": _display_name(filename),
        "title": str(data.get("title") or _display_name(filename)),
        "bean": _bean_name(filename),
        "unit": "C",
        "notes": {
            "roast": data.get("roastingnotes", "").strip() if isinstance(data.get("roastingnotes"), str) else "",
            "cupping": data.get("cuppingnotes", "").strip() if isinstance(data.get("cuppingnotes"), str) else "",
        },
        "weights": {
            "green": None if green_weight is None else round(green_weight, 4),
            "final": None if final_weight is None else round(final_weight, 4),
            "lossPercent": None if weight_loss is None else round(weight_loss, 1),
            "unit": weight_unit,
        },
        "density": None if density_green is None else round(density_green, 1),
        "phases": {
            "total": None if total is None else round(total, 4),
            "drying": _phase(drying, total),
            "browning": _phase(browning, total),
            "development": _phase(development, total),
        },
        "series": {
            "bt": bt_series,
            "et": et_series,
            "ror": _calculate_ror(bt_series),
            "heat": heat_series,
            "air": air_series,
        },
        "events": events,
        "warnings": [] if os.path.basename(filename).lower().endswith("glitch.alog") else list(dict.fromkeys(warnings)),
    }
