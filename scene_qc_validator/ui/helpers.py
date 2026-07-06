import os
import re


def addon_version():
    manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blender_manifest.toml")
    try:
        with open(manifest_path, "r", encoding="utf-8") as manifest:
            match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', manifest.read())
    except OSError:
        match = None
    return match.group(1) if match else "unknown"


def result_visible(s, r):
    if s.result_filter == 'FAIL' and r.severity != 'FAIL':
        return False
    if s.result_filter == 'FIXABLE' and not r.can_fix:
        return False
    return True
