# clab_connector/clients/eda/client.py

import json
import logging
import yaml

from clab_connector.clients.eda.http_client import create_pool_manager
from clab_connector.utils.exceptions import EDAConnectionError

logger = logging.getLogger(__name__)


class EDAClient:
    """
    EDAClient communicates with the EDA REST API
    (formerly class 'EDA')
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
        headers = {}
        if requires_auth:
            if self.access_token is None:
                logger.info("No access_token found, logging in to EDA...")
                self.login()
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, api_path, requires_auth=True):
        url = f"{self.url}/{api_path}"
        logger.info(f"GET {url}")
        return self.http.request("GET", url, headers=self.get_headers(requires_auth))

    def post(self, api_path, payload, requires_auth=True):
        url = f"{self.url}/{api_path}"
        logger.info(f"POST {url}")
        return self.http.request(
            "POST",
            url,
            headers=self.get_headers(requires_auth),
            body=json.dumps(payload).encode("utf-8"),
        )

    def is_up(self):
        logger.info("Checking EDA health")
        resp = self.get("core/about/health", requires_auth=False)
        data = json.loads(resp.data.decode("utf-8"))
        return data["status"] == "UP"

    def get_version(self):
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
        try:
            self.get_version()
            return True
        except EDAConnectionError:
            return False

    def add_to_transaction(self, cr_type, payload):
        item = {"type": {cr_type: payload}}
        self.transactions.append(item)
        logger.debug(f"Adding item to transaction: {json.dumps(item, indent=2)}")
        return item

    def add_create_to_transaction(self, resource_yaml):
        return self.add_to_transaction(
            "create", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_replace_to_transaction(self, resource_yaml):
        return self.add_to_transaction(
            "replace", {"value": yaml.safe_load(resource_yaml)}
        )

    def add_delete_to_transaction(
        self, namespace, kind, name, group=None, version=None
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

    def is_transaction_item_valid(self, item):
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
