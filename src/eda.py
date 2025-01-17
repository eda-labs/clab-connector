import json
import logging

import urllib3
import yaml

# configure logging
logger = logging.getLogger(__name__)


class EDA:
    CORE_GROUP = "core.eda.nokia.com"
    CORE_VERSION = "v1"
    INTERFACE_GROUP = "interfaces.eda.nokia.com"
    INTERFACE_VERSION = "v1alpha1"

    def __init__(self, hostname, username, password, verify):
        """
        Constructor

        Parameters
        ----------
        hostname:       EDA hostname (IP or FQDN)
        username:       EDA user name
        password:       EDA user password
        verify:         Whether to verify the certificate when communicating with EDA
        """
        self.url = f"{hostname}"
        self.username = username
        self.password = password
        self.verify = verify
        self.access_token = None
        self.refresh_token = None
        self.version = None
        self.transactions = []

        # Create urllib3 connection pool
        self.http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED' if verify else 'CERT_NONE',
            retries=urllib3.Retry(3)
        )

    def login(self):
        """
        Retrieves an access_token and refresh_token from the EDA API
        """
        payload = {"username": self.username, "password": self.password}

        response = self.post("auth/login", payload, False)
        response_data = json.loads(response.data.decode('utf-8'))

        if "code" in response_data and response_data["code"] != 200:
            raise Exception(
                f"Could not authenticate with EDA, error message: '{response_data['message']} {response_data['details']}'"
            )

        self.access_token = response_data["access_token"]
        self.refresh_token = response_data["refresh_token"]

    def get_headers(self, requires_auth):
        """
        Configures the right headers for an HTTP request

        Parameters
        ----------
        requires_auth: Whether the request requires authorization

        Returns
        -------
        A header dictionary
        """
        headers = {}
        if requires_auth:
            if self.access_token is None:
                logger.info("No access_token found, authenticating...")
                self.login()

            headers["Authorization"] = f"Bearer {self.access_token}"

        return headers

    def get(self, api_path, requires_auth=True):
        """
        Performs an HTTP GET request, taking the right proxy settings into account

        Parameters
        ----------
        api_path:       path to be appended to the base EDA hostname
        requires_auth:  Whether this request requires authentication

        Returns
        -------
        The HTTP response
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"Performing GET request to '{url}'")

        return self.http.request(
            'GET',
            url,
            headers=self.get_headers(requires_auth)
        )

    def post(self, api_path, payload, requires_auth=True):
        """
        Performs an HTTP POST request, taking the right proxy settings into account

        Parameters
        ----------
        api_path:       path to be appended to the base EDA hostname
        payload:        JSON data for the request
        requires_auth:  Whether this request requires authentication

        Returns
        -------
        The HTTP response
        """
        url = f"{self.url}/{api_path}"
        logger.info(f"Performing POST request to '{url}'")
        return self.http.request(
            'POST',
            url,
            headers=self.get_headers(requires_auth),
            body=json.dumps(payload).encode('utf-8')
        )

    def is_up(self):
        """
        Gets the health of EDA

        Returns
        -------
        True if EDA status is "UP", False otherwise
        """
        logger.info("Checking whether EDA is up")
        health = self.get("core/about/health", requires_auth=False)
        health_data = json.loads(health.data.decode('utf-8'))
        logger.debug(health_data)
        return health_data["status"] == "UP"

    def get_version(self):
        """
        Retrieves the EDA version number
        """
        # caching this, as it might get called a lot when backwards compatibility
        # starts becoming a point of focus
        if self.version is not None:
            return self.version

        logger.info("Getting EDA version")
        version_response = self.get("core/about/version")
        version_data = json.loads(version_response.data.decode('utf-8'))
        version = version_data["eda"]["version"].split("-")[0]
        logger.info(f"EDA version is {version}")

        # storing this to make the tool backwards compatible
        self.version = version
        return version

    def is_authenticated(self):
        """
        Retrieves the version number of EDA to see if we can authenticate correctly

        Returns
        -------
        True if we can authenticate in EDA, False otherwise
        """
        logger.info("Checking whether we can authenticate with EDA")
        self.get_version()
        # if the previous method did not raise an exception, authentication was successful
        return True

    def add_to_transaction(self, cr_type, payload):
        """
        Adds a transaction to the basket

        Parameters
        ----------
        type:       action type, possible values: ['create', 'delete', 'replace', 'modify']
        payload:    the operation's payload

        Returns
        -------
        The newly added transaction item
        """

        item = {"type": {cr_type: payload}}

        self.transactions.append(item)
        logger.debug(f"Adding item to transaction: {json.dumps(item, indent=4)}")

        return item

    def add_create_to_transaction(self, resource):
        """
        Adds a 'create' operation to the transaction

        Parameters
        ----------
        resource: the resource to be created

        Returns
        -------
        The created item
        """
        return self.add_to_transaction("create", {"value": yaml.safe_load(resource)})

    def add_replace_to_transaction(self, resource):
        """
        Adds a 'replace' operation to the transaction

        Parameters
        ----------
        resource: the resource to be replaced

        Returns
        -------
        The replaced item
        """
        return self.add_to_transaction("replace", {"value": yaml.safe_load(resource)})

    def add_delete_to_transaction(
        self, namespace, kind, name, group=CORE_GROUP, version=CORE_VERSION
    ):
        """
        Adds a 'delete' operation to the transaction

        Parameters
        ----------
        namespace: the namespace of the resource to be deleted
        kind:      the kind of the resource to be deleted
        group:     the group of the resource to be deleted
        version:   the version of the resource to be deleted

        Returns
        -------
        The created item
        """
        self.add_to_transaction(
            "delete",
            {
                "gvk": {  # Group, Version, Kind
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
        Validates a transaction item

        Parameters
        ----------
        item: the item to be validated

        Returns
        -------
        True if the transaction is valid, False otherwise
        """
        logger.info("Validating transaction item")

        response = self.post("core/transaction/v1/validate", item)
        if response.status == 204:
            logger.info("Validation successful")
            return True

        response_data = json.loads(response.data.decode('utf-8'))  # Need to decode response data

        if "code" in response_data:
            message = f"{response_data['message']}"
            if "details" in response_data:
                message = f"{message} - {response_data['details']}"
            logger.warning(
                f"While validating a transaction item, the following validation error was returned (code {response_data['code']}): '{message}'"
            )

        return False

    def commit_transaction(
        self, description, dryrun=False, resultType="normal", retain=True
    ):
        """
        Commits the transaction to EDA, and waits for the transaction to complete

        Parameters
        ----------
        description:    Description provided for this transaction
        dryrun:         Whether this commit should be treated as a dryrun
        resultType:     Don't know yet what this does
        retain:         Don't know yet what this does
        """

        payload = {
            "description": description,
            "dryrun": dryrun,
            "resultType": resultType,
            "retain": retain,
            "crs": self.transactions,
        }

        logger.info(f"Committing transaction with {len(self.transactions)} item(s)")
        logger.debug(json.dumps(payload, indent=4))

        response = self.post("core/transaction/v1", payload)
        response_data = json.loads(response.data.decode('utf-8'))
        if "id" not in response_data:
            raise Exception(f"Could not find transaction ID in response {response_data}")

        transactionId = response_data["id"]

        logger.info(f"Waiting for transaction with ID {transactionId} to complete")
        result = json.loads(self.get(
            f"core/transaction/v1/details/{transactionId}?waitForComplete=true&failOnErrors=true"
        ).data.decode('utf-8'))

        if "code" in result:
            message = f"{result['message']}"

            if "details" in message:
                message = f"{message} - {result['details']}"

            errors = []
            if "errors" in result:
                errors = [
                    f"{x['error']['message']} {x['error']['details']}"
                    for x in result["errors"]
                ]

            logger.error(
                f"Committing transaction failed (error code {result['code']}). Error message: '{message} {errors}'"
            )
            raise Exception("Failed to commit - see error above")

        logger.info("Commit successful")
        self.transactions = []
        return transactionId

    def revert_transaction(self, transactionId):
        """
        Reverts a transaction in EDA

        Parameters
        ----------
        transactionId: ID of the transaction to revert

        Returns
        -------
        True if revert was successful, raises exception otherwise
        """
        logger.info(f"Reverting transaction with ID {transactionId}")

        # First wait for the transaction details to ensure it's committed
        self.get(
            f"core/transaction/v1/details/{transactionId}?waitForComplete=true"
        ).json()

        response = self.post(f"core/transaction/v1/revert/{transactionId}", {})
        result = json.loads(response.data.decode('utf-8'))

        if "code" in result and result["code"] != 0:
            message = f"{result['message']}"

            if "details" in result:
                message = f"{message} - {result['details']}"

            errors = []
            if "errors" in result:
                errors = [
                    f"{x['error']['message']} {x['error']['details']}"
                    for x in result["errors"]
                ]

            logger.error(
                f"Reverting transaction failed (error code {result['code']}). Error message: '{message} {errors}'"
            )
            raise Exception("Failed to revert transaction - see error above")

        logger.info("Transaction revert successful")
        return True

    def restore_transaction(self, transactionId):
        """
        Restores to a specific transaction ID in EDA

        Parameters
        ----------
        transactionId: ID of the transaction to restore to (will restore to transactionId - 1)

        Returns
        -------
        True if restore was successful, raises exception otherwise
        """
        restore_point = int(transactionId)
        logger.info(f"Restoring to transaction ID {restore_point}")

        # First wait for the transaction details to ensure it's committed
        self.get(
            f"core/transaction/v1/details/{transactionId}?waitForComplete=true"
        ).json()

        response = self.post(f"core/transaction/v1/restore/{restore_point}", {})
        result = json.loads(response.data.decode('utf-8'))

        if "code" in result and result["code"] != 0:
            message = f"{result['message']}"

            if "details" in result:
                message = f"{message} - {result['details']}"

            errors = []
            if "errors" in result:
                errors = [
                    f"{x['error']['message']} {x['error']['details']}"
                    for x in result["errors"]
                ]

            logger.error(
                f"Restoring to transaction failed (error code {result['code']}). Error message: '{message} {errors}'"
            )
            raise Exception("Failed to restore transaction - see error above")

        logger.info("Transaction restore successful")
        return True
