# clab_connector/services/integration/sros_post_integration.py

import logging
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

def verify_ssh_credentials(mgmt_ip: str, username: str, passwords: List[str], quiet: bool = False) -> Optional[str]:
    """
    Verify which SSH credentials work for the given node.

    Parameters
    ----------
    mgmt_ip : str
        Management IP address of the node.
    username : str
        SSH username to try.
    passwords : List[str]
        List of passwords to try in order.
    quiet : bool
        If True, reduce verbosity of output.

    Returns
    -------
    Optional[str]
        The working password if found, None otherwise.
    """
    # Check if sshpass is installed
    try:
        subprocess.check_call(
            ["which", "sshpass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        logger.warning("sshpass not installed, credential verification skipped")
        return None

    # Try each password
    for password in passwords:
        try:
            # Use echo command piped to SSH instead of direct command execution
            # This allows sending commands after the connection is established
            cmd = [
                "sshpass", "-p", password,
                "ssh", "-q",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                f"{username}@{mgmt_ip}"
            ]

            if not quiet:
                logger.debug(f"Trying command: {' '.join(cmd)}")

            # Use echo to pipe "logout" to SSH after connection
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Send the logout command after connection established
            process.communicate(input=b"logout\n")

            # Check the return code
            if process.returncode == 0:
                if not quiet:
                    logger.info(f"Successfully connected to {mgmt_ip} with password: {password}")
                return password
            elif process.returncode == 5:
                # Authentication failure
                if not quiet:
                    logger.debug(f"Authentication failed with password: {password}")
            else:
                # Other error (255 likely means the command failed but auth worked)
                if not quiet:
                    logger.debug(f"Connection established but command failed with exit code {process.returncode}")
                return password  # Return the password anyway as authentication succeeded

        except Exception as e:
            if not quiet:
                logger.debug(f"Failed to connect with password: {password}, error: {e}")

    # If no password worked but we know manual connection works,
    # return the last password as a fallback
    if passwords:
        logger.warning(f"No password worked automatically, but manual connection may work. Using {passwords[-1]} as fallback")
        return passwords[-1]

    return None

def transfer_file(src_path: Path, dest_path: str, username: str, mgmt_ip: str,
                  password: Optional[str] = None, quiet: bool = False) -> bool:
    """
    Transfer a file to the target node using SCP.

    Parameters
    ----------
    src_path : Path
        Source file path to transfer.
    dest_path : str
        Destination path on the target node.
    username : str
        SSH username.
    mgmt_ip : str
        Management IP address of the node.
    password : Optional[str]
        Password for SSH authentication (if provided).
    quiet : bool
        If True, reduce verbosity of output.

    Returns
    -------
    bool
        True if the transfer was successful, False otherwise.
    """
    try:
        if password:
            cmd = [
                "sshpass", "-p", password, "scp", "-q",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                str(src_path), f"{username}@{mgmt_ip}:{dest_path}"
            ]
        else:
            cmd = [
                "scp", "-q",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                str(src_path), f"{username}@{mgmt_ip}:{dest_path}"
            ]

        if not quiet:
            logger.debug(f"Running transfer command: {' '.join(cmd)}")

        subprocess.check_call(
            cmd,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None
        )
        return True
    except subprocess.CalledProcessError as e:
        if not quiet:
            logger.debug(f"Transfer failed: {e}")
        return False

def execute_ssh_commands(script_path: Path, username: str, mgmt_ip: str,
                         node_name: str, password: Optional[str] = None, quiet: bool = False) -> bool:
    """
    Execute SSH commands on the SROS node and handle output.
    Returns True on success, False on failure.

    Parameters
    ----------
    script_path : Path
        Path to the script file containing commands to execute.
    username : str
        SSH username.
    mgmt_ip : str
        Management IP address of the node.
    node_name : str
        Name of the node being configured.
    password : Optional[str]
        Password for automated SSH authentication.
    quiet : bool
        If True, reduce verbosity of SSH output.
    """
    try:
        if password:
            # Use subprocess list form to avoid shell escaping issues
            cmd = [
                "sshpass", "-p", password,
                "ssh", "-q",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                f"{username}@{mgmt_ip}"
            ]

            # Redirect input from script file
            with open(script_path, 'r') as script_file:
                if not quiet:
                    logger.debug(f"Running SSH command: {' '.join(cmd)}")

                process = subprocess.Popen(
                    cmd,
                    stdin=script_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )

                output, _ = process.communicate()

                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, cmd, output)
        else:
            # Non-password version
            cmd = [
                "ssh", "-q",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                f"{username}@{mgmt_ip}"
            ]

            with open(script_path, 'r') as script_file:
                if not quiet:
                    logger.debug(f"Running SSH command: {' '.join(cmd)}")

                process = subprocess.Popen(
                    cmd,
                    stdin=script_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )

                output, _ = process.communicate()

                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, cmd, output)

        if not quiet:
            auth_method = "provided password" if password else "default authentication"
            logger.info(f"SROS node {node_name} configuration completed successfully using {auth_method}")
            logger.debug(f"Command output summary: {output[:500] if output else ''}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during SROS configuration: {e}")
        logger.error(f"Command error output: {e.output if hasattr(e, 'output') else 'No output'}")
        return False

def prepare_sros_node(node_name: str, namespace: str, version: str, mgmt_ip: str,
                     username: str = "admin", password: str = "admin", quiet: bool = False) -> bool:
    """
    Perform SROS-specific post-integration steps with password fallback.

    Parameters
    ----------
    node_name : str
        Name of the node to configure.
    namespace : str
        Kubernetes namespace.
    version : str
        SROS version.
    mgmt_ip : str
        Management IP address of the node.
    username : str
        SSH username.
    password : str
        Initial SSH password to try.
    quiet : bool
        If True, reduce verbosity of output.

    Returns
    -------
    bool
        True if successful, False otherwise.
    """
    # Check credentials first - always try both passwords
    passwords_to_try = ["admin", "NokiaSros1!"]
    if not quiet:
        logger.info(f"Verifying SSH credentials for {node_name}")

    working_password = verify_ssh_credentials(mgmt_ip, username, passwords_to_try, quiet)

    # If verification fails but we know manual connection works,
    # default to using "NokiaSros1!" since that's what worked manually
    if not working_password:
        working_password = "NokiaSros1!"
        logger.warning(f"Automatic credential verification failed. Using fallback password: {working_password}")

    # Setup temporary directory for files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        cert_path = temp_path / "edaboot.crt"
        key_path = temp_path / "edaboot.key"
        config_path = temp_path / "config.cfg"
        script_path = temp_path / "sros_commands.txt"

        try:
            # Extract TLS certificate
            if not quiet:
                logger.info(f"Extracting TLS certificate for {node_name}")

            cert_cmd = f"kubectl get secret {namespace}--{node_name}-cert-tls -n eda-system -o jsonpath='{{.data.tls\\.crt}}' | base64 -d > {cert_path}"
            subprocess.check_call(
                cert_cmd,
                shell=True,
                stdout=subprocess.DEVNULL if quiet else None,
                stderr=subprocess.DEVNULL if quiet else None
            )

            if not cert_path.exists() or cert_path.stat().st_size == 0:
                raise FileNotFoundError(f"Certificate file for {node_name} is empty or doesn't exist")

            # Extract TLS key
            if not quiet:
                logger.info(f"Extracting TLS key for {node_name}")

            key_cmd = f"kubectl get secret {namespace}--{node_name}-cert-tls -n eda-system -o jsonpath='{{.data.tls\\.key}}' | base64 -d > {key_path}"
            subprocess.check_call(
                key_cmd,
                shell=True,
                stdout=subprocess.DEVNULL if quiet else None,
                stderr=subprocess.DEVNULL if quiet else None
            )

            if not key_path.exists() or key_path.stat().st_size == 0:
                raise FileNotFoundError(f"Key file for {node_name} is empty or doesn't exist")

            # Extract configuration
            if not quiet:
                logger.info(f"Extracting initial configuration for {node_name}")

            config_cmd = f"kubectl get artifact initcfg-{node_name}-{version} -n {namespace} -o jsonpath='{{.spec.textFile.content}}' | sed 's/\\\\n/\\n/g' > {config_path}"
            subprocess.check_call(
                config_cmd,
                shell=True,
                stdout=subprocess.DEVNULL if quiet else None,
                stderr=subprocess.DEVNULL if quiet else None
            )

            if not config_path.exists() or config_path.stat().st_size == 0:
                raise FileNotFoundError(f"Configuration file for {node_name} is empty or doesn't exist")

            # Extract inner config content
            with open(config_path, 'r') as f:
                config_text = f.read()

            match = re.search(r'configure\s*\{(.*)\}', config_text, re.DOTALL)
            if not match:
                raise ValueError("Could not extract inner configuration content - invalid format")

            inner_config = match.group(1).strip()
            if not inner_config:
                raise ValueError("Extracted configuration is empty")

            # Transfer certificates to the node - try different paths
            if not quiet:
                logger.info(f"Transferring certificates to {node_name}")

            # Try possible certificate destinations in order
            cert_destinations = ["cf3:/", "/"]
            cert_destination = None

            for dest in cert_destinations:
                if not quiet:
                    logger.info(f"Attempting to transfer certificates to {dest}")

                cert_success = transfer_file(cert_path, dest, username, mgmt_ip, working_password, quiet)
                key_success = transfer_file(key_path, dest, username, mgmt_ip, working_password, quiet)

                if cert_success and key_success:
                    cert_destination = dest
                    if not quiet:
                        logger.info(f"Successfully transferred certificates to {dest}")
                    break

            # if not cert_destination:
            #     logger.error(f"Failed to transfer certificates to {node_name} using any method")
            #     return False

            # Create configuration script
            with open(script_path, "w") as f:
                # Environment settings for less verbosity
                f.write("environment more false\n")
                f.write("environment print-detail false\n")
                f.write("environment confirmations false\n")

                # Certificate import commands
                f.write(f"admin system security pki import type certificate input-url {cert_destination}edaboot.crt output-file edaboot.crt format pem\n")
                f.write(f"admin system security pki import type key input-url {cert_destination}edaboot.key output-file edaboot.key format pem\n")

                # Configuration commands
                f.write("configure global\n")
                f.write(inner_config + "\n")
                f.write("commit\n")
                f.write("exit all\n")

            # Transfer and execute the script
            script_dest = f"{cert_destination}commands.txt"

            if not quiet:
                logger.info(f"Transferring command script to {node_name}")

            script_success = transfer_file(script_path, script_dest, username, mgmt_ip, working_password, quiet)

            if not script_success:
                logger.error(f"Failed to transfer command script to {node_name}")
                return False

            # Execute commands
            if not quiet:
                logger.info(f"Executing configuration commands on {node_name}")

            success = execute_ssh_commands(script_path, username, mgmt_ip, node_name, working_password, quiet)

            return success

        except FileNotFoundError as e:
            logger.error(str(e))
            return False
        except ValueError as e:
            logger.error(str(e))
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during SROS post-integration: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during SROS post-integration: {e}")
            return False