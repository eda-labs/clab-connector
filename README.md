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
> **Hardware License:** A valid **`hardware license` for EDA version 24.12.1** is mandatory for using this connector tool.

## Prerequisites

Before running the Containerlab EDA Connector tool, ensure the following prerequisites are met:

- **EDA Setup:**
  - Installed without simulation (`Simulate=False`).
  - Contains a valid `hardware license` for version 24.12.1.
- **Network Connectivity:**
  - EDA nodes can ping the Containerlab's management IP.
- **Containerlab:**
  - Minimum required version - `v0.62.2`
- **kubectl:**
  - You must have `kubectl` installed and configured to connect to the same Kubernetes cluster that is running EDA. The connector will use `kubectl apply` in the background to create the necessary `Artifact` resources.


> [!NOTE]
> **Proxy Settings:** This tool does utilize the system's proxy (`$HTTP_PROXY` and `$HTTPS_PROXY` ) variables.

## Installation

Follow these steps to set up the Containerlab EDA Connector tool:

> [!TIP]
> **Why uv?**
> [uv](https://docs.astral.sh/uv) is a single, ultra-fast tool that can replace `pip`, `pipx`, `virtualenv`, `pip-tools`, `poetry`, and more. It automatically manages Python versions, handles ephemeral or persistent virtual environments (`uv venv`), lockfiles, and often runs **10–100× faster** than pip installs.

1. **Install uv** (no Python needed):

    ```
    # On Linux and macOS
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2. **Install clab-connector**
    ```
    uv tool install git+https://github.com/eda-labs/clab-connector.git
    ```

3. **Run the Connector**

    ```
    clab-connector --help
    ```

> [!TIP]
> Upgrade clab-connector to the latest version using `uv tool upgrade clab-connector`.

### Alternative: Using pip

If you’d rather use pip or can’t install uv:

1. **Create & Activate a Virtual Environment after cloning**:

    ```
    python -m venv venv
    source venv/bin/activate
    ```

2. **Install Your Project** (which reads `pyproject.toml` for dependencies):

    ```
    pip install .
    ```

3. **Run the Connector**:

    ```
    clab-connector --help
    ```



## Usage

The tool offers two primary subcommands: `integrate` and `remove`.

#### Integrate Containerlab with EDA

To integrate your Containerlab topology with EDA you need to get a path to the `topology-data.json` file created by Containerlab when it deploys the lab. This file is located in the Containerlab's Lab Directory as described in the [documentation](https://containerlab.dev/manual/conf-artifacts/). With the path to the topology data file is known, you can use the following command to integrate the Containerlab topology with EDA:

```
clab-connector integrate \
--topology-data path/to/topology-data.json \
--eda-url https://eda.example.com \
--eda-user youruser \
--eda-password yourpassword \
```

#### Remove Containerlab Integration from EDA

Remove the previously integrated Containerlab topology from EDA:

```
clab-connector remove \
    --topology-data path/to/topology-data.json \
    --eda-url https://eda.example.com \
    --eda-user youruser \
    --eda-password yourpassword
```

| Option              | Required | Default   | Description                                                            |
|---------------------|----------|-----------|------------------------------------------------------------------------|
| `--topology-data`, `-t` | Yes      | None      | Path to the Containerlab topology data JSON file                        |
| `--eda-url`, `-e`   | Yes      | None      | EDA deployment hostname or IP address                                   |
| `--eda-user`        | No       | admin     | EDA username                                                            |
| `--eda-password`    | No       | admin     | EDA password                                                            |
| `--log-level`, `-l` | No       | WARNING   | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL)                       |
| `--log-file`        | No       | False     | Optional log file path                                                  |
| `--verify`          | No       | False     | Enable certificate verification for EDA                                 |


#### Export a lab from EDA to Containerlab

```
clab-connector export-lab \
    --namespace eda
```

| Option              | Required | Default   | Description                                                            |
|---------------------|----------|-----------|------------------------------------------------------------------------|
| `--namespace`, `-n` | Yes      | None      | Namespace in which the lab is deployed in EDA                          |
| `--output`, `-o`    | No       | None      | Output .clab.yaml file path                                            |
| `--log-level`, `-l` | No       | WARNING   | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL)                      |
| `--log-file`        | No       | False     | Optional log file path                                                 |

#### Generate CR YAML Manifests
The `generate-crs` command allows you to generate all the CR YAML manifests that would be applied to EDA—grouped by category. By default all manifests are concatenated into a single file. If you use the --separate flag, the manifests are written into separate files per category (e.g. `artifacts.yaml`, `init.yaml`, `node-security-profile.yaml`, etc.).


##### Combined file example:
```
clab-connector generate-crs \
  --topology-data path/to/topology-data.json \
  --output all-crs.yaml
```
##### Separate files example:
```
clab-connector generate-crs \
  --topology-data path/to/topology-data.json \
  --separate \
  --output manifests
```



### Example Command

```
clab-connector -l INFO integrate -t topology-data.json -e https://eda.example.com
```

## Example Topologies

Explore the [example-topologies](./example-topologies/) directory for sample Containerlab topology files to get started quickly.

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
