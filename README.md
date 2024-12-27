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
- **Containerlab Configuration:**
  - Deployed with the required [startup configurations](./startup-configurations/).
- **srlinux YANG Models:**
  - The `srlinux-yang-models` for your specific SR Linux version must be uploaded to EDA. By default, `srlinux-yang-models` for SR Linux version `24.10.1` are installed. For other versions, you need to create and apply an Artifact.
  
    **Example Artifact YAML for SR Linux 24.7.1:**
    ~~~yaml
    apiVersion: artifacts.eda.nokia.com/v1
    kind: Artifact
    metadata:
      name: srlinux-ghcr-24.7.1
      namespace: eda-system
    spec:
      filePath: srlinux-24.7.1.zip
      remoteFileUrl:
        fileUrl: https://github.com/nokia/srlinux-yang-models/releases/download/v24.7.1/srlinux-24.7.1.zip
      repo: schemaprofiles
    ~~~
    
    Apply this configuration using:
    ~~~
    kubectl apply -f path/to/artifact.yaml
    ~~~
    
    You can find all YANG model releases [here](https://github.com/nokia/srlinux-yang-models/releases).
    


> [!NOTE]
> **Proxy Settings:** This tool does not utilize the system's proxy (`$http_proxy`) variables. Instead, it provides optional arguments to specify HTTP and HTTPS proxies for communicating with EDA.

## Installation

Follow these steps to set up the Containerlab EDA Connector tool:

> [!TIP]
> Using a virtual environment is recommended to avoid version conflicts with global Python packages.


1. **Create a Virtual Environment:**

    ```
    python3 -m venv venv/
    ```


2. **Activate the Virtual Environment:**

    
    ```
    source venv/bin/activate
    ```


3. **Upgrade pip:**

    ```
    python -m pip install --upgrade pip
    ```

4. **Install Required Python Modules:**

    ```
    python -m pip install -r requirements.txt
    ```

5. **Verify Installation:**

    ```
    python eda_containerlab_connector.py --help
    ```

## Usage

The tool offers two primary subcommands: `integrate` and `remove`.

### Integrate Containerlab with EDA

Integrate your Containerlab topology into EDA:

```
python eda_containerlab_connector.py integrate \
    --topology-file path/to/topology.yaml \
    --eda-url https://eda.example.com \
    --eda-user admin \
    --eda-password yourpassword \
    --http-proxy http://proxy.example.com:8080 \
    --https-proxy https://proxy.example.com:8443 \
    --verify
```

### Remove Containerlab Integration from EDA

Remove the previously integrated Containerlab topology from EDA:

```
python eda_containerlab_connector.py remove \
    --topology-file path/to/topology.yaml \
    --eda-url https://eda.example.com \
    --eda-user admin \
    --eda-password yourpassword
```

> [!NOTE]
> **Logging Levels:** Use the `--log-level` flag to set the desired logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). For example, `--log-level DEBUG` provides detailed logs for troubleshooting.

### Example Command

```
python eda_containerlab_connector.py integrate -t example-topology.yaml -e https://eda.example.com -u admin -p adminpassword -l INFO
```

## Example Topologies

Explore the [example-topologies](./example-topologies/) directory for sample Containerlab topology files to get started quickly.

## Instruction video

The video below shows off how the tool can be run:

<p align="center">
  <video width="100%" controls>
    <source src="./assets/demo.mp4" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>

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

