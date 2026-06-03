"""
app/services/ua_parser.py — Pure-Python User-Agent parser.

No third-party dependencies. Uses regex heuristics that cover ~95% of
real-world traffic. Results are used for analytics bucketing only,
not for security decisions.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UAResult:
    browser: str       # Chrome | Firefox | Safari | Edge | Opera | Other
    os: str            # Windows | macOS | iOS | Android | Linux | Other
    device_type: str   # desktop | mobile | tablet


# ---------------------------------------------------------------------------
# Compiled patterns — order matters (most specific first)
# ---------------------------------------------------------------------------

_MOBILE_RE = re.compile(r"Mobile|Android.*Mobile|iPhone|Windows Phone", re.I)
_TABLET_RE = re.compile(r"iPad|Android(?!.*Mobile)|Tablet", re.I)

_BROWSER_PATTERNS = [
    ("Edge", re.compile(r"Edg/|Edge/", re.I)),
    ("Opera", re.compile(r"OPR/|Opera", re.I)),
    ("Chrome", re.compile(r"Chrome/", re.I)),
    ("Firefox", re.compile(r"Firefox/", re.I)),
    ("Safari", re.compile(r"Safari/", re.I)),
]

_OS_PATTERNS = [
    ("iOS", re.compile(r"iPhone|iPad|CPU OS", re.I)),
    ("Android", re.compile(r"Android", re.I)),
    ("Windows", re.compile(r"Windows NT|Windows Phone", re.I)),
    ("macOS", re.compile(r"Macintosh|Mac OS X", re.I)),
    ("Linux", re.compile(r"Linux", re.I)),
]


def parse_ua(user_agent: str | None) -> UAResult:
    """
    Parse a User-Agent string into browser, OS, and device-type buckets.
    Returns ``UAResult(browser='Other', os='Other', device_type='desktop')``
    for None / empty / unrecognised strings.
    """
    if not user_agent:
        return UAResult(browser="Other", os="Other", device_type="desktop")

    # Device type — check tablet before mobile (tablets send both keywords)
    if _TABLET_RE.search(user_agent):
        device_type = "tablet"
    elif _MOBILE_RE.search(user_agent):
        device_type = "mobile"
    else:
        device_type = "desktop"

    # Browser
    browser = "Other"
    for name, pattern in _BROWSER_PATTERNS:
        if pattern.search(user_agent):
            browser = name
            break

    # OS
    os_ = "Other"
    for name, pattern in _OS_PATTERNS:
        if pattern.search(user_agent):
            os_ = name
            break

    return UAResult(browser=browser, os=os_, device_type=device_type)


def aggregate_ua_list(user_agents: list[str | None]) -> dict:
    """
    Parse a list of user-agent strings and return aggregated counts.

    Returns::

        {
            "browsers":     {"Chrome": 10, "Firefox": 3, ...},
            "os":           {"Windows": 8, "macOS": 5, ...},
            "device_types": {"desktop": 12, "mobile": 1, ...},
        }
    """
    browsers: dict[str, int] = {}
    oses: dict[str, int] = {}
    device_types: dict[str, int] = {}

    for ua in user_agents:
        result = parse_ua(ua)
        browsers[result.browser] = browsers.get(result.browser, 0) + 1
        oses[result.os] = oses.get(result.os, 0) + 1
        device_types[result.device_type] = device_types.get(result.device_type, 0) + 1

    return {
        "browsers": browsers,
        "os": oses,
        "device_types": device_types,
    }
