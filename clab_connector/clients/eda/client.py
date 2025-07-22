# clab_connector/clients/eda/client.py

"""
This module provides the EDAClient class for communicating with the EDA REST API.
Starting with EDA v24.12.1, authentication is handled via Keycloak.

We support two flows:
1. If kc_secret is known (user passes --kc-secret), we do resource-owner
   password flow directly in realm='eda'.

2. If kc_secret is unknown, we do an admin login in realm='master' using
   kc_user / kc_password to retrieve the 'eda' client secret,
   then proceed with resource-owner flow in realm='eda'.
"""

import json
import logging
import yaml

from clab_connector.utils.constants import SUBSTEP_INDENT
from urllib.parse import urlencode

from clab_connector.clients.eda.http_client import create_pool_manager
from clab_connector.utils.exceptions import EDAConnectionError

logger = logging.getLogger(__name__)


class EDAClient:
    """
    EDAClient communicates with the EDA REST API via Keycloak flows.

    Parameters
    ----------
    hostname : str
        The base URL for EDA, e.g. "https://my-eda.example".
    eda_user : str
        EDA user in realm='eda'.
    eda_password : str
        EDA password in realm='eda'.
    kc_secret : str, optional
        Known Keycloak client secret for 'eda'. If not provided, we do the admin
        realm flow to retrieve it using kc_user/kc_password.
    verify : bool
        Whether to verify SSL certificates (default=True).
    kc_user : str
        Keycloak "master" realm admin username (default="admin").
    kc_password : str
        Keycloak "master" realm admin password (default="admin").
    """

    KEYCLOAK_ADMIN_REALM = "master"
    KEYCLOAK_ADMIN_CLIENT_ID = "admin-cli"
    EDA_REALM = "eda"
    EDA_API_CLIENT_ID = "eda"

    CORE_GROUP = "core.eda.nokia.com"
    CORE_VERSION = "v1"

    def __init__(
        self,
        hostname: str,
        eda_user: str,
        eda_password: str,
        kc_secret: str = None,
        verify: bool = True,
        kc_user: str = "admin",
        kc_password: str = "admin",
    ):
        self.url = hostname.rstrip("/")
        self.eda_user = eda_user
        self.eda_password = eda_password
        self.kc_secret = kc_secret  # If set, we skip the admin login
        self.verify = verify
        self.kc_user = kc_user
        self.kc_password = kc_password

        self.access_token = None
        self.refresh_token = None
        self.version = None
        self.transactions = []

        self.http = create_pool_manager(url=self.url, verify=self.verify)

    def login(self):
        """
        Acquire an access token via Keycloak resource-owner flow in realm='eda'.
        If kc_secret is not provided, fetch it using kc_user/kc_password in realm='master'.
        """
        if not self.kc_secret:
            logger.debug(
                "No kc_secret provided; retrieving it from Keycloak master realm."
            )
            self.kc_secret = self._fetch_client_secret_via_admin()
            logger.info(
                f"{SUBSTEP_INDENT}Successfully retrieved EDA client secret from Keycloak."
            )

        logger.debug(
            "Acquiring user access token via Keycloak resource-owner flow (realm=eda)."
        )
        self.access_token = self._fetch_user_token(self.kc_secret)
        if not self.access_token:
            raise EDAConnectionError("Could not retrieve an access token for EDA.")

        logger.debug("Keycloak-based login successful (realm=eda).")

    def _fetch_client_secret_via_admin(self) -> str:
        """
        Use kc_user/kc_password in realm='master' to retrieve
        the client secret for 'eda' client in realm='eda'.

        Returns
        -------
        str
            The 'eda' client secret.

        Raises
        ------
        EDAConnectionError
            If we fail to fetch an admin token or the 'eda' client secret.
        """
        if not self.kc_user or not self.kc_password:
            raise EDAConnectionError(
                "Cannot fetch 'eda' client secret: no kc_secret provided and no kc_user/kc_password available."
            )

        admin_token = self._fetch_admin_token(self.kc_user, self.kc_password)
        if not admin_token:
            raise EDAConnectionError(
                "Failed to fetch Keycloak admin token in realm=master."
            )

        admin_api_url = (
            f"{self.url}/core/httpproxy/v1/keycloak/"
            f"admin/realms/{self.EDA_REALM}/clients"
        )
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

        resp = self.http.request("GET", admin_api_url, headers=headers)
        if resp.status != 200:
            raise EDAConnectionError(
                f"Failed to list clients in realm='{self.EDA_REALM}': {resp.data.decode()}"
            )

        clients = json.loads(resp.data.decode("utf-8"))
        eda_client = next(
            (c for c in clients if c.get("clientId") == self.EDA_API_CLIENT_ID), None
        )
        if not eda_client:
            raise EDAConnectionError(
                f"Client '{self.EDA_API_CLIENT_ID}' not found in realm='{self.EDA_REALM}'."
            )

        client_id = eda_client["id"]
        secret_url = f"{admin_api_url}/{client_id}/client-secret"
        secret_resp = self.http.request("GET", secret_url, headers=headers)
        if secret_resp.status != 200:
            raise EDAConnectionError(
                f"Failed to fetch '{self.EDA_API_CLIENT_ID}' client secret: {secret_resp.data.decode()}"
            )

        return json.loads(secret_resp.data.decode("utf-8"))["value"]

    def _fetch_admin_token(self, admin_user: str, admin_password: str) -> str:
        """
        Fetch an admin token from the 'master' realm using admin_user/admin_password.
        """
        token_url = (
            f"{self.url}/core/httpproxy/v1/keycloak/"
            f"realms/{self.KEYCLOAK_ADMIN_REALM}/protocol/openid-connect/token"
        )
        form_data = {
            "grant_type": "password",
            "client_id": self.KEYCLOAK_ADMIN_CLIENT_ID,
            "username": admin_user,
            "password": admin_password,
        }
        encoded_data = urlencode(form_data).encode("utf-8")

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.http.request("POST", token_url, body=encoded_data, headers=headers)
        if resp.status != 200:
            raise EDAConnectionError(
                f"Failed Keycloak admin login in realm='{self.KEYCLOAK_ADMIN_REALM}': {resp.data.decode()}"
            )

        token_json = json.loads(resp.data.decode("utf-8"))
        return token_json.get("access_token")

    def _fetch_user_token(self, client_secret: str) -> str:
        """
        Resource-owner password flow in realm='eda' using eda_user/eda_password.
        """
        token_url = (
            f"{self.url}/core/httpproxy/v1/keycloak/"
            f"realms/{self.EDA_REALM}/protocol/openid-connect/token"
        )
        form_data = {
            "grant_type": "password",
            "client_id": self.EDA_API_CLIENT_ID,
            "client_secret": client_secret,
            "scope": "openid",
            "username": self.eda_user,
            "password": self.eda_password,
        }
        encoded_data = urlencode(form_data).encode("utf-8")

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.http.request("POST", token_url, body=encoded_data, headers=headers)
        if resp.status != 200:
            raise EDAConnectionError(f"Failed user token request: {resp.data.decode()}")

        token_json = json.loads(resp.data.decode("utf-8"))
        return token_json.get("access_token")

    # ---------------------------------------------------------------------
    # Below here, the rest of the class is unchanged: GET/POST, commit tx, etc.
    # ---------------------------------------------------------------------

    def get_headers(self, requires_auth: bool = True) -> dict:
        headers = {}
        if requires_auth:
            if not self.access_token:
                logger.debug("No access_token found; performing Keycloak login...")
                self.login()
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, api_path: str, requires_auth: bool = True):
        url = f"{self.url}/{api_path}"
        logger.debug(f"GET {url}")
        return self.http.request("GET", url, headers=self.get_headers(requires_auth))

    def post(self, api_path: str, payload: dict, requires_auth: bool = True):
        url = f"{self.url}/{api_path}"
        logger.debug(f"POST {url}")
        body = json.dumps(payload).encode("utf-8")
        headers = self.get_headers(requires_auth)
        headers["Content-Type"] = "application/json"
        return self.http.request(
            "POST", url, headers=headers, body=body
        )

    def patch(self, api_path: str, payload: str, requires_auth: bool = True):
        url = f"{self.url}/{api_path}"
        logger.debug(f"PATCH {url}")
        body = payload.encode("utf-8")
        headers = self.get_headers(requires_auth)
        headers["Content-Type"] = "application/json"
        return self.http.request(
            "PATCH", url, headers=headers, body=body
        )

    def is_up(self) -> bool:
        logger.info(f"{SUBSTEP_INDENT}Checking EDA health")
        resp = self.get("core/about/health", requires_auth=False)
        if resp.status != 200:
            return False

        data = json.loads(resp.data.decode("utf-8"))
        return data.get("status") == "UP"

    def get_version(self) -> str:
        if self.version is not None:
            return self.version

        logger.debug("Retrieving EDA version")
        resp = self.get("core/about/version")
        if resp.status != 200:
            raise EDAConnectionError(f"Version check failed: {resp.data.decode()}")

        data = json.loads(resp.data.decode("utf-8"))
        raw_ver = data["eda"]["version"]
        self.version = raw_ver.split("-")[0]
        logger.debug(f"EDA version: {self.version}")
        return self.version

    def is_authenticated(self) -> bool:
        try:
            self.get_version()
            return True
        except EDAConnectionError:
            return False

    def add_to_transaction(self, cr_type: str, payload: dict) -> dict:
        item = {"type": {cr_type: payload}}
        self.transactions.append(item)
        logger.debug(f"Adding item to transaction: {json.dumps(item, indent=2)}")
        return item

    def add_create_to_transaction(self, resource_yaml: str) -> dict:
        return self.add_to_transaction(
            "create", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_replace_to_transaction(self, resource_yaml: str) -> dict:
        return self.add_to_transaction(
            "replace", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_delete_to_transaction(
        self,
        namespace: str,
        kind: str,
        name: str,
        group: str = None,
        version: str = None,
    ):
        group = group or self.CORE_GROUP
        version = version or self.CORE_VERSION
        self.add_to_transaction(
            "delete",
            {
                "gvk": {
                    "group": group,
                    "version": version,
                    "kind": kind,
                },
                "name": name,
                "namespace": namespace,
            },
        )

    def is_transaction_item_valid(self, item: dict) -> bool:
        logger.debug("Validating transaction item")

        # Determine which validation endpoint to use based on the EDA version
        version = self.get_version()
        logger.debug(f"EDA version for validation: {version}")

        if version.startswith("v"):
            version = version[1:]

        parts = version.split(".")
        major = int(parts[0]) if parts[0].isdigit() else 0

        # v2 is the default. Only 24.x releases still use the v1 endpoint.
        if major == 24:
            logger.debug("Using v1 transaction validation endpoint")
            resp = self.post("core/transaction/v1/validate", item)
        else:
            logger.debug("Using v2 transaction validation endpoint")
            resp = self.post("core/transaction/v2/validate", [item])

        if resp.status == 204:
            logger.debug("Transaction item validation success.")
            return True

        data = json.loads(resp.data.decode("utf-8"))
        logger.warning(f"{SUBSTEP_INDENT}Validation error: {data}")
        return False

    def commit_transaction(
        self,
        description: str,
        dryrun: bool = False,
        resultType: str = "normal",
        retain: bool = True,
    ) -> str:
        version = self.get_version()
        logger.debug(f"EDA version for transaction: {version}")

        if version.startswith("v"):
            version = version[1:]

        parts = version.split(".")
        major = int(parts[0]) if parts[0].isdigit() else 0

        payload = {
            "description": description,
            "dryrun": dryrun,
            "resultType": resultType,
            "retain": retain,
            "crs": self.transactions,
        }
        logger.info(
            f"{SUBSTEP_INDENT}Committing transaction: {description}, {len(self.transactions)} items"
        )
        if major == 24:
            logger.debug("Using v1 transaction commit endpoint")
            resp = self.post("core/transaction/v1", payload)
        else:
            logger.debug("Using v2 transaction commit endpoint")
            resp = self.post("core/transaction/v2", payload)
        if resp.status != 200:
            raise EDAConnectionError(
                f"Transaction request failed: {resp.data.decode()}"
            )

        data = json.loads(resp.data.decode("utf-8"))
        tx_id = data.get("id")
        if not tx_id:
            raise EDAConnectionError(f"No transaction ID in response: {data}")

        logger.info(f"{SUBSTEP_INDENT}Waiting for transaction {tx_id} to complete...")
        if major == 24:
            details_path = (
                f"core/transaction/v1/details/{tx_id}?waitForComplete=true&failOnErrors=true"
            )
        else:
            details_path = f"core/transaction/v2/result/summary/{tx_id}"
        details_resp = self.get(details_path)
        if details_resp.status != 200:
            raise EDAConnectionError(
                f"Transaction detail request failed: {details_resp.data.decode()}"
            )

        details = json.loads(details_resp.data.decode("utf-8"))
        if "code" in details:
            logger.error(f"Transaction commit failed: {details}")
            raise EDAConnectionError(f"Transaction commit failed: {details}")

        logger.info(f"{SUBSTEP_INDENT}Commit successful.")
        self.transactions = []
        return tx_id
