#!/usr/bin/env python3
"""Prepare an AAS Web UI update without changing unrelated chart formatting."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


RELEASES_URL = "https://api.github.com/repos/eclipse-basyx/basyx-aas-web-ui/releases"
IMAGE = "eclipsebasyx/aas-gui"
TAG_PATTERN = re.compile(r"v([1-9][0-9]*)-([0-9]{6})")


def tag_version(tag):
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError(f"Unsupported Web UI tag: {tag!r}")
    major, date = match.groups()
    # Explicit century avoids strptime's two-digit-year pivot.
    day = datetime.date(2000 + int(date[:2]), int(date[2:4]), int(date[4:]))
    return int(major), day


def request_json(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_releases(token):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "basyx-chart-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    releases = []
    page = 1
    while True:
        batch = request_json(f"{RELEASES_URL}?per_page=100&page={page}", headers)
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def latest_release(releases, current_tag):
    current = tag_version(current_tag)
    candidates = []
    for release in releases:
        if release.get("draft") or release.get("prerelease") or not release.get("published_at"):
            continue
        tag = release.get("tag_name", "")
        try:
            version = tag_version(tag)
        except ValueError:
            continue
        if version[0] == current[0] and version > current:
            candidates.append((version, tag))
    return max(candidates)[1] if candidates else None


def image_available(tag):
    token = request_json(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{IMAGE}:pull"
    )["token"]
    request = urllib.request.Request(
        f"https://registry-1.docker.io/v2/{IMAGE}/manifests/{tag}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": ", ".join([
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            ]),
        },
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        # Authentication errors, rate limits and outages must fail visibly.
        raise


def image_tag_match(values):
    block = re.search(r"^aasWebGui:\n(?:(?:[ \t].*|)\n)*", values, re.MULTILINE)
    if block is None:
        raise ValueError("Cannot locate aasWebGui values")
    image = re.search(r"^  image:\n(?:    .*\n)*", block.group(), re.MULTILINE)
    if image is None or not re.search(
        rf"^    repository: {re.escape(IMAGE)}\s*$", image.group(), re.MULTILINE
    ):
        raise ValueError(f"Expected aasWebGui.image.repository: {IMAGE}")
    tag = re.search(r"^    tag: (?P<tag>v[1-9][0-9]*-[0-9]{6})[ \t]*$", image.group(), re.MULTILINE)
    if tag is None:
        raise ValueError("Cannot locate supported aasWebGui.image.tag")
    start = block.start() + image.start() + tag.start("tag")
    return tag.group("tag"), start, start + len(tag.group("tag"))


def prepare_update(root, releases, available):
    values_path = root / "charts/basyx/values.yaml"
    values = values_path.read_text()
    old_tag, start, end = image_tag_match(values)
    new_tag = latest_release(releases, old_tag)
    if new_tag is None:
        print(f"AAS Web UI is current ({old_tag}).")
        return {}
    if not available(new_tag):
        print(f"Waiting for {IMAGE}:{new_tag} to be published.")
        return {}

    chart_path = root / "charts/basyx/Chart.yaml"
    chart = chart_path.read_text()
    version_match = re.search(r"^version: ([0-9]+)\.([0-9]+)\.([0-9]+)$", chart, re.MULTILINE)
    if version_match is None:
        raise ValueError("Expected a stable chart version")
    major, minor, patch = map(int, version_match.groups())
    version = f"{major}.{minor}.{patch + 1}"
    chart = chart[:version_match.start()] + f"version: {version}" + chart[version_match.end():]

    readme_path = root / "README.md"
    readme = readme_path.read_text()
    heading = "### Upgrading to chart "
    index = readme.find(heading)
    if index == -1:
        raise ValueError("Cannot locate README upgrade notes")
    note = (
        f"### Upgrading to chart {version}\n\n"
        f"Chart {version} updates the default AAS Web UI image to `{new_tag}`.\n\n"
    )
    # Validate and calculate every edit before writing any file.
    values_path.write_text(values[:start] + new_tag + values[end:])
    chart_path.write_text(chart)
    readme_path.write_text(readme[:index] + note + readme[index:])
    print(f"Prepared chart {version}: {old_tag} -> {new_tag}")
    return {"tag": new_tag, "chart-version": version, "previous-tag": old_tag}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    result = prepare_update(
        args.root, fetch_releases(os.environ.get("GH_TOKEN")), image_available
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"changed={'true' if result else 'false'}\n")
            for key, value in result.items():
                output.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
