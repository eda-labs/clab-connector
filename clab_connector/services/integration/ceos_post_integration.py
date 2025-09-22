#!/usr/bin/env python3
"""ceos_post_integration.py - Arista cEOS post-integration helpers"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import tempfile
import time
from pathlib import Path

import paramiko

logger = logging.getLogger(__name__)

# Default retry parameters
RETRIES = 20
DELAY = 2.0


def _run_with_retry(
    cmd: str, quiet: bool, retries: int = RETRIES, delay: float = DELAY
) -> None:
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

        time.sleep(2)

        for cmd in commands:
            chan.send(cmd + "\n")

            time.sleep(0.5)

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
            logger.debug("Output: %s", output)
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
                logger.info(
                    "%s extraction succeeded on attempt %s/%s",
                    desc,
                    attempt + 1,
                    RETRIES,
                )
            logger.info("%s file size: %s bytes", desc, size)
            return size
        if attempt == RETRIES - 1:
            raise ValueError(f"{desc} file is empty after extraction")
        logger.warning(
            "%s file empty (attempt %s/%s), re-extracting...",
            desc,
            attempt + 1,
            RETRIES,
        )
        time.sleep(DELAY)


def _extract_cert_and_config(
    node_name: str,
    namespace: str,
    version: str,
    cert_p: Path,
    key_p: Path,
    cfg_p: Path,
    quiet: bool,
):
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

    _extract_file(extract_cmd, cfg_p, "Startup-config", quiet)


def _copy_files_and_config(
    dest_roots: tuple[str, str],
    cert_p: Path,
    key_p: Path,
    postscript_p: Path,
    config_p: Path,
    username: str,
    mgmt_ip: str,
    working_pw: str,
    quiet: bool,
) -> str:
    logger.info("Copying files to device …")

    for root in dest_roots:
        logger.info(f"Attempting to copy files to root: {root}")

        cfg_success = transfer_file(
            config_p, root + "startup-config", username, mgmt_ip, working_pw, quiet
        )
        if cfg_success:
            logger.info(f"Config copied successfully to {root}startup-config")
        else:
            logger.warning(f"Failed to copy config to {root}startup-config")
            continue

        _build_post_script(postscript_p, root)
        post_success = transfer_file(
            postscript_p, root + "copy_certs.sh", username, mgmt_ip, working_pw, quiet
        )
        if post_success:
            logger.info(f"Post script copied successfully to {root}copy_certs.sh")
        else:
            logger.warning(f"Failed to copy post script to {root}copy_certs.sh")
            continue

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
            logger.info(f"All files copied successfully using root: {root}")
            return root
        else:
            logger.warning(f"Failed to copy private key to {root}edaboot.key")

    raise RuntimeError("Failed to copy files to device")


def _build_enable_scp_script(script_p: Path) -> None:
    with script_p.open("w") as f:
        f.write("enable\n")
        f.write("configure terminal\n")
        f.write("aaa authorization exec default local\n")
        f.write("exit\n")
        f.write("write\n")


def _build_command_script(script_p: Path, dest_root: str) -> None:
    with script_p.open("w") as f:
        f.write("enable\n")
        f.write("configure replace startup-config ignore-errors\n")
        f.write(f"copy file:{dest_root}edaboot.crt certificate:\n")
        f.write(f"copy file:{dest_root}edaboot.key sslkey:\n")
        f.write("configure terminal\n")
        f.write("management api gnmi\n")
        f.write("    transport grpc discovery\n")
        f.write("    ssl profile edaboot\n")
        f.write("management api gnmi\n")
        f.write("    transport grpc mgmt\n")
        f.write("    ssl profile EDA\n")
        f.write("exit\n")
        f.write("write\n")


def _build_post_script(script_p: Path, dest_root: str) -> None:
    with script_p.open("w") as f:
        f.write("#!/usr/bin/Cli -p2\n")
        f.write(f"copy file:{dest_root}edaboot.crt certificate:\n")
        f.write(f"copy file:{dest_root}edaboot.key sslkey:\n")
        f.write("configure terminal\n")
        f.write("management api gnmi\n")
        f.write("    transport grpc discovery\n")
        f.write("    ssl profile edaboot\n")
        f.write("management api gnmi\n")
        f.write("    transport grpc mgmt\n")
        f.write("    ssl profile EDA\n")


# --------------------------------------------------------------------------- #
# High-level workflow                                                         #
# --------------------------------------------------------------------------- #
def prepare_ceos_node(
    node_name: str,
    namespace: str,
    version: str,
    mgmt_ip: str,
    username: str = "admin",
    password: str | None = None,
    quiet: bool = True,
) -> bool:
    """
    Perform EOS-specific post-integration steps.
    """
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
        cfg_p = tdir_path / "startup-config"
        post_p = tdir_path / "copy-certs.sh"
        prescript_p = tdir_path / "ceos_enable_scp.txt"
        script_p = tdir_path / "ceos_integrate_commands.txt"

        try:
            _extract_cert_and_config(
                node_name, namespace, version, cert_p, key_p, cfg_p, quiet
            )

            _build_enable_scp_script(prescript_p)

            if not execute_ssh_commands(
                prescript_p, username, mgmt_ip, node_name, working_pw, quiet
            ):
                raise RuntimeError("Unable to enable SCP")

            dest_root = _copy_files_and_config(
                ("/mnt/flash/", "/"),
                cert_p,
                key_p,
                post_p,
                cfg_p,
                username,
                mgmt_ip,
                working_pw,
                quiet,
            )

            _build_command_script(script_p, dest_root)

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
