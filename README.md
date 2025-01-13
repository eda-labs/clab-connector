# Containerlab EDA Connector Tool

Integrate your [Containerlab](https://containerlab.dev/) topology seamlessly with [EDA (Event-Driven Automation)](https://docs.eda.dev) to streamline network automation and management.

## Overview

There are two primary methods to create and experiment with network functions provided by EDA:

1. **Real Hardware:** Offers robust and reliable performance but can be challenging to acquire and maintain, especially for large-scale setups.
2. **Sandbox System:** Highly flexible and cost-effective but limited in adding secondary containers like authentication servers or establishing external connectivity.

[Containerlab](https://containerlab.dev/) bridges these gaps by providing an elegant solution for network emulation using container-based topologies. This tool enhances your Containerlab experience by automating the onboarding process into EDA, ensuring a smooth and efficient integration.

## 🚨 Important Requirements

> [!IMPORTANT]
> **EDA Installation Mode:** This tool **requires EDA to be installed with `Simulate=False`**. Ensure that your EDA deployment is configured accordingly.
>
> **Hardware License:** A valid **`hardware license` for EDA version 24.12.0** is mandatory for using this connector tool.

## Prerequisites

Before running the Containerlab EDA Connector tool, ensure the following prerequisites are met:

- **EDA Setup:**
  - Installed without simulation (`Simulate=False`).
  - Contains a valid `hardware license` for version 24.12.0.
- **Network Connectivity:**
  - EDA nodes can ping the Containerlab's management IP.
- **Containerlab:**
  - Minimum required version - `v0.61.0`
- **kubectl:**
  - You must have `kubectl` installed and configured to connect to the same Kubernetes cluster that is running EDA. The connector will use `kubectl apply` in the background to create the necessary `Artifact` resources.

> [!TIP]
> **Network Connectivity between Kind and Containerlab:**
>
> If you're running EDA in KinD (Kubernetes in Docker) and Containerlab on the same host, you need to allow communication between containerlab and kind docker networks:
>
> ```bash
> sudo iptables -I DOCKER-USER 2 \
> -o $(sudo docker network inspect kind -f '{{.Id}}' | cut -c 1-12 | awk '{print "br-"$1}') \
> -m comment --comment "allow communications to kind bridge" -j ACCEPT
> ```

> [!NOTE]
> **Proxy Settings:** This tool does not utilize the system's proxy (`$http_proxy`) variables. Instead, it provides optional arguments to specify HTTP and HTTPS proxies for communicating with EDA.

## Installation

Follow these steps to set up the Containerlab EDA Connector tool:

> [!TIP]
> **Why uv?**
> [uv](https://docs.astral.sh/uv) is a single, ultra-fast tool that can replace `pip`, `pipx`, `virtualenv`, `pip-tools`, `poetry`, and more. It automatically manages Python versions, handles ephemeral or persistent virtual environments (`uv venv`), lockfiles, and often runs **10–100× faster** than pip installs.

1. **Install uv** (no Python or Rust needed):

    ```
    # On macOS and Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2. **(Optional) Create a Persistent Virtual Environment with uv**:

    ```
    uv venv
    ```

    This pins a Python version (if you haven't installed one yet) and creates a `.venv/` folder.

3. **Run the Connector** (uv automatically installs dependencies in a venv from `pyproject.toml`):

    ```
    uv run python eda_containerlab_connector.py --help
    ```

## Alternative: Using pip

If you’d rather use pip or can’t install uv:

1. **(Optional) Create & Activate a Virtual Environment**:

    ```
    python -m venv venv
    source venv/bin/activate
    ```

2. **Install Your Project** (which reads `pyproject.toml` for dependencies):

    ```
    python -m pip install --upgrade pip
    pip install .
    ```

3. **Run the Connector**:

    ```
    python eda_containerlab_connector.py --help
    ```

### Quick try

With either uv or pip, you can now run:

```
python eda_containerlab_connector.py <subcommand> [options]
```

Or, using uv:

```
uv run python eda_containerlab_connector.py <subcommand> [options]
```

## Usage

The tool offers two primary subcommands: `integrate` and `remove`.

### Integrate Containerlab with EDA

Integrate your Containerlab topology into EDA:

```
python eda_containerlab_connector.py --verify integrate \
--topology-file path/to/topology-data.json \
--eda-url https://eda.example.com \
--eda-user admin \
--eda-password yourpassword \ 
--http-proxy http://proxy.example.com:8080 \
--https-proxy https://proxy.example.com:8443
```

### Remove Containerlab Integration from EDA

Remove the previously integrated Containerlab topology from EDA:

```
python eda_containerlab_connector.py remove \
    --topology-file path/to/topology-data.json \
    --eda-url https://eda.example.com \
    --eda-user admin \
    --eda-password yourpassword
```

> [!NOTE]
> **Logging Levels:** Use the `--log-level` flag to set the desired logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). For example, `--log-level DEBUG` provides detailed logs for troubleshooting.

### Example Command

```
python eda_containerlab_connector.py -l INFO integrate -t topology-data.json -e https://eda.example.com 
```

## Example Topologies

Explore the [example-topologies](./example-topologies/) directory for sample Containerlab topology files to get started quickly.

## Instruction video

The video below shows off how the tool can be run:

<a href="./assets/demo.mp4">View demo video</a>

## Requesting Support

If you encounter issues or have questions, please reach out through the following channels:

- **GitHub Issues:** [Create an issue](https://github.com/eda-labs/clab-connector/issues) on GitHub.
- **Discord:** Join our [Discord community](https://eda.dev/discord)

> [!TIP]
> Running the script with `-l INFO` or `-l DEBUG` flags can provide additional insights into any failures or issues.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your enhancements.

## Acknowledgements

- [Containerlab](https://containerlab.dev/) for providing an excellent network emulation platform.
- [EDA (Event-Driven Automation)](https://docs.eda.dev/) for the robust automation capabilities.
