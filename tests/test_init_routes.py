from types import SimpleNamespace

import yaml

from clab_connector.services.integration.topology_integrator import TopologyIntegrator
from clab_connector.services.manifest import manifest_generator as manifest_module
from clab_connector.services.manifest.manifest_generator import ManifestGenerator


class FakeEDAClient:
    def __init__(self):
        self.resources = []

    def add_replace_to_transaction(self, resource_yaml):
        resource = yaml.safe_load(resource_yaml)
        self.resources.append(resource)
        return resource

    @staticmethod
    def is_transaction_item_valid(_item):
        return True


class FakeTopology:
    def __init__(self, mgmt_ipv4_gw="172.20.20.1"):
        self.name = "clos01"
        self.namespace = "clab-clos01"
        self.namespace_overridden = False
        self.mgmt_ipv4_gw = mgmt_ipv4_gw
        self.ssh_pub_keys = []
        self.nodes = []

    @staticmethod
    def get_node_profiles():
        return []

    @staticmethod
    def get_toponodes():
        return []

    @staticmethod
    def get_topolink_interfaces(*_args, **_kwargs):
        return []

    @staticmethod
    def get_topolinks(*_args, **_kwargs):
        return []


def init_resources_by_name(init_resources):
    return {
        resource["metadata"]["name"]: resource
        for resource in (yaml.safe_load(item) for item in init_resources)
    }


def test_create_init_adds_mgmt_default_route_to_all_init_resources():
    eda_client = FakeEDAClient()
    integrator = TopologyIntegrator(eda_client)
    integrator.topology = SimpleNamespace(
        namespace="clab-clos01",
        mgmt_ipv4_gw="172.20.20.1",
    )

    integrator.create_init()

    resources = {item["metadata"]["name"]: item for item in eda_client.resources}
    assert set(resources) == {"init-base", "init-base-ceos"}
    for resource in resources.values():
        assert resource["spec"]["mgmt"]["staticRoutes"] == [
            {"nextHop": "172.20.20.1", "prefix": "0.0.0.0/0"}
        ]


def test_manifest_generator_adds_mgmt_default_route_to_init_base(monkeypatch):
    monkeypatch.setattr(
        manifest_module,
        "parse_topology_file",
        lambda *_args, **_kwargs: FakeTopology(),
    )

    generator = ManifestGenerator("dummy.json")
    cr_groups = generator.generate()

    resources = init_resources_by_name(cr_groups["init"])
    assert resources["init-base"]["spec"]["mgmt"]["staticRoutes"] == [
        {"nextHop": "172.20.20.1", "prefix": "0.0.0.0/0"}
    ]
    assert resources["init-base-ceos"]["spec"]["mgmt"]["staticRoutes"] == [
        {"nextHop": "172.20.20.1", "prefix": "0.0.0.0/0"}
    ]


def test_manifest_generator_keeps_empty_static_routes_without_gateway(monkeypatch):
    monkeypatch.setattr(
        manifest_module,
        "parse_topology_file",
        lambda *_args, **_kwargs: FakeTopology(mgmt_ipv4_gw=None),
    )

    generator = ManifestGenerator("dummy.json")
    cr_groups = generator.generate()

    resources = [yaml.safe_load(item) for item in cr_groups["init"]]
    assert all(resource["spec"]["mgmt"]["staticRoutes"] == [] for resource in resources)
