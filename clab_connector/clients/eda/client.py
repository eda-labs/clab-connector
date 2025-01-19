# clab_connector/clients/eda/client.py

"""
This module provides the EDAClient class for communicating with the EDA REST API.
Starting with EDA v24.12.1, authentication is handled via Keycloak.

We support two flows:
1. If client_secret is known (user passes --client-secret), we do resource-owner
   password flow directly in realm='eda'.
2. If client_secret is unknown, we do an admin login in realm='master' using
   the same eda_user/eda_password (assuming they are Keycloak admin credentials),
   retrieve the 'eda' client secret, then proceed with resource-owner flow.
"""

import json
import logging
import yaml
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
    username : str
        EDA user (also used as Keycloak admin if secret is unknown).
    password : str
        Password for the above user (also used as Keycloak admin if secret unknown).
    verify : bool
        Whether to verify SSL certificates.
    client_secret : str, optional
        Known Keycloak client secret for 'eda'. If not provided, we do the admin
        realm flow to retrieve it using username/password.
    """

    KEYCLOAK_ADMIN_REALM = "master"
    KEYCLOAK_ADMIN_CLIENT_ID = "admin-cli"
    EDA_REALM = "eda"
    EDA_API_CLIENT_ID = "eda"

    CORE_GROUP = "core.eda.nokia.com"
    CORE_VERSION = "v1"
    INTERFACE_GROUP = "interfaces.eda.nokia.com"
    INTERFACE_VERSION = "v1alpha1"

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        verify: bool = True,
        client_secret: str = None,
    ):
        self.url = hostname.rstrip("/")
        self.username = username
        self.password = password
        self.verify = verify
        self.client_secret = client_secret

        self.access_token = None
        self.refresh_token = None
        self.version = None
        self.transactions = []

        self.http = create_pool_manager(url=self.url, verify=self.verify)

    def login(self):
        """
        Acquire an access token via Keycloak resource-owner flow in realm='eda'.
        If client_secret is unknown, fetch it using admin credentials in realm='master'.
        """
        if not self.client_secret:
            logger.info("No client_secret provided; fetching via Keycloak admin API...")
            self.client_secret = self._fetch_client_secret_via_admin()
            logger.info("Successfully retrieved client_secret from Keycloak.")

        logger.info("Acquiring user access token via Keycloak resource-owner flow...")
        self.access_token = self._fetch_user_token(self.client_secret)
        if not self.access_token:
            raise EDAConnectionError("Could not retrieve an access token for EDA.")

        logger.info("Keycloak-based login successful.")

    def _fetch_client_secret_via_admin(self) -> str:
        """
        Use the same username/password as Keycloak admin in realm='master'.
        Then retrieve the client secret for the 'eda' client in realm='eda'.

        Returns
        -------
        str
            The client_secret for 'eda'.

        Raises
        ------
        EDAConnectionError
            If we fail to fetch an admin token or the 'eda' client secret.
        """
        admin_token = self._fetch_admin_token()
        if not admin_token:
            raise EDAConnectionError("Failed to fetch Keycloak admin token.")

        # List clients in the "eda" realm
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
                f"Failed to list clients in realm '{self.EDA_REALM}': {resp.data.decode()}"
            )

        clients = json.loads(resp.data.decode("utf-8"))
        eda_client = next(
            (c for c in clients if c.get("clientId") == self.EDA_API_CLIENT_ID), None
        )
        if not eda_client:
            raise EDAConnectionError("Client 'eda' not found in realm 'eda'")

        # Get the client secret
        client_id = eda_client["id"]
        secret_url = f"{admin_api_url}/{client_id}/client-secret"
        secret_resp = self.http.request("GET", secret_url, headers=headers)
        if secret_resp.status != 200:
            raise EDAConnectionError(
                f"Failed to fetch 'eda' client secret: {secret_resp.data.decode()}"
            )

        return json.loads(secret_resp.data.decode("utf-8"))["value"]

    def _fetch_admin_token(self) -> str:
        """
        Fetch an admin token from the 'master' realm using self.username/password.
        """
        token_url = (
            f"{self.url}/core/httpproxy/v1/keycloak/"
            f"realms/{self.KEYCLOAK_ADMIN_REALM}/protocol/openid-connect/token"
        )
        form_data = {
            "grant_type": "password",
            "client_id": self.KEYCLOAK_ADMIN_CLIENT_ID,
            "username": self.username,
            "password": self.password,
        }
        encoded_data = urlencode(form_data).encode("utf-8")

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.http.request("POST", token_url, body=encoded_data, headers=headers)
        if resp.status != 200:
            raise EDAConnectionError(
                f"Failed Keycloak admin login: {resp.data.decode()}"
            )

        token_json = json.loads(resp.data.decode("utf-8"))
        return token_json.get("access_token")

    def _fetch_user_token(self, client_secret: str) -> str:
        """
        Resource-owner password flow in the 'eda' realm using self.username/password.
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
            "username": self.username,
            "password": self.password,
        }
        encoded_data = urlencode(form_data).encode("utf-8")

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.http.request("POST", token_url, body=encoded_data, headers=headers)
        if resp.status != 200:
            raise EDAConnectionError(f"Failed user token request: {resp.data.decode()}")

        token_json = json.loads(resp.data.decode("utf-8"))
        return token_json.get("access_token")

    def get_headers(self, requires_auth: bool = True) -> dict:
        """
        Construct HTTP headers, adding Bearer auth if requires_auth=True.
        """
        headers = {}
        if requires_auth:
            if not self.access_token:
                logger.debug("No access_token found; performing Keycloak login...")
                self.login()
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, api_path: str, requires_auth: bool = True):
        """
        Perform an HTTP GET request against the EDA API.
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"GET {url}")
        return self.http.request("GET", url, headers=self.get_headers(requires_auth))

    def post(self, api_path: str, payload: dict, requires_auth: bool = True):
        """
        Perform an HTTP POST request with a JSON body to the EDA API.
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"POST {url}")
        body = json.dumps(payload).encode("utf-8")
        return self.http.request(
            "POST", url, headers=self.get_headers(requires_auth), body=body
        )

    def is_up(self) -> bool:
        """
        Check if EDA is healthy by calling /core/about/health.
        """
        logger.info("Checking EDA health")
        resp = self.get("core/about/health", requires_auth=False)
        if resp.status != 200:
            return False

        data = json.loads(resp.data.decode("utf-8"))
        return data.get("status") == "UP"

    def get_version(self) -> str:
        """
        Retrieve and cache the EDA version from /core/about/version.
        """
        if self.version is not None:
            return self.version

        logger.info("Retrieving EDA version")
        resp = self.get("core/about/version")
        if resp.status != 200:
            raise EDAConnectionError(f"Version check failed: {resp.data.decode()}")

        data = json.loads(resp.data.decode("utf-8"))
        raw_ver = data["eda"]["version"]
        self.version = raw_ver.split("-")[0]
        logger.info(f"EDA version: {self.version}")
        return self.version

    def is_authenticated(self) -> bool:
        """
        Check if the client is authenticated by trying to get the version.
        """
        try:
            self.get_version()
            return True
        except EDAConnectionError:
            return False

    def add_to_transaction(self, cr_type: str, payload: dict) -> dict:
        """
        Append an operation (create/replace/delete) to the transaction list.
        """
        item = {"type": {cr_type: payload}}
        self.transactions.append(item)
        logger.debug(f"Adding item to transaction: {json.dumps(item, indent=2)}")
        return item

    def add_create_to_transaction(self, resource_yaml: str) -> dict:
        """
        Add a 'create' resource to the transaction from YAML content.
        """
        return self.add_to_transaction(
            "create", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_replace_to_transaction(self, resource_yaml: str) -> dict:
        """
        Add a 'replace' resource to the transaction from YAML content.
        """
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
        """
        Add a 'delete' operation for a resource by namespace/kind/name.
        """
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
        """
        Validate a single transaction item with /core/transaction/v1/validate.
        """
        logger.info("Validating transaction item")
        resp = self.post("core/transaction/v1/validate", item)
        if resp.status == 204:  # 204 means success
            logger.info("Transaction item validation success.")
            return True

        data = json.loads(resp.data.decode("utf-8"))
        logger.warning(f"Validation error: {data}")
        return False

    def commit_transaction(
        self,
        description: str,
        dryrun: bool = False,
        resultType: str = "normal",
        retain: bool = True,
    ) -> str:
        """
        Commit accumulated transaction items to EDA.
        """
        payload = {
            "description": description,
            "dryrun": dryrun,
            "resultType": resultType,
            "retain": retain,
            "crs": self.transactions,
        }
        logger.info(
            f"Committing transaction: {description}, {len(self.transactions)} items"
        )
        resp = self.post("core/transaction/v1", payload)
        if resp.status != 200:
            raise EDAConnectionError(
                f"Transaction request failed: {resp.data.decode()}"
            )

        data = json.loads(resp.data.decode("utf-8"))
        tx_id = data.get("id")
        if not tx_id:
            raise EDAConnectionError(f"No transaction ID in response: {data}")

        logger.info(f"Waiting for transaction {tx_id} to complete...")
        details_path = f"core/transaction/v1/details/{tx_id}?waitForComplete=true&failOnErrors=true"
        details_resp = self.get(details_path)
        if details_resp.status != 200:
            raise EDAConnectionError(
                f"Transaction detail request failed: {details_resp.data.decode()}"
            )

        details = json.loads(details_resp.data.decode("utf-8"))
        if "code" in details:
            logger.error(f"Transaction commit failed: {details}")
            raise EDAConnectionError(f"Transaction commit failed: {details}")

        logger.info("Commit successful.")
        self.transactions = []
        return tx_id
