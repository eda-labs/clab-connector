# clab_connector/services/integration/sros_post_integration.py

import logging
import subprocess
import time
import tempfile
import re
from pathlib import Path

logger = logging.getLogger(__name__)

def prepare_sros_node(node_name, namespace, version, mgmt_ip, username="admin", password="admin"):
    """
    Perform SROS-specific post-integration steps.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract TLS certificates and config
        cert_path = Path(temp_dir) / "edaboot.crt"
        key_path = Path(temp_dir) / "edaboot.key"
        config_path = Path(temp_dir) / "config.cfg"
        script_path = Path(temp_dir) / "sros_commands.txt"

        try:
            # Extract certificates from K8s secrets
            logger.info(f"Extracting TLS certificate for {node_name}")
            cert_cmd = f"kubectl get secret {namespace}--{node_name}-cert-tls -n eda-system -o jsonpath='{{.data.tls\\.crt}}' | base64 -d > {cert_path}"
            subprocess.check_call(cert_cmd, shell=True)

            logger.info(f"Extracting TLS key for {node_name}")
            key_cmd = f"kubectl get secret {namespace}--{node_name}-cert-tls -n eda-system -o jsonpath='{{.data.tls\\.key}}' | base64 -d > {key_path}"
            subprocess.check_call(key_cmd, shell=True)

            # Extract configuration
            logger.info(f"Extracting initial configuration for {node_name}")
            config_cmd = f"kubectl get artifact initcfg-{node_name}-{version} -n {namespace} -o jsonpath='{{.spec.textFile.content}}' | sed 's/\\\\n/\\n/g' > {config_path}"
            subprocess.check_call(config_cmd, shell=True)

            # Process the configuration - remove the outer "configure {" and "}"
            with open(config_path, 'r') as f:
                config_text = f.read()

            # Extract the inner content
            match = re.search(r'configure\s*\{(.*)\}', config_text, re.DOTALL)
            if not match:
                logger.warning("Could not extract inner configuration content")
                return False

            inner_config = match.group(1).strip()

            # Wait for node to be reachable
            logger.info(f"Waiting for {node_name} to be reachable...")
            max_retries = 30
            for i in range(max_retries):
                try:
                    subprocess.check_call(["ping", "-c", "1", "-W", "2", mgmt_ip],
                                         stdout=subprocess.DEVNULL)
                    logger.info(f"Node {node_name} is reachable")
                    break
                except subprocess.CalledProcessError:
                    logger.debug(f"Waiting for {node_name} to be reachable ({i+1}/{max_retries})")
                    time.sleep(5)
            else:
                logger.error(f"Timed out waiting for {node_name} to be reachable")
                return False

            # Allow additional time for SSH to start
            time.sleep(10)

            # Transfer certificates to the node
            logger.info(f"Transferring certificates to {node_name}")
            subprocess.check_call([
                "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                str(cert_path), f"{username}@{mgmt_ip}:/cf3:/"
            ])

            subprocess.check_call([
                "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                str(key_path), f"{username}@{mgmt_ip}:/cf3:/"
            ])

            # Create a simple script with all commands
            with open(script_path, "w") as f:
                # Certificate import commands
                f.write("admin system security pki import type certificate input-url cf3:/edaboot.crt output-file edaboot.crt format pem\n")
                f.write("admin system security pki import type key input-url cf3:/edaboot.key output-file edaboot.key format pem\n")

                # Configure commands
                f.write("configure global\n")
                f.write(inner_config + "\n")  # Add the inner configuration directly
                f.write("commit\n")
                f.write("exit all\n")

            # Transfer and execute the script on the SROS node
            subprocess.check_call([
                "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                str(script_path), f"{username}@{mgmt_ip}:/cf3:/commands.txt"
            ])

            # Execute the commands
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{mgmt_ip} < {script_path}"
            subprocess.check_call(ssh_cmd, shell=True)

            logger.info(f"SROS node {node_name} successfully configured")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Error during SROS post-integration: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during SROS post-integration: {e}")
            return False