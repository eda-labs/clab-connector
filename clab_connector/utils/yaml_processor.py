import logging

import yaml

from clab_connector.utils.constants import SUBSTEP_INDENT

INLINE_LIST_LENGTH = 2

logger = logging.getLogger(__name__)


class YAMLProcessor:
    class CustomDumper(yaml.SafeDumper):
        """
        Custom YAML dumper that adjusts the indentation for lists and maintains certain lists in inline format.
        """

    def custom_list_representer(self, dumper, data):
        # Check if we are at the specific list under 'links' with 'endpoints'
        if (
            len(data) == INLINE_LIST_LENGTH
            and isinstance(data[0], str)
            and ":" in data[0]
        ):
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True
            )
        else:
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=False
            )

    def custom_dict_representer(self, dumper, data):
        return dumper.represent_dict(data.items())

    def __init__(self):
        # Assign custom representers to the CustomDumper class
        self.CustomDumper.add_representer(list, self.custom_list_representer)
        self.CustomDumper.add_representer(dict, self.custom_dict_representer)

    def load_yaml(self, yaml_str):
        try:
            # Load YAML data
            data = yaml.safe_load(yaml_str)
            return data

        except yaml.YAMLError as e:
            logger.error(f"Error loading YAML: {e!s}")
            raise

    def save_yaml(self, data, output_file, flow_style=None):
        try:
            # Save YAML data
            with open(output_file, "w") as file:
                if flow_style is None:
                    yaml.dump(
                        data,
                        file,
                        Dumper=self.CustomDumper,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )
                else:
                    yaml.dump(data, file, default_flow_style=False, sort_keys=False)

            logger.info(f"{SUBSTEP_INDENT}YAML file saved as '{output_file}'.")

        except OSError as e:
            logger.error(f"Error saving YAML file: {e!s}")
            raise
