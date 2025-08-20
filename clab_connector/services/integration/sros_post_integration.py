#!/usr/bin/env python3
"""sros_post_integration.py - SROS post-integration helpers"""

from __future__ import annotations

import contextlib
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

import paramiko

logger = logging.getLogger(__name__)

# Default retry parameters
RETRIES = 20
DELAY = 2.0


def _run_with_retry(cmd: str, quiet: bool, retries: int = RETRIES, delay: float = DELAY) -> None:
    """Run a shell command with retries."""
    for attempt in range(retries):
        suppress_stderr = quiet or (attempt < retries - 1)
        try:
            subprocess.check_call(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL if quiet else None,
                stderr=subprocess.DEVNULL if suppress_stderr else None,
            )
            if attempt > 0:
                logger.info("Command succeeded on attempt %s/%s", attempt + 1, retries)
            return
        except subprocess.CalledProcessError:
            if attempt == retries - 1:
                logger.error("Command failed after %s attempts: %s", retries, cmd)
                raise
            logger.warning(
                "Command failed (attempt %s/%s), retrying in %ss...",
                attempt + 1,
                retries,
                delay,
            )
            time.sleep(delay)


# --------------------------------------------------------------------------- #
# SSH helpers                                                                 #
# --------------------------------------------------------------------------- #
def verify_ssh_credentials(
    mgmt_ip: str,
    username: str,
    passwords: list[str],
    quiet: bool = False,
) -> str | None:
    """
    Return the first password that opens an SSH session, else None.
    """
    for pw in passwords:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if not quiet:
                logger.debug(
                    "Trying SSH to %s with user '%s' and password '%s'",
                    mgmt_ip,
                    username,
                    pw,
                )

            client.connect(
                hostname=mgmt_ip,
                port=22,
                username=username,
                password=pw,
                timeout=10,
                banner_timeout=10,
                allow_agent=False,
                look_for_keys=False,
            )

            # If we reach this point authentication succeeded.
            if not quiet:
                logger.info("Password '%s' works for %s", pw, mgmt_ip)
            return pw

        except paramiko.AuthenticationException:
            if not quiet:
                logger.debug("Password '%s' rejected for %s", pw, mgmt_ip)
        except (TimeoutError, OSError, paramiko.SSHException) as e:
            if not quiet:
                logger.debug("SSH connection problem with %s: %s", mgmt_ip, e)
        finally:
            with contextlib.suppress(Exception):
                client.close()

    return None


def transfer_file(
    src_path: Path,
    dest_path: str,
    username: str,
    mgmt_ip: str,
    password: str,
    quiet: bool = False,
) -> bool:
    """
    SCP file to the target node using Paramiko SFTP.
    """
    try:
        if not quiet:
            logger.debug("SCP %s → %s@%s:%s", src_path, username, mgmt_ip, dest_path)

        transport = paramiko.Transport((mgmt_ip, 22))
        transport.connect(username=username, password=password)

        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(str(src_path), dest_path)
        sftp.close()
        transport.close()
        return True
    except Exception as e:
        if not quiet:
            logger.debug("SCP failed: %s", e)
        return False


def execute_ssh_commands(
    script_path: Path,
    username: str,
    mgmt_ip: str,
    node_name: str,
    password: str,
    quiet: bool = False,
) -> bool:
    """
    Push the command file line-by-line over an interactive shell.
    No timeouts version that will wait as long as needed for each command.
    """
    try:
        commands = script_path.read_text().splitlines()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=mgmt_ip,
            username=username,
            password=password,
            allow_agent=False,
            look_for_keys=False,
        )

        chan = client.invoke_shell()
        output = []

        for cmd in commands:
            if cmd.strip() == "commit":
                time.sleep(2)  # Wait 2 seconds before sending commit

            chan.send(cmd + "\n")
            while not chan.recv_ready():
                pass

            buffer = ""
            while chan.recv_ready():
                buffer += chan.recv(4096).decode()
            output.append(buffer)

        # Get any remaining output
        while chan.recv_ready():
            output.append(chan.recv(4096).decode())

        chan.close()
        client.close()

        if not quiet:
            logger.info(
                "Configuration of %s completed (output %d chars)",
                node_name,
                sum(map(len, output)),
            )
        return True
    except Exception as e:
        logger.error("SSH exec error on %s: %s", node_name, e)
        return False


# --------------------------------------------------------------------------- #
# Helper utilities                                                            #
# --------------------------------------------------------------------------- #
def _extract_file(cmd: str, path: Path, desc: str, quiet: bool) -> int:
    """Run `cmd` until `path` exists and is non-empty."""
    for attempt in range(RETRIES):
        _run_with_retry(cmd, quiet, retries=1)
        size = path.stat().st_size if path.exists() else 0
        if size > 0:
            if attempt > 0:
                logger.info("%s extraction succeeded on attempt %s/%s", desc, attempt + 1, RETRIES)
            logger.info("%s file size: %s bytes", desc, size)
            return size
        if attempt == RETRIES - 1:
            raise ValueError(f"{desc} file is empty after extraction")
        logger.warning("%s file empty (attempt %s/%s), re-extracting...", desc, attempt + 1, RETRIES)
        time.sleep(DELAY)


def _extract_config(cmd: str, path: Path, quiet: bool) -> str:
    """Extract a config file and return the inner configure block."""
    for attempt in range(RETRIES):
        _run_with_retry(cmd, quiet, retries=1)
        cfg_text = path.read_text() if path.exists() else ""
        if not cfg_text.strip():
            if attempt == RETRIES - 1:
                raise ValueError("Config file is empty after extraction")
            logger.warning("Config file empty (attempt %s/%s), re-extracting...", attempt + 1, RETRIES)
            time.sleep(DELAY)
            continue
        match = re.search(r"configure\s*\{(.*)\}", cfg_text, re.DOTALL)
        if match and match.group(1).strip():
            if attempt > 0:
                logger.info("Config extraction succeeded on attempt %s/%s", attempt + 1, RETRIES)
            return match.group(1).strip()
        if attempt == RETRIES - 1:
            raise ValueError("Could not find inner config block")
        logger.warning("Config block not found (attempt %s/%s), re-extracting...", attempt + 1, RETRIES)
        time.sleep(DELAY)


def _extract_cert_and_config(
    node_name: str,
    namespace: str,
    version: str,
    cert_p: Path,
    key_p: Path,
    cfg_p: Path,
    quiet: bool,
) -> str:
    logger.info("Extracting TLS cert / key …")

    # Extract cert and key with retries and validation
    cert_cmd = (
        f"kubectl get secret {namespace}--{node_name}-cert-tls "
        f"-n eda-system -o jsonpath='{{.data.tls\\.crt}}' "
        f"| base64 -d > {cert_p}"
    )
    key_cmd = (
        f"kubectl get secret {namespace}--{node_name}-cert-tls "
        f"-n eda-system -o jsonpath='{{.data.tls\\.key}}' "
        f"| base64 -d > {key_p}"
    )
    
    _extract_file(cert_cmd, cert_p, "Certificate", quiet)
    _extract_file(key_cmd, key_p, "Private key", quiet)

    logger.info("Extracting initial config …")

    # Extract and parse config with retries
    extract_cmd = (
        f"kubectl get artifact initcfg-{node_name}-{version} -n {namespace} "
        f"-o jsonpath='{{.spec.textFile.content}}' "
        f"| sed 's/\\n/\\n/g' > {cfg_p}"
    )
    
    return _extract_config(extract_cmd, cfg_p, quiet)

def _copy_certificates(
    dest_roots: tuple[str, str],
    cert_p: Path,
    key_p: Path,
    username: str,
    mgmt_ip: str,
    working_pw: str,
    quiet: bool,
) -> str:
    logger.info("Copying certificates to device …")
    
    for root in dest_roots:
        logger.info(f"Attempting to copy certificates to root: {root}")
        
        cert_success = transfer_file(
            cert_p, root + "edaboot.crt", username, mgmt_ip, working_pw, quiet
        )
        if cert_success:
            logger.info(f"Certificate copied successfully to {root}edaboot.crt")
        else:
            logger.warning(f"Failed to copy certificate to {root}edaboot.crt")
            continue
            
        key_success = transfer_file(
            key_p, root + "edaboot.key", username, mgmt_ip, working_pw, quiet
        )
        if key_success:
            logger.info(f"Private key copied successfully to {root}edaboot.key")
            logger.info(f"Both certificate files copied successfully using root: {root}")
            return root
        else:
            logger.warning(f"Failed to copy private key to {root}edaboot.key")
    
    raise RuntimeError("Failed to copy certificate/key to device")


def _build_command_script(script_p: Path, dest_root: str, inner_cfg: str) -> None:
    with script_p.open("w") as f:
        f.write("environment more false\n")
        f.write("environment print-detail false\n")
        f.write("environment confirmations false\n")
        f.write(
            f"admin system security pki import type certificate input-url {dest_root}edaboot.crt output-file edaboot.crt format pem\n"
        )
        f.write(
            f"admin system security pki import type key input-url {dest_root}edaboot.key output-file edaboot.key format pem\n"
        )
        f.write("configure global\n")
        f.write(inner_cfg + "\n")
        f.write("commit\n")
        f.write("exit all\n")


# --------------------------------------------------------------------------- #
# High-level workflow                                                         #
# --------------------------------------------------------------------------- #
def prepare_sros_node(
    node_name: str,
    namespace: str,
    version: str,
    mgmt_ip: str,
    node_type: str,
    username: str = "admin",
    password: str | None = None,
    quiet: bool = True,
) -> bool:
    """
    Perform SROS-specific post-integration steps.
    """
    # First check if we can login with admin:admin
    # If we can't, assume the node is already bootstrapped
    admin_pwd = "admin" if node_type == "nokia_sros" else "NokiaSros1!"
    can_login = verify_ssh_credentials(mgmt_ip, username, [admin_pwd], quiet)

    if not can_login and node_type == "nokia_sros":
        logger.info("Node: %s already bootstrapped", node_name)
        return True
    if not can_login:
        logger.error("Can't login to node %s of kind %s", node_name, node_type)

    # Proceed with original logic if admin:admin works
    # 1. determine password list (keep provided one first if present)
    pwd_list: list[str] = []
    if password:
        pwd_list.append(password)
    pwd_list.append("admin")

    logger.info("Verifying SSH credentials for %s ...", node_name)
    working_pw = verify_ssh_credentials(mgmt_ip, username, pwd_list, quiet)

    if not working_pw:
        logger.error("No valid password found - aborting")
        return False
    # 2. create temp artefacts
    with tempfile.TemporaryDirectory() as tdir:
        tdir_path = Path(tdir)
        cert_p = tdir_path / "edaboot.crt"
        key_p = tdir_path / "edaboot.key"
        cfg_p = tdir_path / "config.cfg"
        script_p = tdir_path / "sros_commands.txt"

        try:
            inner_cfg = _extract_cert_and_config(
                node_name, namespace, version, cert_p, key_p, cfg_p, quiet
            )
            dest_root = _copy_certificates(
                ("cf3:/", "/"), cert_p, key_p, username, mgmt_ip, working_pw, quiet
            )
            _build_command_script(script_p, dest_root, inner_cfg)

            logger.info("Pushing configuration to %s …", node_name)
            return execute_ssh_commands(
                script_p, username, mgmt_ip, node_name, working_pw, quiet
            )

        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            ValueError,
            RuntimeError,
        ) as e:
            logger.error("Post-integration failed: %s", e)
            return False
        except Exception as e:
            logger.exception("Unexpected error: %s", e)
            return False
