# clab_connector/utils/helpers.py

import logging
import os
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(PACKAGE_ROOT, "templates")

# Kubernetes constraints
MAX_LABEL_VALUE_LEN = 63
DNS1123_SUBDOMAIN_MAX = 253

template_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape()
)


def render_template(template_name: str, data: dict) -> str:
    """
    Render a Jinja2 template by name, using a data dictionary.

    Parameters
    ----------
    template_name : str
        The name of the template file (e.g., "node-profile.j2").
    data : dict
        A dictionary of values to substitute into the template.

    Returns
    -------
    str
        The rendered template as a string.
    """
    template = template_environment.get_template(template_name)
    return template.render(data)


def normalize_name(name: str) -> str:
    """
    Convert a name to a normalized, EDA-safe format.

    Parameters
    ----------
    name : str
        The original name.

    Returns
    -------
    str
        The normalized name.
    """
    safe_name = name.lower().replace("_", "-").replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ".-").strip(".-")
    if not safe_name or not safe_name[0].isalnum():
        safe_name = "x" + safe_name
    if not safe_name[-1].isalnum():
        safe_name += "0"
    return safe_name


def sanitize_label_value(value) -> str:
    """
    Sanitize a label value to be safe for Kubernetes labels.

    Rules applied:
    - Convert to string and strip whitespace.
    - Replace internal whitespace with hyphens.
    - Remove characters not in [A-Za-z0-9-_.].
    - Ensure the value is <= 63 characters (truncate if necessary).
    - Ensure it starts and ends with an alphanumeric character; if not,
      trim offending characters.
    - If the result is empty, return a stable placeholder `value0`.

    Parameters
    ----------
    value : any
        The label value to sanitize.

    Returns
    -------
    str
        A sanitized label value safe for Kubernetes labels.
    """
    # Kubernetes allows empty label values. Preserve empty string result.
    if value is None:
        return ""
    s = str(value).strip()
    if s == "":
        return ""

    # Collapse whitespace to single hyphen
    s = re.sub(r"\s+", "-", s)
    # Remove characters not allowed in label values (allow a-z0-9, -, _, .)
    # Lowercase early to make subsequent checks simpler and to guarantee
    # the emitted label is lowercase as required.
    s = s.lower()
    s = re.sub(r"[^a-z0-9\-_.]", "", s)
    # Trim non-alphanumeric from ends to satisfy k8s start/end rules
    s = re.sub(r"^[^A-Za-z0-9]+", "", s)
    s = re.sub(r"[^A-Za-z0-9]+$", "", s)
    # Truncate to MAX_LABEL_VALUE_LEN characters
    if len(s) > MAX_LABEL_VALUE_LEN:
        s = s[:MAX_LABEL_VALUE_LEN]

    # Validate final form against k8s label value pattern:
    # begin and end with alnum, with [-_.a-z0-9] in between (lowercase)
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9_.-]{0,61}[a-z0-9])?", s):
        return s

    # If sanitization failed to produce a valid value, return a stable
    # fallback that complies with k8s rules.
    return "value0"


def sanitize_label_key(key: str) -> str:
    """
    Sanitize a Kubernetes label key. Supports optional prefix (DNS subdomain)
    followed by '/' and a name. The prefix and name are sanitized separately.

    This function attempts to be conservative: it preserves a valid prefix
    when present and normalizes the name to conform to label name rules.
    """
    if not key:
        return "label"
    key = key.strip()
    # If there's a prefix, validate it as a DNS-1123 subdomain
    if "/" in key:
        prefix, name = key.split("/", 1)
        prefix = prefix.strip().lower()

        # DNS-1123 subdomain regex per k8s: components separated by '.',
        # each component max 63 chars, begin and end with alnum, can contain '-'
        dns_comp = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
        dns_re = re.compile(rf"^(?:{dns_comp})(?:\.(?:{dns_comp}))*$")

        if len(prefix) > DNS1123_SUBDOMAIN_MAX or not dns_re.fullmatch(prefix):
            # Drop invalid prefix to avoid producing an invalid label key
            prefix = ""

        # Sanitize the name part using label value rules, but ensure non-empty
        name_s = sanitize_label_value(name)
        if name_s == "":
            name_s = "label"

        if prefix:
            return f"{prefix}/{name_s}"
        return name_s

    # No prefix present; treat as label name
    name_s = sanitize_label_value(key)
    return name_s if name_s != "" else "label"


def sanitize_labels(labels: dict) -> dict:
    """
    Sanitize a mapping of label keys -> values, producing a new dict
    where keys and values are safe for Kubernetes labels.

    The function avoids dropping labels by transforming keys and values
    into compliant forms. If a sanitized key collides with an existing
    sanitized key, a numeric suffix is appended to make it unique.
    """
    if not labels:
        return {}
    out = {}
    seen = {}
    for k, v in labels.items():
        sk = sanitize_label_key(str(k))
        sv = sanitize_label_value(v)

        # Ensure unique sanitized key by appending a counter if needed
        base = sk
        idx = 1
        while sk in out:
            idx += 1
            sk = f"{base}-{idx}"

        out[sk] = sv
        seen[k] = sk
    return out
