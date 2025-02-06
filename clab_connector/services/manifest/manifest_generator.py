# clab_connector/services/manifest/manifest_generator.py

import os
import logging
from clab_connector.models.topology import parse_topology_file
from clab_connector.utils import helpers

logger = logging.getLogger(__name__)

class ManifestGenerator:
    """
    Generate YAML manifests (CR definitions) from a containerlab topology.
    The CRs include (if applicable):
      - Artifacts (grouped by artifact name)
      - Init
      - NodeSecurityProfile
      - NodeUserGroup
      - NodeUser
      - NodeProfiles
      - TopoNodes
      - Topolink Interfaces
      - Topolinks

    When the --separate option is used, the manifests are output as one file per category
    (e.g. artifacts.yaml, init.yaml, etc.). Otherwise all CRs are concatenated into one YAML file.
    """

    def __init__(self, topology_file: str, output: str = None, separate: bool = False):
        """
        Parameters
        ----------
        topology_file : str
            Path to the containerlab topology JSON file.
        output : str
            If separate is False: path to the combined output file.
            If separate is True: path to an output directory where each category file is written.
        separate : bool
            If True, generate separate YAML files per CR category.
            Otherwise, generate one combined YAML file.
        """
        self.topology_file = topology_file
        self.output = output
        self.separate = separate
        self.topology = None
        # Dictionary mapping category name to a list of YAML document strings.
        self.cr_groups = {}

    def generate(self):
        """Parse the topology and generate the CR YAML documents grouped by category."""
        self.topology = parse_topology_file(self.topology_file)
        namespace = f"clab-{self.topology.name}"
        logger.info(f"Generating manifests for namespace: {namespace}")

        # --- Artifacts: Group each unique artifact into one document per artifact.
        artifacts = []
        seen_artifacts = set()
        for node in self.topology.nodes:
            if not node.needs_artifact():
                continue
            artifact_name, filename, download_url = node.get_artifact_info()
            if not artifact_name or not filename or not download_url:
                logger.warning(f"No artifact info for node {node.name}; skipping.")
                continue
            if artifact_name in seen_artifacts:
                continue
            seen_artifacts.add(artifact_name)
            artifact_yaml = node.get_artifact_yaml(artifact_name, filename, download_url)
            if artifact_yaml:
                artifacts.append(artifact_yaml)
        if artifacts:
            self.cr_groups["artifacts"] = artifacts

        # --- Init resource
        init_yaml = helpers.render_template("init.yaml.j2", {"namespace": namespace})
        self.cr_groups["init"] = [init_yaml]

        # --- Node Security Profile
        nsp_yaml = helpers.render_template("nodesecurityprofile.yaml.j2", {"namespace": namespace})
        self.cr_groups["node-security-profile"] = [nsp_yaml]

        # --- Node User Group
        nug_yaml = helpers.render_template("node-user-group.yaml.j2", {"namespace": namespace})
        self.cr_groups["node-user-group"] = [nug_yaml]

        # --- Node User
        nu_yaml = helpers.render_template(
            "node-user.j2",
            {
                "namespace": namespace,
                "node_user": "admin",
                "username": "admin",
                "password": "NokiaSrl1!",
                "ssh_pub_keys": self.topology.ssh_pub_keys or [],
            },
        )
        self.cr_groups["node-user"] = [nu_yaml]

        # --- Node Profiles
        profiles = self.topology.get_node_profiles()
        if profiles:
            self.cr_groups["node-profiles"] = list(profiles)

        # --- TopoNodes
        toponodes = self.topology.get_toponodes()
        if toponodes:
            self.cr_groups["toponodes"] = list(toponodes)

        # --- Topolink Interfaces
        intfs = self.topology.get_topolink_interfaces()
        if intfs:
            self.cr_groups["topolink-interfaces"] = list(intfs)

        # --- Topolinks
        links = self.topology.get_topolinks()
        if links:
            self.cr_groups["topolinks"] = list(links)

        return self.cr_groups

    def output_manifests(self):
        """Output the generated CR YAML documents either as one combined file or as separate files per category."""
        if not self.cr_groups:
            logger.warning("No manifests were generated.")
            return

        if not self.separate:
            # One combined YAML file: concatenate all documents (across all groups) with separators.
            all_docs = []
            for category, docs in self.cr_groups.items():
                header = f"# --- {category.upper()} ---"
                all_docs.append(header)
                all_docs.extend(docs)
            combined = "\n---\n".join(all_docs)
            if self.output:
                with open(self.output, "w") as f:
                    f.write(combined)
                logger.info(f"Combined manifest written to {self.output}")
            else:
                print(combined)
        else:
            # Separate files per category: self.output must be a directory.
            output_dir = self.output or "manifests"
            os.makedirs(output_dir, exist_ok=True)
            for category, docs in self.cr_groups.items():
                combined = "\n---\n".join(docs)
                file_path = os.path.join(output_dir, f"{category}.yaml")
                with open(file_path, "w") as f:
                    f.write(combined)
                logger.info(f"Manifest for '{category}' written to {file_path}")
