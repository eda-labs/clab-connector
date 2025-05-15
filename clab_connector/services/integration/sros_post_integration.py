# clab_connector/services/integration/sros_post_integration.py

import logging
import subprocess
import tempfile
import re
from pathlib import Path

logger = logging.getLogger(__name__)

def execute_ssh_commands(script_path, username, mgmt_ip, node_name):
    """
    Execute SSH commands on the SROS node and handle output.
    Returns True on success, False on failure.
    """
    ssh_cmd = f"ssh -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{mgmt_ip} < {script_path} 2>&1 | grep -v '^\\['"
    try:
        output = subprocess.check_output(ssh_cmd, shell=True, stderr=subprocess.STDOUT)
        logger.info(f"SROS node {node_name} configuration completed successfully")
        logger.debug(f"Command output summary: {output[:500]}...")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during SROS configuration: {e}")
        logger.error(f"Command error output: {e.output}")
        return False

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

            # Transfer certificates to the node with fallback mechanism
            logger.info(f"Attempting to transfer certificates to {node_name}")
            cert_destination = None

            # Try with cf3:/ first
            try:
                logger.info("Trying to transfer certificates to cf3:/")
                subprocess.check_call([
                    "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                    str(cert_path), f"{username}@{mgmt_ip}:/cf3:/"
                ])

                subprocess.check_call([
                    "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                    str(key_path), f"{username}@{mgmt_ip}:/cf3:/"
                ])
                cert_destination = "cf3:/"
                logger.info("Successfully transferred certificates to cf3:/")
            except subprocess.CalledProcessError:
                # Fall back to root path
                logger.info("Falling back to transferring certificates to root path")
                try:
                    subprocess.check_call([
                        "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                        str(cert_path), f"{username}@{mgmt_ip}:/"
                    ])

                    subprocess.check_call([
                        "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                        str(key_path), f"{username}@{mgmt_ip}:/"
                    ])
                    cert_destination = "/"
                    logger.info("Successfully transferred certificates to root path")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to transfer certificates to {node_name}: {e}")
                    return False

            # Create a simple script with all commands - add silent mode options
            with open(script_path, "w") as f:
                # Configure environment to reduce output verbosity
                f.write("environment more false\n")  # Disable paging
                f.write("environment print-detail false\n")  # Reduce command output detail
                f.write("environment confirmations false\n")  # Disable confirmations

                # Certificate import commands based on where we successfully copied the files
                if cert_destination == "cf3:/":
                    f.write("admin system security pki import type certificate input-url cf3:/edaboot.crt output-file edaboot.crt format pem\n")
                    f.write("admin system security pki import type key input-url cf3:/edaboot.key output-file edaboot.key format pem\n")
                else:
                    f.write("admin system security pki import type certificate input-url /edaboot.crt output-file edaboot.crt format pem\n")
                    f.write("admin system security pki import type key input-url /edaboot.key output-file edaboot.key format pem\n")

                # Configure commands in a less verbose way
                f.write("configure global\n")
                f.write(inner_config + "\n")  # Add the inner configuration directly
                f.write("commit\n")
                f.write("exit all\n")

            # Transfer and execute the script on the SROS node - use same path that worked for certificates
            if cert_destination == "cf3:/":
                script_dest = f"{username}@{mgmt_ip}:/cf3:/commands.txt"
            else:
                script_dest = f"{username}@{mgmt_ip}:/commands.txt"

            subprocess.check_call([
                "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                str(script_path), script_dest
            ])

            # Execute the commands using helper function to reduce nesting
            return execute_ssh_commands(script_path, username, mgmt_ip, node_name)

        except subprocess.CalledProcessError as e:
            logger.error(f"Error during SROS post-integration: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during SROS post-integration: {e}")
            return False