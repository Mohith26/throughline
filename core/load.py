"""Reads a design file from JSON on disk.

Loading is separated from validation on purpose. This module's job is to turn
text into objects and to complain only about things that make an object
impossible to build, such as a missing title or an unknown severity word. Every
other kind of problem, including links that point at nothing, is left for
trace.py to report as a finding, because a half written design file still has to
load.
"""

import json
import os

from core import model

SECTIONS = ("needs", "requirements", "hazards", "controls", "verifications", "runs")


class LoadError(ValueError):
    def __init__(self, message, section=None, index=None, identifier=None):
        parts = []
        if section:
            parts.append(section)
        if identifier:
            parts.append(identifier)
        elif index is not None:
            parts.append("entry %d" % index)
        prefix = " ".join(parts)
        super(LoadError, self).__init__(("%s: %s" % (prefix, message)) if prefix else message)
        self.section = section
        self.index = index
        self.identifier = identifier


def _get(row, key, section, index, required=True, default=None):
    if key in row:
        return row[key]
    if required:
        raise LoadError("missing field %r" % key, section, index, row.get("id"))
    return default


def from_dict(payload):
    if not isinstance(payload, dict):
        raise LoadError("top level must be an object")
    unknown = [k for k in payload if k not in SECTIONS and not k.startswith("_")]
    if unknown:
        raise LoadError("unknown top level sections: %s" % ", ".join(sorted(unknown)))

    design = model.DesignFile()

    for index, row in enumerate(payload.get("needs", [])):
        design.add(model.UserNeed(
            _get(row, "id", "needs", index), _get(row, "title", "needs", index),
            **{k: v for k, v in row.items() if k not in ("id", "title")}))

    for index, row in enumerate(payload.get("requirements", [])):
        design.add(model.Requirement(
            _get(row, "id", "requirements", index), _get(row, "title", "requirements", index),
            needs=_get(row, "needs", "requirements", index, required=False, default=[]),
            safety_related=_get(row, "safety_related", "requirements", index,
                                required=False, default=False),
            **{k: v for k, v in row.items()
               if k not in ("id", "title", "needs", "safety_related")}))

    for index, row in enumerate(payload.get("hazards", [])):
        try:
            design.add(model.Hazard(
                _get(row, "id", "hazards", index), _get(row, "title", "hazards", index),
                _get(row, "severity", "hazards", index),
                _get(row, "probability", "hazards", index),
                **{k: v for k, v in row.items()
                   if k not in ("id", "title", "severity", "probability")}))
        except model.ModelError as exc:
            raise LoadError(str(exc), "hazards", index, row.get("id"))

    for index, row in enumerate(payload.get("controls", [])):
        try:
            design.add(model.RiskControl(
                _get(row, "id", "controls", index), _get(row, "title", "controls", index),
                _get(row, "hazard", "controls", index),
                requirement=_get(row, "requirement", "controls", index, required=False),
                residual_severity=_get(row, "residual_severity", "controls", index, required=False),
                residual_probability=_get(row, "residual_probability", "controls", index,
                                          required=False),
                **{k: v for k, v in row.items()
                   if k not in ("id", "title", "hazard", "requirement",
                                "residual_severity", "residual_probability")}))
        except model.ModelError as exc:
            raise LoadError(str(exc), "controls", index, row.get("id"))

    for index, row in enumerate(payload.get("verifications", [])):
        design.add(model.Verification(
            _get(row, "id", "verifications", index), _get(row, "title", "verifications", index),
            requirements=_get(row, "requirements", "verifications", index,
                              required=False, default=[]),
            method=_get(row, "method", "verifications", index, required=False, default="test"),
            sample_size=_get(row, "sample_size", "verifications", index, required=False),
            acceptance=_get(row, "acceptance", "verifications", index, required=False),
            **{k: v for k, v in row.items()
               if k not in ("id", "title", "requirements", "method",
                            "sample_size", "acceptance")}))

    for index, row in enumerate(payload.get("runs", [])):
        try:
            design.add(model.TestRun(
                _get(row, "id", "runs", index), _get(row, "verification", "runs", index),
                _get(row, "result", "runs", index), _get(row, "executed_on", "runs", index),
                units=_get(row, "units", "runs", index, required=False),
                failures=_get(row, "failures", "runs", index, required=False),
                notes=_get(row, "notes", "runs", index, required=False),
                **{k: v for k, v in row.items()
                   if k not in ("id", "verification", "result", "executed_on",
                                "units", "failures", "notes")}))
        except model.ModelError as exc:
            raise LoadError(str(exc), "runs", index, row.get("id"))

    return design


def load(path):
    with open(path, "r") as handle:
        try:
            payload = json.load(handle)
        except ValueError as exc:
            raise LoadError("file is not valid JSON: %s" % exc)
    return from_dict(payload)


def load_dir(directory):
    """Merge every .json file in a directory into one design file, which is how
    a real project splits things up by subsystem."""
    design = model.DesignFile()
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        part = load(os.path.join(directory, name))
        for section in SECTIONS:
            source = getattr(part, section)
            target = getattr(design, section)
            for key, value in source.items():
                if key in target:
                    raise LoadError("duplicate id %s across files" % key, section)
                target[key] = value
    return design
