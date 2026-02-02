# clab_connector/services/workflow/network_topology_generator.py

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml

from clab_connector.clients.kubernetes.client import list_nodeprofiles
from clab_connector.models.node.factory import create_node
from clab_connector.utils import helpers
from clab_connector.utils.constants import SUBSTEP_INDENT
from clab_connector.utils.exceptions import TopologyFileError
from clab_connector.utils.yaml_processor import YAMLProcessor

logger = logging.getLogger(__name__)

SUPPORTED_KINDS = {
    "nokia_srlinux",
    "nokia_sros",
    "nokia_srsim",
    "arista_ceos",
}
SIM_NODE_KIND = "linux"
DEFAULT_SIM_IMAGE = "ghcr.io/srl-labs/network-multitool:latest"

NODE_TEMPLATE_LABEL_KEYS = (
    "eda.nokia.com/node-template",
    "eda.nokia.com/nodeTemplate",
    "eda.nokia.com/template",
)
NODE_PROFILE_LABEL_KEYS = (
    "eda.nokia.com/node-profile",
    "eda.nokia.com/nodeProfile",
)
NODEPROFILE_CONTAINER_IMAGE_LABEL_KEYS = (
    "eda.nokia.com/nodeprofile-container-image",
    "eda.nokia.com/nodeprofileContainerImage",
)
NODEPROFILE_IMAGE_PULL_SECRET_LABEL_KEYS = (
    "eda.nokia.com/nodeprofile-image-pull-secret",
    "eda.nokia.com/nodeprofileImagePullSecret",
)
PLATFORM_LABEL_KEYS = ("eda.nokia.com/platform",)
ROLE_LABEL_KEYS = ("eda.nokia.com/role", "role")
SECURITY_PROFILE_LABEL_KEYS = ("eda.nokia.com/security-profile",)

SIM_NODE_TEMPLATE_LABEL_KEYS = (
    "eda.nokia.com/sim-node-template",
    "eda.nokia.com/simNodeTemplate",
)
SIM_NODE_TYPE_LABEL_KEYS = ("eda.nokia.com/sim-type", "eda.nokia.com/simType")
SIM_NODE_IMAGE_LABEL_KEYS = ("eda.nokia.com/sim-image", "eda.nokia.com/simImage")

LINK_TEMPLATE_LABEL_KEYS = (
    "eda.nokia.com/link-template",
    "eda.nokia.com/linkTemplate",
)
LINK_TYPE_LABEL_KEYS = ("eda.nokia.com/link-type", "eda.nokia.com/linkType")
LINK_SPEED_LABEL_KEYS = ("eda.nokia.com/link-speed", "eda.nokia.com/linkSpeed")
LINK_ENCAP_LABEL_KEYS = ("eda.nokia.com/encap-type", "eda.nokia.com/encapType")

NODE_CONTROL_LABELS = {
    *NODE_TEMPLATE_LABEL_KEYS,
    *NODE_PROFILE_LABEL_KEYS,
    *NODEPROFILE_CONTAINER_IMAGE_LABEL_KEYS,
    *NODEPROFILE_IMAGE_PULL_SECRET_LABEL_KEYS,
    *PLATFORM_LABEL_KEYS,
}
LINK_CONTROL_LABELS = {
    *LINK_TEMPLATE_LABEL_KEYS,
    *LINK_TYPE_LABEL_KEYS,
    *LINK_SPEED_LABEL_KEYS,
    *LINK_ENCAP_LABEL_KEYS,
}


class NetworkTopologyGenerator:
    """
    Generate an EDA NetworkTopology workflow YAML from a containerlab .clab.yml file.

    Label-based overrides (containerlab node labels):
      - eda.nokia.com/node-template: explicit nodeTemplate name
      - eda.nokia.com/node-profile: override nodeProfile for the template
      - eda.nokia.com/platform: override platform for the template
      - eda.nokia.com/role or role: set eda.nokia.com/role label
      - eda.nokia.com/security-profile: set security profile label
      - eda.nokia.com/nodeprofile-container-image: override nodeProfile containerImage
      - eda.nokia.com/nodeprofile-image-pull-secret: override nodeProfile imagePullSecret
      - eda.nokia.com/sim-node-template: explicit simNodeTemplate name (linux nodes)
      - eda.nokia.com/sim-type: override simNodeTemplate type (linux nodes)
      - eda.nokia.com/sim-image: override simNodeTemplate image (linux nodes)

    Label-based overrides (containerlab link labels):
      - eda.nokia.com/link-template: explicit linkTemplate name
      - eda.nokia.com/link-type: override link type (interSwitch|edge|loopback)
      - eda.nokia.com/link-speed: set template speed
      - eda.nokia.com/encap-type: set template encapType
    """

    def __init__(
        self,
        topology_file: str | Path,
        output: str | Path | None = None,
        nodeprofiles_output: str | Path | None = None,
        namespace: str | None = None,
        operation: str | None = None,
        resolve_nodeprofiles: bool = False,
        create_nodeprofiles: bool = True,
    ) -> None:
        self.topology_file = Path(topology_file)
        self.output = Path(output) if output else None
        self.nodeprofiles_output = (
            Path(nodeprofiles_output) if nodeprofiles_output else None
        )
        self.namespace = namespace or "eda"
        self.operation = operation
        self.resolve_nodeprofiles = resolve_nodeprofiles and not create_nodeprofiles
        self.create_nodeprofiles = create_nodeprofiles
        self._nodeprofiles = (
            self._load_nodeprofiles()
            if (resolve_nodeprofiles or create_nodeprofiles)
            else {}
        )
        self._nodeprofile_defs: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._topo_name: str | None = None

    def run(self) -> Path:
        data = self._load_yaml()
        topology = data.get("topology") or {}
        if not isinstance(topology, dict):
            raise TopologyFileError("Invalid topology section in clab YAML")

        nodes_data = topology.get("nodes") or {}
        if not isinstance(nodes_data, dict):
            raise TopologyFileError("Invalid topology.nodes section in clab YAML")

        links_data = topology.get("links") or []
        if not isinstance(links_data, list):
            raise TopologyFileError("Invalid topology.links section in clab YAML")

        kinds_data = topology.get("kinds") or {}
        if not isinstance(kinds_data, dict):
            kinds_data = {}

        topo_name_raw = data.get("name") or self.topology_file.stem
        topo_name = helpers.normalize_name(str(topo_name_raw))
        self._topo_name = topo_name

        (
            node_templates,
            nodes_out,
            node_infos,
            sim_node_templates,
            sim_nodes,
        ) = self._build_nodes(nodes_data, kinds_data)
        link_templates, links_out = self._build_links(links_data, node_infos)

        spec: dict[str, Any] = {}
        if node_templates:
            spec["nodeTemplates"] = node_templates
        if nodes_out:
            spec["nodes"] = nodes_out
        if link_templates:
            spec["linkTemplates"] = link_templates
        if links_out:
            spec["links"] = links_out
        if sim_node_templates or sim_nodes:
            simulation: dict[str, Any] = {}
            if sim_node_templates:
                simulation["simNodeTemplates"] = sim_node_templates
            if sim_nodes:
                simulation["simNodes"] = sim_nodes
            spec["simulation"] = simulation
        if self.operation:
            spec["operation"] = self.operation

        if not spec:
            logger.warning(
                "%sNo supported nodes or links found; output will be minimal.",
                SUBSTEP_INDENT,
            )

        workflow: dict[str, Any] = {
            "apiVersion": "topologies.eda.nokia.com/v1alpha1",
            "kind": "NetworkTopology",
            "metadata": {"name": topo_name},
            "spec": spec,
        }
        if self.namespace:
            workflow["metadata"]["namespace"] = self.namespace

        output_path = self._resolve_output_path(topo_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        processor = YAMLProcessor()
        if self.create_nodeprofiles and self._nodeprofile_defs:
            nodeprofile_docs = list(self._nodeprofile_defs.values())
            if self.nodeprofiles_output:
                self.nodeprofiles_output.parent.mkdir(parents=True, exist_ok=True)
                processor.save_yaml_documents(
                    nodeprofile_docs, str(self.nodeprofiles_output)
                )
                processor.save_yaml(workflow, str(output_path))
                logger.info(
                    "%sNetworkTopology written to %s", SUBSTEP_INDENT, output_path
                )
                logger.info(
                    "%sNodeProfiles written to %s",
                    SUBSTEP_INDENT,
                    self.nodeprofiles_output,
                )
            else:
                processor.save_yaml_documents(
                    [*nodeprofile_docs, workflow], str(output_path)
                )
                logger.info(
                    "%sNodeProfiles + NetworkTopology written to %s",
                    SUBSTEP_INDENT,
                    output_path,
                )
        else:
            processor.save_yaml(workflow, str(output_path))
            logger.info("%sNetworkTopology written to %s", SUBSTEP_INDENT, output_path)
        return output_path

    def _load_yaml(self) -> dict[str, Any]:
        if not self.topology_file.exists():
            raise TopologyFileError(
                f"Topology file '{self.topology_file}' does not exist"
            )
        try:
            with self.topology_file.open() as handle:
                data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise TopologyFileError(
                f"Topology file '{self.topology_file}' is not valid YAML"
            ) from exc
        except OSError as exc:
            raise TopologyFileError(
                f"Failed to read topology file '{self.topology_file}': {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise TopologyFileError("Topology YAML must be a mapping")
        return data

    def _build_nodes(
        self, nodes_data: dict[str, Any], kinds_data: dict[str, Any]
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        templates: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        nodes_out: list[dict[str, Any]] = []
        node_infos: dict[str, dict[str, Any]] = {}
        sim_templates: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        sim_nodes: list[dict[str, Any]] = []
        used_names: set[str] = set()

        for raw_name, node_data in nodes_data.items():
            if not isinstance(node_data, dict):
                logger.warning(
                    "%sSkipping node '%s': node entry is not a mapping",
                    SUBSTEP_INDENT,
                    raw_name,
                )
                continue

            kind = node_data.get("kind")
            if not kind:
                logger.warning(
                    "%sSkipping node '%s': missing kind", SUBSTEP_INDENT, raw_name
                )
                continue

            kind_defaults = kinds_data.get(kind, {}) if isinstance(kinds_data, dict) else {}
            node_type = node_data.get("type") or kind_defaults.get("type")
            image = node_data.get("image") or kind_defaults.get("image")
            version = self._parse_image_version(image)
            raw_labels = node_data.get("labels") if isinstance(node_data.get("labels"), dict) else {}

            normalized_name = self._unique_name(str(raw_name), used_names)

            if kind == SIM_NODE_KIND:
                sim_template_name = self._label_value(
                    raw_labels, SIM_NODE_TEMPLATE_LABEL_KEYS
                )
                sim_type = self._label_value(raw_labels, SIM_NODE_TYPE_LABEL_KEYS)
                sim_image = self._label_value(raw_labels, SIM_NODE_IMAGE_LABEL_KEYS)

                if not sim_template_name:
                    sim_template_name = self._default_sim_template_name(image)
                sim_template_name = helpers.normalize_name(sim_template_name)

                if not sim_type:
                    sim_type = "Linux"

                if not sim_image:
                    sim_image = image or DEFAULT_SIM_IMAGE

                sim_template = {
                    "name": sim_template_name,
                    "type": sim_type,
                    "image": sim_image,
                }
                if sim_template_name not in sim_templates:
                    sim_templates[sim_template_name] = sim_template
                else:
                    self._warn_sim_template_conflict(
                        sim_template_name, sim_templates[sim_template_name], sim_template
                    )

                sim_nodes.append(
                    {"name": normalized_name, "template": sim_template_name}
                )

                node_infos[str(raw_name)] = {
                    "raw_name": str(raw_name),
                    "name": normalized_name,
                    "kind": kind,
                    "type": node_type,
                    "image": image,
                    "version": version,
                    "labels": raw_labels,
                    "node_obj": None,
                    "supported": False,
                    "sim": True,
                    "sim_template": sim_template_name,
                }
                continue

            node_obj = None
            if kind in SUPPORTED_KINDS:
                node_obj = create_node(
                    name=str(raw_name),
                    config={
                        "kind": kind,
                        "type": node_type,
                        "version": version,
                        "mgmt_ipv4": None,
                        "mgmt_ipv4_prefix_length": None,
                        "labels": None,
                    },
                )

            node_info = {
                "raw_name": str(raw_name),
                "name": normalized_name,
                "kind": kind,
                "type": node_type,
                "image": image,
                "version": version,
                "labels": raw_labels,
                "node_obj": node_obj,
                "supported": node_obj is not None,
                "sim": False,
            }
            node_infos[str(raw_name)] = node_info

            if not node_info["supported"]:
                logger.info(
                    "%sSkipping unsupported node '%s' (kind=%s)",
                    SUBSTEP_INDENT,
                    raw_name,
                    kind,
                )
                continue

            template_name = self._label_value(raw_labels, NODE_TEMPLATE_LABEL_KEYS)
            if template_name:
                template_name = template_name.strip()
            role_value = self._label_value(raw_labels, ROLE_LABEL_KEYS)
            sec_profile = self._label_value(raw_labels, SECURITY_PROFILE_LABEL_KEYS)

            explicit_profile = self._label_value(raw_labels, NODE_PROFILE_LABEL_KEYS)
            if self.create_nodeprofiles:
                node_profile = self._ensure_nodeprofile(
                    kind=kind,
                    version=version,
                    image=image,
                    raw_labels=raw_labels,
                    base_profile_name=explicit_profile,
                )
            else:
                node_profile = explicit_profile
                if not node_profile:
                    node_profile = self._derive_node_profile(kind, version, image)
                    resolved = self._resolve_nodeprofile(kind, version)
                    if resolved:
                        node_profile = resolved
                if not node_profile:
                    node_profile = f"{kind}-unknown"
                    logger.warning(
                        "%sNode '%s' missing version; using nodeProfile '%s'",
                        SUBSTEP_INDENT,
                        raw_name,
                        node_profile,
                    )

            platform = self._label_value(raw_labels, PLATFORM_LABEL_KEYS)
            if not platform:
                platform = self._derive_platform(node_obj, node_type, kind)

            if not template_name:
                template_name = self._default_node_template_name(
                    kind, node_type, version, role_value
                )

            template_labels = self._build_template_labels(
                raw_labels,
                role_value,
                sec_profile,
                control_keys=NODE_CONTROL_LABELS,
            )

            template = {
                "name": template_name,
                "nodeProfile": node_profile,
                "platform": platform,
            }
            if template_labels:
                template["labels"] = template_labels

            if template_name not in templates:
                templates[template_name] = template
            else:
                self._warn_template_conflict(
                    template_name, templates[template_name], template
                )

            node_labels = self._build_node_labels(
                raw_labels,
                role_value,
                sec_profile,
                control_keys=NODE_CONTROL_LABELS,
            )
            node_entry = {"name": normalized_name, "template": template_name}
            if node_labels:
                node_entry["labels"] = node_labels
            nodes_out.append(node_entry)

        return (
            list(templates.values()),
            nodes_out,
            node_infos,
            list(sim_templates.values()),
            sim_nodes,
        )

    def _build_links(
        self, links_data: list[Any], node_infos: dict[str, dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        templates: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        links_out: list[dict[str, Any]] = []
        used_link_names: set[str] = set()

        for link_idx, link in enumerate(links_data, start=1):
            link_info = link if isinstance(link, dict) else {}
            endpoints = self._extract_endpoints(link)
            if not endpoints or len(endpoints) != 2:
                logger.warning(
                    "%sSkipping link %d: invalid endpoints",
                    SUBSTEP_INDENT,
                    link_idx,
                )
                continue

            a_raw, a_intf = self._split_endpoint(endpoints[0])
            b_raw, b_intf = self._split_endpoint(endpoints[1])
            if not a_raw or not b_raw:
                logger.warning(
                    "%sSkipping link %d: invalid endpoint format",
                    SUBSTEP_INDENT,
                    link_idx,
                )
                continue

            a_info = node_infos.get(a_raw)
            b_info = node_infos.get(b_raw)
            if not a_info or not b_info:
                logger.warning(
                    "%sSkipping link %d: unknown nodes '%s' or '%s'",
                    SUBSTEP_INDENT,
                    link_idx,
                    a_raw,
                    b_raw,
                )
                continue

            a_supported = a_info.get("supported", False)
            b_supported = b_info.get("supported", False)
            a_sim = a_info.get("sim", False)
            b_sim = b_info.get("sim", False)
            if (a_sim and b_sim) or (not (a_supported or b_supported or a_sim or b_sim)):
                logger.info(
                    "%sSkipping link %d: endpoints unsupported or both sim nodes",
                    SUBSTEP_INDENT,
                    link_idx,
                )
                continue

            a_intf = self._map_interface_name(a_info, a_intf)
            b_intf = self._map_interface_name(b_info, b_intf)

            link_labels = (
                link_info.get("labels") if isinstance(link_info.get("labels"), dict) else {}
            )
            explicit_type = self._normalize_link_type(
                self._label_value(link_labels, LINK_TYPE_LABEL_KEYS)
            )

            if a_raw == b_raw:
                link_type = "loopback"
            elif a_supported and b_supported:
                link_type = "interSwitch"
            else:
                link_type = "edge"

            if explicit_type:
                if explicit_type != link_type:
                    logger.warning(
                        "%sLink %d type override '%s' differs from inferred '%s'",
                        SUBSTEP_INDENT,
                        link_idx,
                        explicit_type,
                        link_type,
                    )
                link_type = explicit_type

            if (a_sim or b_sim) and link_type != "edge":
                logger.warning(
                    "%sLink %d connects to a sim node; forcing link type to 'edge'",
                    SUBSTEP_INDENT,
                    link_idx,
                )
                link_type = "edge"

            template_name = self._label_value(link_labels, LINK_TEMPLATE_LABEL_KEYS)
            if template_name:
                template_name = template_name.strip()
            if not template_name:
                template_name = link_type

            template = self._build_link_template(link_type, link_labels, template_name)
            if template_name not in templates:
                templates[template_name] = template
            else:
                self._warn_template_conflict(
                    template_name, templates[template_name], template
                )

            local_node = a_info["name"]
            local_intf = a_intf
            remote_node = b_info["name"]
            remote_intf = b_intf

            if link_type in {"edge", "loopback"}:
                local_info = a_info
                remote_info = b_info
                local_intf_use = a_intf
                remote_intf_use = b_intf

                if not a_supported and b_supported:
                    local_info = b_info
                    remote_info = a_info
                    local_intf_use = b_intf
                    remote_intf_use = a_intf

                link_name = self._unique_name(
                    f"{local_info['name']}-{local_intf_use}", used_link_names
                )
                endpoint: dict[str, Any] = {
                    "local": {
                        "node": local_info["name"],
                        "interface": local_intf_use,
                    }
                }

                if remote_info.get("sim", False):
                    endpoint["sim"] = {
                        "simNode": remote_info["name"],
                        "simNodeInterface": remote_intf_use,
                    }
                elif link_type == "loopback":
                    endpoint["remote"] = {
                        "node": remote_info["name"],
                        "interface": remote_intf_use,
                    }

                link_entry = {
                    "name": link_name,
                    "template": template_name,
                    "endpoints": [endpoint],
                }
            else:
                link_name = self._unique_name(
                    f"{local_node}-{local_intf}-{remote_node}-{remote_intf}",
                    used_link_names,
                )
                endpoint = {
                    "local": {"node": local_node, "interface": local_intf},
                    "remote": {"node": remote_node, "interface": remote_intf},
                }
                link_entry = {
                    "name": link_name,
                    "template": template_name,
                    "endpoints": [endpoint],
                }

            links_out.append(link_entry)

        return list(templates.values()), links_out

    def _build_link_template(
        self, link_type: str, link_labels: dict[str, Any], template_name: str
    ) -> dict[str, Any]:
        labels = self._build_template_labels(
            link_labels,
            role_value=self._label_value(link_labels, ROLE_LABEL_KEYS) or link_type,
            sec_profile=None,
            control_keys=LINK_CONTROL_LABELS,
            default_security_profile=False,
        )
        template: dict[str, Any] = {"name": template_name, "type": link_type}
        if labels:
            template["labels"] = labels

        speed = self._label_value(link_labels, LINK_SPEED_LABEL_KEYS)
        if speed:
            template["speed"] = str(speed)

        encap = self._label_value(link_labels, LINK_ENCAP_LABEL_KEYS)
        if encap:
            template["encapType"] = str(encap)
        else:
            template["encapType"] = "null"

        return template

    def _default_node_template_name(
        self,
        kind: str | None,
        node_type: str | None,
        version: str | None,
        role_value: str | None,
    ) -> str:
        parts = [p for p in [kind, node_type, version, role_value] if p]
        base = "-".join(parts) if parts else "node"
        return helpers.normalize_name(base)

    def _default_sim_template_name(self, image: str | None) -> str:
        if image and "network-multitool" in image:
            return "multitool"
        return "linux"

    def _kind_to_os(self, kind: str | None) -> str | None:
        os_map = {
            "nokia_srlinux": "srl",
            "nokia_sros": "sros",
            "nokia_srsim": "sros",
            "arista_ceos": "eos",
        }
        return os_map.get(kind or "")

    def _default_nodeprofile_name(
        self,
        os_key: str | None,
        version: str | None,
        base_profile_name: str | None,
    ) -> str:
        topo_name = self._topo_name or "topology"
        if base_profile_name:
            if base_profile_name.startswith(f"{topo_name}-"):
                return base_profile_name
            suffix = base_profile_name
        elif os_key and version:
            suffix = f"{os_key}-{version}"
        elif os_key:
            suffix = os_key
        else:
            suffix = "nodeprofile"
        return helpers.normalize_name(f"{topo_name}-{suffix}")

    def _select_base_profile(
        self, kind: str | None, version: str | None, base_profile_name: str | None
    ) -> dict[str, Any] | None:
        by_name = self._nodeprofiles.get("by_name", {}) if self._nodeprofiles else {}
        if base_profile_name and base_profile_name in by_name:
            return by_name[base_profile_name]

        os_key = self._kind_to_os(kind)
        if not os_key:
            return None

        candidates = (
            self._nodeprofiles.get("by_os_version", {}).get(os_key, {})
            if self._nodeprofiles
            else {}
        )
        if not candidates:
            return None

        if version:
            normalized = self._normalize_version(kind, version).lower()
            if normalized in candidates:
                return candidates[normalized]

        entry = next(iter(candidates.values()))
        logger.warning(
            "%sNodeProfile for %s version %s not found in %s; using profile %s as base",
            SUBSTEP_INDENT,
            os_key,
            version,
            self.namespace,
            entry["name"],
        )
        return entry

    def _build_nodeprofile_spec(
        self,
        kind: str | None,
        version: str | None,
        image: str | None,
        raw_labels: dict[str, Any],
        base_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        spec: dict[str, Any] = {}
        if base_entry and isinstance(base_entry.get("spec"), dict):
            spec = dict(base_entry["spec"])

        os_key = self._kind_to_os(kind)
        normalized_version = self._normalize_version(kind, version) if version else None

        if os_key and not spec.get("operatingSystem"):
            spec["operatingSystem"] = os_key
        if normalized_version and not spec.get("version"):
            spec["version"] = normalized_version

        container_image = self._label_value(
            raw_labels, NODEPROFILE_CONTAINER_IMAGE_LABEL_KEYS
        )
        if container_image:
            spec["containerImage"] = container_image

        image_pull_secret = self._label_value(
            raw_labels, NODEPROFILE_IMAGE_PULL_SECRET_LABEL_KEYS
        )
        if image_pull_secret:
            spec["imagePullSecret"] = image_pull_secret

        if not spec:
            logger.warning(
                "%sNo base NodeProfile spec available for kind=%s version=%s; "
                "creating stub spec",
                SUBSTEP_INDENT,
                kind,
                version,
            )
            spec = {
                "operatingSystem": os_key or "unknown",
                "version": normalized_version or "unknown",
                "nodeUser": "admin",
                "onboardingUsername": "admin",
                "onboardingPassword": "admin",
                "yang": "",
            }

        missing_required = [
            field
            for field in (
                "nodeUser",
                "onboardingUsername",
                "onboardingPassword",
                "operatingSystem",
                "version",
                "yang",
            )
            if not spec.get(field)
        ]
        if missing_required:
            logger.warning(
                "%sNodeProfile spec missing required fields %s; "
                "you may need to patch the profile",
                SUBSTEP_INDENT,
                ", ".join(missing_required),
            )

        if os_key in {"srl", "sros"} and not spec.get("containerImage"):
            logger.warning(
                "%sNodeProfile spec for %s %s has no containerImage; "
                "sim pods will not start until it is set",
                SUBSTEP_INDENT,
                os_key,
                spec.get("version", version),
            )

        return spec

    def _ensure_nodeprofile(
        self,
        kind: str | None,
        version: str | None,
        image: str | None,
        raw_labels: dict[str, Any],
        base_profile_name: str | None,
    ) -> str:
        os_key = self._kind_to_os(kind)
        normalized_version = self._normalize_version(kind, version) if version else None

        base_entry = self._select_base_profile(kind, version, base_profile_name)
        profile_name = self._default_nodeprofile_name(
            os_key, normalized_version, base_profile_name
        )
        profile_name = helpers.normalize_name(profile_name)

        spec = self._build_nodeprofile_spec(
            kind=kind,
            version=version,
            image=image,
            raw_labels=raw_labels,
            base_entry=base_entry,
        )

        if profile_name in self._nodeprofile_defs:
            existing = self._nodeprofile_defs[profile_name]
            if existing.get("spec") != spec:
                logger.warning(
                    "%sNodeProfile '%s' has conflicting specs; keeping first",
                    SUBSTEP_INDENT,
                    profile_name,
                )
            return profile_name

        self._nodeprofile_defs[profile_name] = {
            "apiVersion": "core.eda.nokia.com/v1",
            "kind": "NodeProfile",
            "metadata": {"name": profile_name, "namespace": self.namespace},
            "spec": spec,
        }
        return profile_name

    def _derive_node_profile(
        self, kind: str | None, version: str | None, _image: str | None
    ) -> str | None:
        if not kind or not version:
            return None
        normalized_version = self._normalize_version(kind, version)
        prefix = kind.replace("nokia_", "")
        if kind == "nokia_srlinux":
            prefix = "srlinux-ghcr"
        elif kind in {"nokia_sros", "nokia_srsim"}:
            prefix = "sros-ghcr"
        elif kind == "arista_ceos":
            prefix = "eos"
        return f"{prefix}-{normalized_version}"

    def _derive_platform(
        self, node_obj: Any, node_type: str | None, kind: str | None
    ) -> str:
        if node_obj is not None:
            try:
                return node_obj.get_platform()
            except Exception:  # noqa: BLE001
                logger.debug("Failed to derive platform via node object", exc_info=True)
        if node_type:
            return str(node_type)
        return str(kind or "UNKNOWN")

    def _parse_image_version(self, image: str | None) -> str | None:
        if not image:
            return None
        image_ref = image.split("@", 1)[0]
        last_colon = image_ref.rfind(":")
        last_slash = image_ref.rfind("/")
        if last_colon > last_slash:
            tag = image_ref[last_colon + 1 :]
            return tag.split("-", 1)[0]
        return None

    def _normalize_version(self, kind: str | None, version: str) -> str:
        normalized = str(version).strip()
        if kind in {"nokia_sros", "nokia_srsim"}:
            return normalized.lower().replace(".r", ".r")
        return normalized

    def _load_nodeprofiles(self) -> dict[str, dict[str, dict[str, Any]]]:
        profiles_by_name: dict[str, dict[str, Any]] = {}
        profiles_by_os_version: dict[str, dict[str, dict[str, Any]]] = {}
        try:
            items = list_nodeprofiles(self.namespace)
        except Exception:  # noqa: BLE001
            logger.warning(
                "%sFailed to load node profiles from EDA; using derived profiles",
                SUBSTEP_INDENT,
            )
            return {"by_name": profiles_by_name, "by_os_version": profiles_by_os_version}

        for item in items:
            spec = item.get("spec", {})
            os_key = str(spec.get("operatingSystem", "")).lower()
            version = str(spec.get("version", "")).lower()
            name = item.get("metadata", {}).get("name", "")
            if not os_key or not version or not name:
                continue
            entry = {"name": name, "spec": spec}
            profiles_by_name[name] = entry
            profiles_by_os_version.setdefault(os_key, {})[version] = entry
        return {"by_name": profiles_by_name, "by_os_version": profiles_by_os_version}

    def _resolve_nodeprofile(self, kind: str | None, version: str | None) -> str | None:
        if not self._nodeprofiles or not kind or not version:
            return None

        os_map = {
            "nokia_srlinux": "srl",
            "nokia_sros": "sros",
            "nokia_srsim": "sros",
            "arista_ceos": "eos",
        }
        os_key = os_map.get(kind)
        if not os_key:
            return None

        candidates = self._nodeprofiles.get("by_os_version", {}).get(os_key, {})
        if not candidates:
            return None

        normalized = self._normalize_version(kind, version).lower()
        if normalized in candidates:
            return candidates[normalized]["name"]

        logger.warning(
            "%sNodeProfile for %s version %s not found in %s; using available profile %s",
            SUBSTEP_INDENT,
            os_key,
            version,
            self.namespace,
            next(iter(candidates.values()))["name"],
        )
        return next(iter(candidates.values()))["name"]

    def _extract_endpoints(self, link: Any) -> list[str] | None:
        if isinstance(link, dict):
            if "endpoints" in link:
                endpoints = link.get("endpoints")
                return endpoints if isinstance(endpoints, list) else None
            if "a" in link and "z" in link:
                return [
                    self._endpoint_from_dict(link.get("a")),
                    self._endpoint_from_dict(link.get("z")),
                ]
            if "a" in link and "b" in link:
                return [
                    self._endpoint_from_dict(link.get("a")),
                    self._endpoint_from_dict(link.get("b")),
                ]
        if isinstance(link, list):
            return link
        return None

    def _endpoint_from_dict(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        node = data.get("node")
        interface = data.get("interface")
        if node and interface:
            return f"{node}:{interface}"
        return ""

    def _split_endpoint(self, endpoint: Any) -> tuple[str | None, str | None]:
        if isinstance(endpoint, dict):
            node = endpoint.get("node")
            interface = endpoint.get("interface")
            if node and interface:
                return str(node).strip(), str(interface).strip()
            return None, None
        if not isinstance(endpoint, str) or ":" not in endpoint:
            return None, None
        node, interface = endpoint.split(":", 1)
        return node.strip(), interface.strip()

    def _map_interface_name(self, node_info: dict[str, Any], ifname: str | None) -> str:
        if ifname is None:
            return ""
        if node_info.get("sim", False):
            return str(ifname)

        kind = node_info.get("kind")
        if kind == "nokia_srlinux":
            value = str(ifname).strip()
            match = re.match(r"^e(\d+)-(\d+)$", value)
            if match:
                return f"ethernet-{match.group(1)}/{match.group(2)}"
            match = re.match(r"^ethernet-(\d+)-(\d+)$", value)
            if match:
                return f"ethernet-{match.group(1)}/{match.group(2)}"
            if value.startswith("ethernet-") and "/" in value:
                return value
        if kind in {"nokia_sros", "nokia_srsim"}:
            value = str(ifname).strip()

            def mda_to_letter(mda_num: str) -> str:
                return chr(96 + int(mda_num))

            match = re.match(r"^(\d+)/(\d+)/(\d+)$", value)
            if match:
                slot, mda, port = match.groups()
                return f"ethernet-{slot}-{mda_to_letter(mda)}-{port}-1"
            match = re.match(r"^(\d+)/(\d+)/c(\d+)/(\d+)$", value)
            if match:
                slot, mda, card, port = match.groups()
                if card == "1":
                    return f"ethernet-{slot}-{card}-{port}"
                return f"ethernet-{slot}-{mda_to_letter(mda)}-{card}-{port}"
            match = re.match(r"^(\d+)/x(\d+)/(\d+)/c(\d+)/(\d+)$", value)
            if match:
                slot, xval, mda, card, port = match.groups()
                return (
                    f"ethernet-{slot}-{xval}-{mda_to_letter(mda)}-{card}-{port}"
                )

        node_obj = node_info.get("node_obj")
        if node_obj is not None:
            try:
                return node_obj.get_interface_name_for_kind(str(ifname))
            except Exception:  # noqa: BLE001
                logger.debug("Failed to map interface name via node object", exc_info=True)
        return str(ifname)

    def _label_value(self, labels: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        if not labels:
            return None
        for key in keys:
            if key in labels:
                value = str(labels[key]).strip()
                return value if value != "" else None
        lower_map = {str(k).lower(): k for k in labels.keys()}
        for key in keys:
            lookup = key.lower()
            if lookup in lower_map:
                value = str(labels[lower_map[lookup]]).strip()
                return value if value != "" else None
        return None

    def _build_template_labels(
        self,
        raw_labels: dict[str, Any],
        role_value: str | None,
        sec_profile: str | None,
        control_keys: set[str],
        default_security_profile: bool = True,
    ) -> dict[str, str]:
        labels: dict[str, Any] = {}
        control_keys_lower = {k.lower() for k in control_keys}

        if role_value:
            labels["eda.nokia.com/role"] = role_value

        if sec_profile:
            labels["eda.nokia.com/security-profile"] = sec_profile
        elif default_security_profile:
            labels["eda.nokia.com/security-profile"] = "managed"

        for key, value in raw_labels.items():
            if str(key).lower() in control_keys_lower:
                continue
            if key in {"eda.nokia.com/role", "eda.nokia.com/security-profile"}:
                continue
            if str(key).startswith("eda.nokia.com/"):
                labels[key] = value

        return helpers.sanitize_labels(labels)

    def _build_node_labels(
        self,
        raw_labels: dict[str, Any],
        role_value: str | None,
        sec_profile: str | None,
        control_keys: set[str],
    ) -> dict[str, str]:
        control_keys_lower = {k.lower() for k in control_keys}
        labels = {
            key: value
            for key, value in raw_labels.items()
            if str(key).lower() not in control_keys_lower
        }
        labels.pop("role", None)
        if role_value:
            labels["eda.nokia.com/role"] = role_value
        if sec_profile:
            labels.setdefault("eda.nokia.com/security-profile", sec_profile)
        return helpers.sanitize_labels(labels)

    def _normalize_link_type(self, link_type: str | None) -> str | None:
        if not link_type:
            return None
        value = str(link_type).strip().lower()
        if value in {"inter", "interswitch", "inter-switch", "inter_switch"}:
            return "interSwitch"
        if value in {"edge"}:
            return "edge"
        if value in {"loopback", "loop"}:
            return "loopback"
        return None

    def _warn_template_conflict(
        self, name: str, existing: dict[str, Any], new: dict[str, Any]
    ) -> None:
        for key in ("nodeProfile", "platform", "type", "labels", "speed", "encapType"):
            if existing.get(key) != new.get(key):
                logger.warning(
                    "%sTemplate '%s' has conflicting '%s' values; keeping first",
                    SUBSTEP_INDENT,
                    name,
                    key,
                )
                return

    def _warn_sim_template_conflict(
        self, name: str, existing: dict[str, Any], new: dict[str, Any]
    ) -> None:
        for key in ("type", "image"):
            if existing.get(key) != new.get(key):
                logger.warning(
                    "%sSimNodeTemplate '%s' has conflicting '%s' values; keeping first",
                    SUBSTEP_INDENT,
                    name,
                    key,
                )
                return

    def _resolve_output_path(self, topo_name: str) -> Path:
        if self.output:
            return self.output
        return Path(f"{topo_name}.network-topology.yaml")

    def _unique_name(self, base: str, used: set[str]) -> str:
        normalized = helpers.normalize_name(base)
        name = normalized
        idx = 1
        while name in used:
            idx += 1
            name = f"{normalized}-{idx}"
        if name != normalized:
            logger.warning(
                "%sName '%s' normalized to '%s' (adjusted for uniqueness)",
                SUBSTEP_INDENT,
                base,
                name,
            )
        used.add(name)
        return name
