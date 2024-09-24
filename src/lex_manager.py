#!/usr/bin/env python

##########################################################################
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
##########################################################################
"""Lex Model Building Service helper script

Used to import/export/delete Lex bots and associated resources
(i.e. intents, slot types).

Can be run as a shell script or used as a Lambda Function for CloudFormation
Custom Resources.
"""

import logging
import json

from lex_utils_v2 import LexBotImporter, LexBotExporter, LexBotCreater, LexBotDeleter, LexBotVersionManager, LexBotValidator

DEFAULT_LOGGING_LEVEL = logging.INFO
logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=DEFAULT_LOGGING_LEVEL
)
logger = logging.getLogger(__name__)
logger.setLevel(DEFAULT_LOGGING_LEVEL)

def import_bot(bot_name=None, ticket=None, environment=None, bot_source_version='DRAFT',bot_alias_name=None,delete_old_version_flag='true'):
    bot_importer = LexBotImporter(
        bot_name=bot_name,
        ticket=ticket,
        environment=environment,
        #bot_role_name=bot_role_name,
        bot_source_version=bot_source_version,
        bot_alias_name=bot_alias_name,
        delete_old_version_flag=delete_old_version_flag,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )
    bot_import_status = bot_importer.import_bot()

    return bot_import_status

def delete_old_bot_version(bot_name=None, ticket=None, environment=None, bot_alias_name=None):
    bot_version_manager = LexBotVersionManager(
        bot_name=bot_name,
        ticket=ticket,
        environment=environment,
        bot_alias_name=bot_alias_name,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )
    bot_delete_old_version_status = bot_version_manager.delete_old_bot_version()

    return bot_delete_old_version_status

def export_bot(bot_name=None, ticket=None, environment=None, bot_version='DRAFT'):
    bot_exporter = LexBotExporter(
        bot_name=bot_name,
        ticket=ticket,
        environment=environment,
        bot_version=bot_version,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )

    bot_export_status = bot_exporter.export_bot()

    return bot_export_status

def create_bot(bot_name=None, ticket=None, environment=None, bot_alias_name=None, bot_role_name=None):
    bot_creater = LexBotCreater(
        bot_name=bot_name,
        ticket=ticket,
        environment=environment,
        bot_role_name=bot_role_name,
        bot_alias_name=bot_alias_name,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )

    bot_create_status = bot_creater.create_bot()

    return bot_create_status

def delete_bot(bot_name=None, ticket=None, environment=None):
    bot_deleter = LexBotDeleter(
        bot_name=bot_name,
        ticket=ticket,
        environment=environment,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )
    bot_delete_status = bot_deleter.delete_bot()

    return bot_delete_status

def validate_bot(bot_name=None):
    bot_validator = LexBotValidator(
        bot_name=bot_name,
        logging_level=DEFAULT_LOGGING_LEVEL,
    )
    bot_validate_status = bot_validator.validate_bot()

    return bot_validate_status

def get_parsed_args():
    """ Parse arguments passed when running as a shell script
    """
    parser = argparse.ArgumentParser(
        description='Lex bot manager. Import, export or delete a Lex bot.'
            ' Used to import/export/delete Lex bots and associated resources'
            ' (i.e. intents, slot types).'
    )
    """format_group = parser.add_mutually_exclusive_group()"""
    format_group = parser.add_argument_group()
    format_group.add_argument('-i', '--importbot',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botname',
        help='Import bot as LEXJSON files from Disk into account'
    )
    format_group.add_argument('-r', '--botrolename',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botrolename',
        help='Import bot role name'
    )
    format_group.add_argument('-s', '--botsourceversion',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botsourceversion',
        help='Import bot source version. Defaults to DRAFT'
    )
    format_group.add_argument('-w', '--deleteoldbotversion',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='deleteoldbotversion',
        help='Flag to delete old bot version. Defaults to true'
    )
    format_group.add_argument('-a', '--botaliasname',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botaliasname',
        help='Import bot alias name to associate with new version. Defaults to DRAFT'
    )
    format_group.add_argument('-e', '--exportbot',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botname',
        help='Export bot as LEXJSON files from account to Disk'
    )
    format_group.add_argument('-c', '--createbot',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botname',
        help='Create bot in account'
    )
    format_group.add_argument('-v', '--botversion',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botversion',
        help='Export bot version. Defaults to DRAFT'
    )
    format_group.add_argument('-d', '--deletebot',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botname',
        help='Deletes the bot passed as argument and its associated resources.'
    )
    format_group.add_argument('-t', '--ticket',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='ticket',
        help='ticket for bot resources to export as well as import.'
    )
    format_group.add_argument('-n', '--environment',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='environment',
        help='environment for bot resources to export as well as import.'
    )
    format_group.add_argument('-l', '--validatebot',
        nargs='?',
        default=argparse.SUPPRESS,
        metavar='botname',
        help='Validates the bot passed as argument.'
    )

    args = parser.parse_args()
    if not bool(vars(args)):
        parser.print_help()
        sys.exit(1)

    return args

def main(argv):
    """ Main function used when running as a shell script
    """
    parsed_args = get_parsed_args()

    if 'importbot' in parsed_args:
        try:
            # using the keyword import is problematic
            # turning to dict as workaround
            import_bot(bot_name=parsed_args.importbot, ticket=parsed_args.ticket, environment=parsed_args.environment, bot_source_version=parsed_args.botsourceversion, bot_alias_name=parsed_args.botaliasname)
        except Exception as e:
            error = 'failed to import bot {}'.format(e)
            logging.error(error);
            sys.exit(1)

    if 'exportbot' in parsed_args:
        try:
            export_bot(bot_name=parsed_args.exportbot, ticket=parsed_args.ticket, environment=parsed_args.environment, bot_version=parsed_args.botversion)
        except Exception as e:
            error = 'failed to export bot {}'.format(e)
            logging.error(error);
            sys.exit(1)

    if 'createbot' in parsed_args:
        try:
            create_bot(bot_name=parsed_args.createbot, ticket=parsed_args.ticket, environment=parsed_args.environment, bot_role_name=parsed_args.botrolename, bot_alias_name=parsed_args.botaliasname)
        except Exception as e:
            error = 'failed to create bot {}'.format(e)
            logging.error(error);
            sys.exit(1)

    if 'deletebot' in parsed_args:
        try:
            delete_bot(bot_name=parsed_args.deletebot, ticket=parsed_args.ticket, environment=parsed_args.environment)
        except Exception as e:
            error = 'failed to delete bot {}'.format(e)
            logging.error(error);
            sys.exit(1)

    if 'validatebot' in parsed_args:
        try:
            validate_bot(bot_name=parsed_args.validatebot)
        except Exception as e:
            error = 'failed to validate bot {}'.format(e)
            logging.error(error);
            sys.exit(1)

    if 'deleteoldbotversion' in parsed_args:
        try:
            delete_old_bot_version(bot_name=parsed_args.deleteoldbotversion, ticket=parsed_args.ticket, environment=parsed_args.environment, bot_alias_name=parsed_args.botaliasname)
        except Exception as e:
            error = 'failed to delete old bot version {}'.format(e)
            logging.error(error);
            sys.exit(1)

if __name__ == '__main__':
    #from IPython.core.debugger import Pdb ; Pdb().set_trace() # XXX
    import sys
    import argparse
    # test lambda handler from shell with -t
    if len(sys.argv) > 1 and sys.argv[1] == '-t':
        test_handler()
    # otherwise call main and parse arguments
    else:
        main(sys.argv)