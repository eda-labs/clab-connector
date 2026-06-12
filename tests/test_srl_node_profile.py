import yaml

from clab_connector.models.topology import parse_topology_file


def test_srl_node_profile_uses_topology_image_for_container_image(tmp_path):
    topology_data = tmp_path / "topology-data.json"
    topology_data.write_text(
        """
{
  "type": "clab",
  "name": "srl-lab",
  "clab": {
    "config": {
      "mgmt": {
        "ipv4-subnet": "172.20.20.0/24",
        "ipv4-gw": "172.20.20.1"
      }
    }
  },
  "ssh-pub-keys": [],
  "nodes": {
    "leaf1": {
      "kind": "nokia_srlinux",
      "image": "ghcr.io/nokia/srlinux:25.10.3",
      "mgmt-ipv4-address": "172.20.20.2",
      "mgmt-ipv4-prefix-length": "24",
      "labels": {
        "clab-topo-file": "srl.clab.yml",
        "clab-node-type": "ixr-d3l"
      }
    }
  },
  "links": []
}
""".strip(),
        encoding="utf-8",
    )

    topology = parse_topology_file(str(topology_data))
    profiles = list(topology.get_node_profiles())

    assert len(profiles) == 1
    profile = yaml.safe_load(profiles[0])

    assert profile["spec"]["license"] == "cx-srl-25-10-3-ghcr-license"
    assert profile["spec"]["imagePullSecret"] == "core"
    assert profile["spec"]["containerImage"] == "ghcr.io/nokia/srlinux:25.10.3"
