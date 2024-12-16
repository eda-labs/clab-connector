# Containerlab EDA Connector tool

> :warning: **Made for EDA version 24.8.1**

There are two ways of creating a network and experiment with the functions that EDA provides. The first one is having real hardware, and the second one is the sandbox system. Both approaches have drawbacks, however: real hardware is sometimes difficult to come by and lab space / lab installment is difficult to set up and maintain - especially for large setups. The sandbox system is very flexible, although it is much more difficult to add secondary containers such as authentication servers, linux testboxes, or establishing external connectivity.

[Containerlab](https://containerlab.dev/) provides a very elegant solution to these problems, and this tool aims to provide a smooth experience for onboarding a containerlab topology into the EDA application. It is not a replacement for containerlab (so it won't define architectures for you - although some [examples](./example-topologies/) are provided in this repository), nor is it an extension of containerlab. This tool will not check whether the containerlab setup has been named correctly, or is ready to accept configuration from EDA. It is however created to work with a brand new containerlab setup that has not been touched manually.

## Check this first!

Below is a list of prerequisites before you can run the script. Please check them first. If you have checked all these prerequisites and the script is still not working correctly, please create a Github issue or [mail me](mailto:zeno.dhaene@nokia.com). 
- your EDA setup should be set up without simulation. This requires a special parameter when EDA is initially installed. **This tool will not work with a 'typical' installation**
- you should be able to ping your containerlab's management IP from your EDA node(s)
- the containerlab should be deployed with the required [startup configuration](./startup-configurations/)
- this program does not use the proxy (e.g. `$http_proxy`) variables. Instead, optional arguments were provided if you want to specify a proxy to reach your FSS. Note that they have not been tested very well, so please reach out if it's not working as expected
- the software image for your node must be uploaded first using the template below (replace the version numbers as necessary). I plan to include this step in this tool, but it has not yet been done.
- change the password of the default user that connects to the remote nodes

```yaml
---
apiVersion: artifacts.eda.nokia.com/v1
kind: Artifact
metadata:
  name: srlinux-24.7.1-bin
spec:
  repo: srlimages
  filePath: srlinux.bin
  remoteFileUrl:
    fileUrl: http://<http-server>:8080/SRLinux/srlinux-24.7.1-330.bin
---
apiVersion: artifacts.eda.nokia.com/v1
kind: Artifact
metadata:
  name: srlinux-24.7.1-md5
spec:
  repo: srlimages
  filePath: srlinux.md5
  remoteFileUrl:
    fileUrl: http://<http-server>:8080/SRLinux/srlinux-24.7.1-330.bin.md5
```

Apply this configuration on EDA with the `kubectl apply -f artifacts.yaml` command. 

## Installation

1. Create a new Python environment: 
    
    `python3 -m venv venv/`
2. Activate the Python environment

    `source venv/bin/activate`
3. Upgrade pip

    `python -m pip install --upgrade pip`
4. Install the required python modules

    `python -m pip install -r requirements.txt`
5. Run the tool

    `python eda_containerlab_connector.py --help`

## Running the tool

The video below shows off how the tool can be run:

![Instruction video](./assets/demo.mp4)

## Requesting support

You can request support through the Gitlab issues, via Discord, or personally via Teams or Mail. Note that you can run the script with the flag `-l INFO` or `-l DEBUG` flag for greater detail in where the script is failing.