class SubCommand:
    # name of the subparser of this command
    PARSER_NAME = None
    PARSER_ALIASES = [PARSER_NAME]

    def run(self, args):
        """
        Run the program with the arguments specified for this sub-command

        Parameters
        ----------
        args: input arguments returned by the argument parser
        """
        raise Exception(f"Run method not implemented for subparser {args.subparser}")

    def create_parser(self, subparsers):
        """
        Creates a subparser with arguments specific to this subcommand of the program

        Parameters
        ----------
        subparsers: the subparsers object for the parent command

        Returns
        -------
        An argparse subparser
        """
        raise Exception("get_parser method not implemented")
