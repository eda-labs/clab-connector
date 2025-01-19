# clab_connector/clients/eda/client.py

import json
import logging
import yaml

from clab_connector.clients.eda.http_client import create_pool_manager
from clab_connector.utils.exceptions import EDAConnectionError

logger = logging.getLogger(__name__)


class EDAClient:
    """
    EDAClient communicates with the EDA REST API.

    Parameters
    ----------
    hostname : str
        The base URL or IP address of the EDA API (without trailing slash).
    username : str
        EDA username for authentication.
    password : str
        EDA password for authentication.
    verify : bool
        Whether to verify SSL certificates.
    """

    CORE_GROUP = "core.eda.nokia.com"
    CORE_VERSION = "v1"
    INTERFACE_GROUP = "interfaces.eda.nokia.com"
    INTERFACE_VERSION = "v1alpha1"

    def __init__(self, hostname, username, password, verify):
        self.url = hostname
        self.username = username
        self.password = password
        self.verify = verify
        self.access_token = None
        self.refresh_token = None
        self.version = None
        self.transactions = []
        self.http = create_pool_manager(url=self.url, verify=self.verify)

    def login(self):
        """
        Log in to EDA, retrieving and storing the access and refresh tokens.

        Raises
        ------
        EDAConnectionError
            If authentication fails.
        """
        payload = {"username": self.username, "password": self.password}
        response = self.post("auth/login", payload, requires_auth=False)
        response_data = json.loads(response.data.decode("utf-8"))

        if "code" in response_data and response_data["code"] != 200:
            msg = (
                f"Could not authenticate with EDA. "
                f"Error: {response_data.get('message')} {response_data.get('details', '')}"
            )
            raise EDAConnectionError(msg)

        self.access_token = response_data["access_token"]
        self.refresh_token = response_data["refresh_token"]

    def get_headers(self, requires_auth=True):
        """
        Construct HTTP headers for requests, optionally adding Bearer auth.

        Parameters
        ----------
        requires_auth : bool
            Whether authentication is needed.

        Returns
        -------
        dict
            A dictionary of headers for the HTTP request.
        """
        headers = {}
        if requires_auth:
            if self.access_token is None:
                logger.info("No access_token found, logging in to EDA...")
                self.login()
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, api_path, requires_auth=True):
        """
        Issue an HTTP GET request to the EDA API.

        Parameters
        ----------
        api_path : str
            The relative path of the EDA API endpoint.
        requires_auth : bool
            Whether to include the Bearer token header.

        Returns
        -------
        urllib3.response.HTTPResponse
            The response object.
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"GET {url}")
        return self.http.request("GET", url, headers=self.get_headers(requires_auth))

    def post(self, api_path, payload, requires_auth=True):
        """
        Issue an HTTP POST request to the EDA API with a JSON body.

        Parameters
        ----------
        api_path : str
            The relative path of the EDA API endpoint.
        payload : dict
            The JSON-serializable payload.
        requires_auth : bool
            Whether to include the Bearer token header.

        Returns
        -------
        urllib3.response.HTTPResponse
            The response object.
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"POST {url}")
        return self.http.request(
            "POST",
            url,
            headers=self.get_headers(requires_auth),
            body=json.dumps(payload).encode("utf-8"),
        )

    def is_up(self):
        """
        Check if EDA is healthy.

        Returns
        -------
        bool
            True if EDA health endpoint reports status "UP", False otherwise.
        """
        logger.info("Checking EDA health")
        resp = self.get("core/about/health", requires_auth=False)
        data = json.loads(resp.data.decode("utf-8"))
        return data["status"] == "UP"

    def get_version(self):
        """
        Retrieve and cache the EDA version.

        Returns
        -------
        str
            The EDA version string.

        Raises
        ------
        EDAConnectionError
            If the version cannot be retrieved.
        """
        if self.version is not None:
            return self.version
        logger.info("Retrieving EDA version")
        resp = self.get("core/about/version")
        data = json.loads(resp.data.decode("utf-8"))
        version = data["eda"]["version"].split("-")[0]
        logger.info(f"EDA version: {version}")
        self.version = version
        return version

    def is_authenticated(self):
        """
        Check if the client is authenticated by attempting to retrieve the version.

        Returns
        -------
        bool
            True if authenticated, False otherwise.
        """
        try:
            self.get_version()
            return True
        except EDAConnectionError:
            return False

    def add_to_transaction(self, cr_type, payload):
        """
        Append a resource (create/replace/delete) to the transaction list.

        Parameters
        ----------
        cr_type : str
            One of ["create", "replace", "delete"].
        payload : dict
            The resource payload or definition.

        Returns
        -------
        dict
            The transaction item dict.
        """
        item = {"type": {cr_type: payload}}
        self.transactions.append(item)
        logger.debug(f"Adding item to transaction: {json.dumps(item, indent=2)}")
        return item

    def add_create_to_transaction(self, resource_yaml):
        """
        Add a create operation to the transaction for the given YAML resource.

        Parameters
        ----------
        resource_yaml : str
            YAML data as a string.

        Returns
        -------
        dict
            The created transaction item.
        """
        return self.add_to_transaction(
            "create", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_replace_to_transaction(self, resource_yaml):
        """
        Add a replace operation to the transaction for the given YAML resource.

        Parameters
        ----------
        resource_yaml : str
            YAML data as a string.

        Returns
        -------
        dict
            The created transaction item.
        """
        return self.add_to_transaction(
            "replace", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_delete_to_transaction(
        self, namespace, kind, name, group=None, version=None
    ):
        """
        Add a delete operation to the transaction for the specified resource.

        Parameters
        ----------
        namespace : str
            Namespace of the resource. Use "" for cluster-scoped resources.
        kind : str
            Resource kind, e.g. "Namespace".
        name : str
            Name of the resource.
        group : str, optional
            API group, defaults to the EDA core group.
        version : str, optional
            API version, defaults to the EDA core version.

        Returns
        -------
        None
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

    def is_transaction_item_valid(self, item):
        """
        Validate a single item in the transaction via EDA's /validate endpoint.

        Parameters
        ----------
        item : dict
            The transaction item to validate.

        Returns
        -------
        bool
            True if validation succeeded, False otherwise.
        """
        logger.info("Validating transaction item")
        response = self.post("core/transaction/v1/validate", item)
        if response.status == 204:
            logger.info("Transaction item validation success.")
            return True
        data = json.loads(response.data.decode("utf-8"))
        logger.warning(f"Validation error: {data}")
        return False

    def commit_transaction(
        self, description, dryrun=False, resultType="normal", retain=True
    ):
        """
        Commit the accumulated transaction items to EDA.

        Parameters
        ----------
        description : str
            A short description of the transaction.
        dryrun : bool
            If True, EDA will only simulate the transaction.
        resultType : str
            The type of result to request, e.g. "normal".
        retain : bool
            If True, the transaction is stored in the EDA history.

        Returns
        -------
        str
            The transaction ID.

        Raises
        ------
        EDAConnectionError
            If the transaction fails or does not return an ID.
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
        data = json.loads(resp.data.decode("utf-8"))
        if "id" not in data:
            raise EDAConnectionError(f"No transaction ID in response: {data}")
        tx_id = data["id"]
        logger.info(f"Waiting for transaction {tx_id} to complete")
        details_resp = self.get(
            f"core/transaction/v1/details/{tx_id}?waitForComplete=true&failOnErrors=true"
        )
        details = json.loads(details_resp.data.decode("utf-8"))
        if "code" in details:
            logger.error(f"Transaction commit failed: {details}")
            raise EDAConnectionError(f"Transaction commit failed: {details}")
        logger.info("Commit successful")
        self.transactions = []
        return tx_id
