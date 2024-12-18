import logging
import requests
import yaml
import json

# configure logging
logger = logging.getLogger(__name__)


class EDA:
    CORE_GROUP = "core.eda.nokia.com"
    CORE_VERSION = "v1"
    INTERFACE_GROUP = "interfaces.eda.nokia.com"
    INTERFACE_VERSION = "v1alpha1"

    def __init__(self, hostname, username, password, http_proxy, https_proxy, verify):
        """
        Constructor

        Parameters
        ----------
        hostname:       EDA hostname (IP or FQDN)
        username:       EDA user name
        password:       EDA user password
        http_proxy:     HTTP proxy to be used for communication with EDA
        https_proxy:    HTTPS proxy to be used for communication with EDA
        verify:         Whether to verify the certificate when communicating with EDA
        """
        self.url = f"{hostname}"
        self.username = username
        self.password = password
        self.proxies = {"http": http_proxy, "https": https_proxy}
        self.verify = verify
        self.access_token = None
        self.refresh_token = None
        self.version = None
        self.transactions = []

    def login(self):
        """
        Retrieves an access_token and refresh_token from the EDA API
        """
        payload = {"username": self.username, "password": self.password}

        response = self.post("auth/login", payload, False).json()

        if "code" in response and response["code"] != 200:
            raise Exception(
                f"Could not authenticate with EDA, error message: '{response['message']} {response['details']}'"
            )

        self.access_token = response["access_token"]
        self.refresh_token = response["refresh_token"]

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

        return requests.get(
            url,
            proxies=self.proxies,
            verify=self.verify,
            headers=self.get_headers(requires_auth),
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
        return requests.post(
            url,
            proxies=self.proxies,
            verify=self.verify,
            json=payload,
            headers=self.get_headers(requires_auth),
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
        logger.debug(health.json())
        return health.json()["status"] == "UP"

    def get_version(self):
        """
        Retrieves the EDA version number
        """
        # caching this, as it might get called a lot when backwards compatibility
        # starts becoming a point of focus
        if self.version is not None:
            return self.version

        logger.info("Getting EDA version")
        version = self.get("core/about/version").json()["eda"]["version"].split("-")[0]
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
        type:       action type, possible values: ['create', 'delete']
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

    def add_delete_to_transaction(
        self, kind, name, group=CORE_GROUP, version=CORE_VERSION
    ):
        """
        Adds a 'delete' operation to the transaction

        Parameters
        ----------
        resource: the resource to be removed

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
                "namespace": "eda"
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
        if response.status_code == 204:
            logger.info("Validation successful")
            return True

        response = response.json()

        if "code" in response:
            message = f"{response['message']}"
            if "details" in response:
                message = f"{message} - {response['details']}"
            logger.warning(
                f"While validating a transaction item, the following validation error was returned (code {response['code']}): '{message}'"
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

        response = self.post("core/transaction/v1", payload).json()
        if "id" not in response:
            raise Exception(f"Could not find transaction ID in response {response}")

        transactionId = response["id"]

        logger.info(f"Waiting for transaction with ID {transactionId} to complete")
        result = self.get(
            f"core/transaction/v1/details/{transactionId}?waitForComplete=true&failOnErrors=true"
        ).json()

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
