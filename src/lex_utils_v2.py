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
""" Lex Model Building Service Helper Classes
"""
# TODO need to DRY codebase
import logging
import json
import copy
import time
import requests
import zipfile
import os
import glob
import traceback
import boto3
from collections import Counter

DEFAULT_LOGGING_LEVEL = logging.WARNING
logging.basicConfig(format='[%(levelname)s] %(message)s', level=DEFAULT_LOGGING_LEVEL)
logger = logging.getLogger(__name__)
lex_root_dir = "lex_bots"

class LexClient():
    def __init__(self, profile_name=''):
        self._profile_name = profile_name

        if self._profile_name:
            try:
                self._lex_client = (
                    boto3.session
                    .Session(profile_name=self._profile_name).client('lexv2-models')
                )
            except Exception as e:
                logger.warning(
                    'Failed to create lexv2 boto3 client using profile: {}'.format(
                        profile_name
                    )
                )
                logger.warning(e)
                raise
        else:
            try:
                self._lex_client = boto3.client('lexv2-models')
            except Exception as e:
                logger.warning('Failed to lexv2 create boto3 client')
                logger.warning(e)
                raise

    @property
    def client(self):
        return self._lex_client

class IAMClient():
    def __init__(self, profile_name=''):
        self._profile_name = profile_name

        if self._profile_name:
            try:
                self._iam_client = (
                    boto3.session
                    .Session(profile_name=self._profile_name).client('iam')
                )
            except Exception as e:
                logger.warning(
                    'Failed to create iam boto3 client using profile: {}'.format(
                        profile_name
                    )
                )
                logger.warning(e)
                raise
        else:
            try:
                self._iam_client = boto3.client('iam')
            except Exception as e:
                logger.warning(e)
                logger.warning('Failed to iam create boto3 client')
                raise

    @property
    def client(self):
        return self._iam_client

class CFNClient():
    def __init__(self, profile_name=''):
        self._profile_name = profile_name

        if self._profile_name:
            try:
                self._cfn_client = (
                    boto3.session
                    .Session(profile_name=self._profile_name).client('cloudformation')
                )
            except Exception as e:
                logger.warning(
                    'Failed to create cloudformation boto3 client using profile: {}'.format(
                        profile_name
                    )
                )
                logger.warning(e)
                raise
        else:
            try:
                self._cfn_client = boto3.client('cloudformation')
            except Exception as e:
                logger.warning('Failed to cloudformation create boto3 client')
                logger.warning(e)
                raise

    @property
    def client(self):
        return self._cfn_client

class LexBotExporter():
    """Class to export a Lex bot definition from an AWS account

    :param bot_name: Lex bot name to import
    :type botn_name: str

    :param bot_version: Lex bot version to import
    :type bot_version: str

    :param lex_iam_role_arn: IAM role ARN to substitute as the bot role
        if empty, the arn will not be substituted
    :type lex_iam_role_arn: str

    :param lambda_arn: Lambda ARN to substitute in *all* code hooks
        if empty, the arn will not be substituted
    :type lambda_arn: str

    :param profile_name: AWS cli/SDK profile credentials to use.
        If empty, the standard credential resolver will be used.
    :type profile_name: str
    """
    def __init__(
            self,
            bot_name,
            ticket,
            environment,
            bot_version='DRAFT',
            lambda_arn=None,
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL
        ):
        self._bot_name = bot_name
        self._ticket = ticket
        self._environment = environment
        self._bot_version = bot_version
        self._lambda_arn = lambda_arn

        self._get_bot_response = {}
        self._get_bot_alias_response = {}

        logger.setLevel(logging_level)
        logging.getLogger('botocore').setLevel(logging_level)

        self._lex_client = LexClient(profile_name=profile_name).client
        get_lex_bot = LexBotGetter(bot_name=bot_name,ticket=ticket,environment=environment,profile_name=profile_name)
        self._bot_id, self._bot_latest_version = get_lex_bot.bot_id_version
        self._current_bot_name = get_lex_bot.current_bot_name
        #os.chdir('../')

    @property
    def bot_name(self):
        return self._bot_name
    
    @property
    def ticket(self):
        return self._ticket

    @property
    def environment(self):
        return self._environment

    @property
    def bot_version(self):
        return self._bot_version

    @staticmethod
    def indent_json_files(dir, bot_name):
        for root, dirs, files in os.walk(dir):
            for file in files:
                if file.endswith('.json'):
                    filepath = os.path.join(root, file)
                    logger.info('Formatting JSON file : ' + filepath)
                    with open(filepath, 'r', encoding='utf-8') as jsonfile:
                        try:
                            jsondata = json.load(jsonfile)
                        except valueError as e:
                            logger.warning('Error parsing JSON file.')
                            continue
                        if file == "Bot.json":
                            jsondata['name'] = bot_name
                        indented_jsondata = json.dumps(jsondata, indent=4, sort_keys=True)
                    with open(filepath, 'w', encoding='utf-8') as jsonfile:
                        jsonfile.write(indented_jsondata)

    @staticmethod
    def remove_existing_bot_defn(dir):
        for root, dirs, files in os.walk(dir, topdown=False):
            for filename in files:
                filepath = os.path.join(root, filename)
                logger.info('Removing file : ' + filepath)
                os.remove(filepath)
            for directory in dirs:
                dirpath = os.path.join(root, directory)
                logger.info('Removing dir : ' + dirpath)
                os.rmdir(dirpath)
        os.rmdir(dir)


    def _export_bot_zip(self):
        try:
            #bot_id = self._get_bot_id()
            logger.info('Retrieved Lex bot id : ' + self._bot_id)
            create_export_bot_response = self._lex_client.create_export(
                resourceSpecification={
                    'botExportSpecification': {
                        'botId': self._bot_id,
                        'botVersion': self._bot_version
                    }
                },
                fileFormat='LexJson'
            )
            export_id = create_export_bot_response['exportId']
            logger.info('Waiting on bot export : ' + export_id)
            bot_export_waiter = self._lex_client.get_waiter('bot_export_completed')
            bot_export_waiter.wait(
                exportId=export_id,
                WaiterConfig={
                    'Delay': 20,
                    'MaxAttempts': 15
                }
            )
            logger.info('Completed bot export : ' + export_id)
            describe_export_bot_response = self._lex_client.describe_export(
                exportId=export_id
            )
            self._get_bot_response = describe_export_bot_response['exportStatus']
            download_url = describe_export_bot_response['downloadUrl']
            bot_download_response = requests.get(download_url,timeout=300)
            if bot_download_response.status_code == 200:
                if ((lex_root_dir == 'lex_bots') and os.path.exists(lex_root_dir+'/'+self._bot_name)):
                    self.remove_existing_bot_defn(lex_root_dir+'/'+self._bot_name)
                with open(self._bot_name+'.zip', 'wb') as f:
                    f.write(bot_download_response.content)
                with zipfile.ZipFile(self._bot_name+'.zip',"r") as zip_ref:
                    zip_ref.extractall(lex_root_dir)
                os.rename(lex_root_dir+'/'+self._current_bot_name,lex_root_dir+'/'+self._bot_name)
                self.indent_json_files(lex_root_dir+'/'+self._bot_name,self._bot_name)
                if os.path.exists(self._bot_name+'.zip'):
                    os.remove(self._bot_name+'.zip')
            logger.info('Downloaded exported bot : ' + export_id)
            delete_export_bot_response = self._lex_client.delete_export(
                exportId=export_id
            )

        except Exception as e:
            logger.warning(e)
            logger.warning('Lex export_bot call failed')
            raise

        return self._get_bot_response

    def export_bot(self):
        """ Performs a Lex get_bot API call

        :returns: the response of Lex get_bot with immutable/unneeded fields
            filtered out so that it can be fed to create/update calls
            returned object contains the exported resources in this structure:
            {bot:  {}, intents: [], slot-types: []}
        :rtype: dict
        """

        logger.info('exporting bot {}'.format(self._current_bot_name))
        self._get_bot = self._export_bot_zip()
        """self._get_bot = self._export_bot()
        self._bot_intents = self._export_bot_intents()
        self._slot_types = self._export_bot_slot_types()"""
        logger.info('successfully exported bot definition')

        return dict(
            bot=self._get_bot
        )

class LexBotImporter():
    def __init__(
            self,
            bot_name,
            ticket,
            environment,
            #bot_role_name,
            bot_source_version,
            bot_alias_name,
            delete_old_version_flag,
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL,
        ):
        self._bot_name = bot_name
        self._ticket = ticket
        self._environment = environment
        #self._bot_role_name = bot_role_name
        self._bot_source_version = bot_source_version
        self._bot_alias_name = bot_alias_name
        self._delete_old_version_flag = delete_old_version_flag

        logger.setLevel(logging_level)
        logging.getLogger('botocore').setLevel(logging_level)
        
        self._get_bot_response = {}
        self._lex_client = LexClient(profile_name=profile_name).client
        self._iam_client = IAMClient(profile_name=profile_name).client
        self._cfn_client = CFNClient(profile_name=profile_name).client
        
        get_lex_bot = LexBotGetter(bot_name=bot_name,ticket=ticket,environment=environment,bot_alias_name=environment+"-"+bot_alias_name,profile_name=profile_name)
        self._bot_id, self._bot_latest_version = get_lex_bot.bot_id_version
        self._current_bot_name = get_lex_bot.current_bot_name
        self._bot_alias_id = ''
        if (bot_alias_name != '' and bot_alias_name != None):
            self._bot_alias_id = get_lex_bot.bot_alias_id
        #os.chdir('../')

    @property
    def bot_name(self):
        return self._bot_name

    @property
    def ticket(self):
        return self._ticket

    @property
    def environment(self):
        return self._environment

    #@property
    #def bot_role_name(self):
    #    return self._bot_role_name

    @property
    def bot_source_version(self):
        return self._bot_source_version

    @property
    def bot_alias_name(self):
        return self._bot_alias_name

    @property
    def delete_old_version_flag(self):
        return self._delete_old_version_flag

    #def _get_role_arn(self):
    #    bot_role = self._iam_client.get_role(RoleName=self._bot_role_name)
    #    return bot_role['Role']['Arn']

    def _import_bot_zip(self):
        try:
            #bot_role_arn = self._get_role_arn()
            logger.info("Retrieved Bot role ARN from Role name.")
            bot_prefix_name=self._ticket+"-"+self._environment
            if (self._ticket == ""):
                bot_prefix_name=self._environment
            root_dir = lex_root_dir+'/'
            with zipfile.ZipFile(self._current_bot_name+'.zip', 'w', zipfile.ZIP_DEFLATED) as botzipfile:
                for root, dirs, files in os.walk(root_dir+self._bot_name+'/'):
                    for file in files:
                        if file == "Bot.json":
                            with open(os.path.join(root, file),'r',encoding='utf-8') as botjsonfile:
                                botdefndata = botjsonfile.read()
                            jsonbotdefndata = json.loads(botdefndata)
                            jsonbotdefndata['name'] = self._current_bot_name
                            with open(os.path.join(root, file),'w',encoding='utf-8') as botjsonfile:
                                botjsonfile.write(json.dumps(jsonbotdefndata, sort_keys=True))
                        botzipfile.write(os.path.join(root, file),bot_prefix_name+"-"+os.path.join(root, file).split(root_dir,1)[1])
                botzipfile.write(root_dir+'Manifest.json', os.path.basename('Manifest.json'))
            logger.info("Created zip of Bot to import.")
            create_upload_url_response = self._lex_client.create_upload_url()
            with open(self._current_bot_name+'.zip','rb') as botzipfile:
                try:
                    upload_response = requests.put(create_upload_url_response['uploadUrl'], data=botzipfile, timeout=300)
                    upload_response.raise_for_status()
                except Exception as err:
                    logger.error(err)
            describe_bot_response = self._lex_client.describe_bot(
                botId=self._bot_id
            )
            create_import_bot_response = self._lex_client.start_import(
                importId=create_upload_url_response['importId'],
                resourceSpecification={
                    'botImportSpecification': {
                        'botName': describe_bot_response['botName'],
                        'roleArn': describe_bot_response['roleArn'],
                        'dataPrivacy': describe_bot_response['dataPrivacy'],
                        'idleSessionTTLInSeconds': describe_bot_response['idleSessionTTLInSeconds'],
                    },
                },
                mergeStrategy='Overwrite'
            )
            logger.info("Uploaded bot zip. Waiting for import to complete.")
            import_id = create_import_bot_response['importId']
            bot_import_waiter = self._lex_client.get_waiter('bot_import_completed')
            bot_import_waiter.wait(
                importId=import_id,
                WaiterConfig={
                    'Delay': 20,
                    'MaxAttempts': 15
                }
            )
            describe_import_bot_response = self._lex_client.describe_import(
                importId=import_id
            )
            self._get_bot_response = describe_import_bot_response['importStatus']
            if describe_import_bot_response['importStatus'] == 'Completed':
                if os.path.exists(self._current_bot_name+'.zip'):
                    os.remove(self._current_bot_name+'.zip')
                logger.info('Completed import for bot name {}.'.format(
                    self._current_bot_name
                    )
                )
            
            delete_import_bot_response = self._lex_client.delete_import(
                importId=import_id
            )

            build_bot_response = self._lex_client.build_bot_locale(
                botId=self._bot_id,
                botVersion=self._bot_source_version,
                localeId='en_GB'
            )
            logger.info("Initiated Bot build. Waiting for Bot build to complete.")
            bot_build_waiter = self._lex_client.get_waiter('bot_locale_built')
            bot_build_waiter.wait(
                botId=self._bot_id,
                botVersion=self._bot_source_version,
                localeId='en_GB',
                WaiterConfig={
                    'Delay': 20,
                    'MaxAttempts': 15
                }
            )
            logger.info("Completed Bot build.")

            bot_version_manager = LexBotVersionManager(bot_name=self._bot_name,ticket=self._ticket,environment=self._environment,bot_alias_name=self._bot_alias_name,bot_source_version=self._bot_source_version)
            create_bot_version_response = bot_version_manager.create_bot_version()

            if (self._bot_alias_name != '' and self._bot_alias_name != None and self._bot_alias_id != ''):
                logger.info("Initiated association new Bot version "+create_bot_version_response['botVersion']+ " to alias "+self._environment+"-"+self._bot_alias_name)
                describe_bot_alias_response = self._lex_client.describe_bot_alias(
                    botAliasId=self._bot_alias_id,
                    botId=self._bot_id
                )
                associate_botversion_alias_response = self._lex_client.update_bot_alias(
                    botVersion=create_bot_version_response['botVersion'],
                    botAliasId=describe_bot_alias_response['botAliasId'],
                    botAliasName=describe_bot_alias_response['botAliasName'],
                    description= describe_bot_alias_response.get('description',''),
                    botId=describe_bot_alias_response['botId'],
                    botAliasLocaleSettings=describe_bot_alias_response.get('botAliasLocaleSettings',{'en_GB': {'enabled': True}}),
                    conversationLogSettings=describe_bot_alias_response.get('conversationLogSettings',{}),
                    sentimentAnalysisSettings=describe_bot_alias_response.get('sentimentAnalysisSettings',{'detectSentiment': False})
                )
                logger.info("Completed association new Bot version "+create_bot_version_response['botVersion']+ " to alias "+self._environment+"-"+self._bot_alias_name)
            else:
                logger.info("Not associated new Bot version "+create_bot_version_response['botVersion']+ " as the alias is either not provided or invalid")

        except Exception as e:
            logger.warning('Lex import_bot call failed')
            logger.warning(e)
            traceback.print_exc(limit=None, file=None, chain=True)
            raise

        return self._get_bot_response


    def import_bot(self):
        logger.info('importing bot {}'.format(
              self._current_bot_name
            )
        )
        self._import_bot_zip()
        logger.info('successfully imported bot and associated resources')

class LexBotValidator():
    def __init__(
            self,
            bot_name,
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL,
        ):
        self._bot_name = bot_name

        logger.setLevel(logging_level)
        logging.getLogger('botocore').setLevel(logging_level)
        
        self._validate_bot_response = {}

    @property
    def bot_name(self):
        return self._bot_name

    def _validate_bot(self):
        try:
            root_dir = lex_root_dir+'/'
            for root, dirs, files in os.walk(root_dir+self._bot_name+'/'):
                for file in files:
                    with open(os.path.join(root, file),'r',encoding='utf-8') as botjsonfile:
                        #botdefndata = botjsonfile.read()
                        jsonbotdefndata = json.load(botjsonfile)
                        self.get_duplicates(jsonbotdefndata,os.path.join(root, file),"")                            

        except Exception as e:
            logger.warning('Lex validate_bot call failed')
            logger.warning(e)
            traceback.print_exc(limit=None, file=None, chain=True)
            raise

        return self._validate_bot_response
    
    @staticmethod
    def get_duplicates(jsondata,path,parent_key=""):
        for key, value in jsondata.items():
            if isinstance(value, list):
                duplicates = [item for item, count in Counter(json.dumps(obj, sort_keys=True) for obj in value).items() if count > 1]
                if duplicates:
                    logger.info("duplicates found in file {} in key '{}.{}' {}".format(
                        path, parent_key, key, duplicates
                    ))
                    raise Exception("duplicates found in key '{}'".format(key))
                for index, item in enumerate(value):
                    if isinstance(item, list) or isinstance(item, dict):
                        current_key = f"{parent_key}.{key}[{index}]" if parent_key else f"{key}[{index}]"
                        LexBotValidator.get_duplicates(item,path,parent_key=current_key)

            elif isinstance(value, dict):
                current_key = f"{parent_key}.{key}" if parent_key else key
                LexBotValidator.get_duplicates(value,path,parent_key=current_key)


    def validate_bot(self):
        logger.info('valiadate bot {}'.format(
              self._bot_name
            )
        )
        self._validate_bot()
        logger.info('successfully validated bot and associated resources')

class LexBotVersionManager():
    def __init__(
            self,
            bot_name,
            ticket,
            environment,
            bot_alias_name,
            bot_source_version='DRAFT',
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL,
        ):
        self._bot_name = bot_name
        self._ticket = ticket
        self._environment = environment
        self._bot_alias_name = bot_alias_name
        self._bot_source_version = bot_source_version
        self._logging_level = logging_level

        #logger.setLevel(logging_level)
        #logging.getLogger('botocore').setLevel(logging_level)
        self._delete_bot_version_response = {}
        self._create_bot_version_response = {}
        self._lex_client = LexClient(profile_name=profile_name).client
        self._cfn_client = CFNClient(profile_name=profile_name).client
        get_lex_bot = LexBotGetter(bot_name=bot_name,ticket=ticket,environment=environment,bot_alias_name=environment+"-"+bot_alias_name,profile_name=profile_name)
        self._bot_id, self._bot_latest_version = get_lex_bot.bot_id_version
        self._current_bot_name = get_lex_bot.current_bot_name
        self._bot_alias_id = ''
        if (bot_alias_name != '' and bot_alias_name != None):
            self._bot_alias_id = get_lex_bot.bot_alias_id
                
        #os.chdir('../')

    @property
    def bot_name(self):
        return self._bot_name

    @property
    def ticket(self):
        return self._ticket

    @property
    def environment(self):
        return self._environment

    @property
    def bot_alias_name(self):
        return self._bot_alias_name

    @property
    def bot_source_version(self):
        return self._bot_source_version

    def _delete_old_bot_version(self):
        try:
            logger.setLevel(self._logging_level)
            logging.getLogger('botocore').setLevel(self._logging_level)
            list_bot_versions_response = {"botVersionSummaries": [],"nextToken":""}
            retry = 1
            maxRetries = 30
            version_count = 0
            while (list_bot_versions_response['botVersionSummaries'] == [] and retry <= maxRetries):
                logger.info("Retrieving Bot Versions from Bot Id. Page "+str(retry))
                if list_bot_versions_response['nextToken'] == "":
                    list_bot_versions_response = self._lex_client.list_bot_versions(
                        botId=self._bot_id,
                        sortBy={
                            'attribute': 'BotVersion',
                            'order': 'Ascending'
                        }
                    )
                else:
                    list_bot_versions_response = self._lex_client.list_bots(
                        botId=self._bot_id,
                        sortBy={
                            'attribute': 'BotVersion',
                            'order': 'Ascending'
                        },
                        nextToken = list_bot_versions_response['nextToken']
                    )
                retry = retry + 1
            cfn_stack_response = self._cfn_client.describe_stacks(StackName=self._environment+"-"+self._bot_alias_name)
            cfn_stack_outputs = cfn_stack_response["Stacks"][0]["Outputs"]
            cfn_bot_version = ''
            if self._ticket == '':
                for cfn_stack_output in cfn_stack_outputs:
                    keyName = cfn_stack_output["OutputKey"]
                    if keyName == "BotVersion":
                        cfn_bot_version = cfn_stack_output["OutputValue"]
                logger.info("Oldest CloudFormation Bot Version "+cfn_bot_version)
            bot_version_cntr = 0
            oldestBotVersion = list_bot_versions_response['botVersionSummaries'][bot_version_cntr]['botVersion']
            while (oldestBotVersion == cfn_bot_version and bot_version_cntr <= 10 and self._ticket == ''):
                bot_version_cntr = bot_version_cntr+1
                oldestBotVersion = list_bot_versions_response['botVersionSummaries'][bot_version_cntr]['botVersion']
            logger.info("Oldest Non CloudFormation Bot Version "+oldestBotVersion)
            logger.info("Latest Bot Version "+self._bot_latest_version)
            bot_active_versions_cnt = int(self._bot_latest_version) - int(oldestBotVersion) + 1
            logger.info("No. of Bot Versions active "+str(bot_active_versions_cnt))
            if (bot_active_versions_cnt >= 25):
                logger.info("Bot version limit reached. Deleting Oldest non cloudformation bot version "+oldestBotVersion)
                self._delete_bot_version_response = self._lex_client.delete_bot_version(
                    botId=self._bot_id,
                    botVersion=oldestBotVersion,
                    skipResourceInUseCheck=False
                )
                logger.info("Deleted Oldest non cloudformation bot version "+oldestBotVersion)
        except Exception as e:
            logger.warning(e)
            logger.warning('Lex delete old bot version call failed')
            raise
        return self._delete_bot_version_response

    def delete_old_bot_version(self):
        logger.info('Deleting old version for bot {}'.format(
              self._current_bot_name
            )
        )
        self._delete_old_bot_version()
        logger.info('successfully deleted old bot version')

    def _create_bot_version(self):
        try:
            logger.info("Initiated creation of new Bot version. Waiting for Bot version creation to complete.")
            self._create_bot_version_response = self._lex_client.create_bot_version(
                botId=self._bot_id,
                description='',
                botVersionLocaleSpecification={
                    'en_GB': {
                        'sourceBotVersion': self._bot_source_version
                    }
                }
            )
            

            bot_version_waiter = self._lex_client.get_waiter('bot_version_available')
            bot_version_waiter.wait(
                botId=self._bot_id,
                botVersion=self._create_bot_version_response['botVersion'],
                WaiterConfig={
                    'Delay': 20,
                    'MaxAttempts': 15
                }
            )
            logger.info("Completed creation of Bot version "+self._create_bot_version_response['botVersion'])
        except Exception as e:
            logger.warning(e)
            logger.warning('Lex delete old bot version call failed')
            raise
        return self._create_bot_version_response


    def create_bot_version(self):
        logger.info('Creating new version for bot {}'.format(
              self._current_bot_name
            )
        )
        self._create_bot_version()
        logger.info('successfully created new bot version')
        return self._create_bot_version_response

class LexBotGetter():
    """Class to export a Lex bot definition from an AWS account

    :param bot_name: Lex bot name to import
    :type botn_name: str

    :param bot_version: Lex bot version to import
    :type bot_version: str

    :param lex_iam_role_arn: IAM role ARN to substitute as the bot role
        if empty, the arn will not be substituted
    :type lex_iam_role_arn: str

    :param lambda_arn: Lambda ARN to substitute in *all* code hooks
        if empty, the arn will not be substituted
    :type lambda_arn: str

    :param profile_name: AWS cli/SDK profile credentials to use.
        If empty, the standard credential resolver will be used.
    :type profile_name: str
    """
    def __init__(
            self,
            bot_name,
            ticket,
            environment,
            bot_alias_name='',
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL
        ):
        self._profile_name = profile_name
        self._bot_name = bot_name
        self._ticket = ticket
        self._environment = environment
        self._bot_alias_name = bot_alias_name

        self._lex_client = LexClient(profile_name=profile_name).client

        self._current_bot_name=self._ticket+"-"+self._environment+"-"+self._bot_name
        if (self._ticket == ""):
            self._current_bot_name=self._environment+"-"+self._bot_name

        

    @property
    def bot_id_version(self):
        self._list_bots_response = {"botSummaries": [],"nextToken":""}
        retry = 1
        maxRetries = 30
        logger.info("log "+self._current_bot_name)
        self._bot_latest_version = 'DRAFT'
        while (self._list_bots_response['botSummaries'] == [] and retry <= maxRetries):
            logger.info("Retrieving Bot Id from Bot Name. Page "+str(retry))
            if self._list_bots_response['nextToken'] == "":
                self._list_bots_response = self._lex_client.list_bots(
                    sortBy={
                        'attribute': 'BotName',
                        'order': 'Ascending'
                    },
                    filters=[
                        {
                            'name': 'BotName',
                            'values': [self._current_bot_name],
                            'operator': 'EQ'
                        },
                    ]
                )
            else:
                self._list_bots_response = self._lex_client.list_bots(
                    sortBy={
                        'attribute': 'BotName',
                        'order': 'Ascending'
                    },
                    filters=[
                        {
                            'name': 'BotName',
                            'values': [self._current_bot_name],
                            'operator': 'EQ'
                        },
                    ],
                    nextToken = self._list_bots_response['nextToken']
                )
            retry = retry + 1
        self._bot_id = self._list_bots_response['botSummaries'][0]['botId']
        self._bot_latest_version = self._list_bots_response['botSummaries'][0].get('latestBotVersion','DRAFT')
        return self._bot_id, self._bot_latest_version

    @property
    def bot_alias_id(self):
        bot_id = self._bot_id
        self._bot_alias_id = ''
        self._list_bots_alias_response = {"botAliasSummaries": [],"nextToken":""}
        retry = 1
        maxRetries = 30
        while (self._list_bots_alias_response['botAliasSummaries'] == [] and retry <= maxRetries):
            logger.info("Retrieving Bot Alias Id from Bot Alias Name "+self._bot_alias_name+" for Bot Id "+bot_id+". Page "+str(retry))
            if self._list_bots_alias_response['nextToken'] == "":
                self._list_bots_alias_response = self._lex_client.list_bot_aliases(
                    botId=bot_id
                )
            else:
                self._list_bots_alias_response = self._lex_client.list_bot_aliases(
                    botId=bot_id,
                    nextToken = self._list_bots_alias_response['nextToken']
                )
            retry = retry + 1
        
        for index, botalias in enumerate(self._list_bots_alias_response['botAliasSummaries']):
            if (botalias['botAliasName'] == self._bot_alias_name):
                self._bot_alias_id = botalias['botAliasId']
        if self._bot_alias_id == '':
            logger.info("Bot Alias Name not found")
        else:
            logger.info("Retrieved Bot Alias Id from Bot Alias Name "+ self._bot_alias_id)
        return self._bot_alias_id

    @property
    def current_bot_name(self):
        return self._current_bot_name

class LexBotCreater():
    """Class to create a Lex bot definition in an AWS account

    :param bot_name: Lex bot name to import
    :type botn_name: str

    :param bot_version: Lex bot version to import
    :type bot_version: str

    :param lex_iam_role_arn: IAM role ARN to substitute as the bot role
        if empty, the arn will not be substituted
    :type lex_iam_role_arn: str

    :param lambda_arn: Lambda ARN to substitute in *all* code hooks
        if empty, the arn will not be substituted
    :type lambda_arn: str

    :param profile_name: AWS cli/SDK profile credentials to use.
        If empty, the standard credential resolver will be used.
    :type profile_name: str
    """
    def __init__(
            self,
            bot_name,
            environment,
            ticket,
            bot_role_name,
            bot_alias_name,
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL
        ):
        self._bot_name = bot_name
        self._bot_role_name = bot_role_name
        self._environment = environment
        self._ticket = ticket
        self._bot_alias_name = bot_alias_name

        self._create_bot_response = {}

        logger.setLevel(logging_level)
        logging.getLogger('botocore').setLevel(logging_level)

        self._lex_client = LexClient(profile_name=profile_name).client
        self._iam_client = IAMClient(profile_name=profile_name).client
        get_lex_bot = LexBotGetter(bot_name=bot_name,ticket=ticket,environment=environment,profile_name=profile_name)
        self._current_bot_name = get_lex_bot.current_bot_name
        #os.chdir('../')

    @property
    def bot_name(self):
        return self._bot_name
    
    @property
    def environment(self):
        return self._environment

    @property
    def ticket(self):
        return self._ticket

    @property
    def bot_role_name(self):
        return self._bot_role_name

    @property
    def bot_alias_name(self):
        return self._bot_alias_name

    def _get_role_arn(self):
        bot_role = self._iam_client.get_role(RoleName=self._bot_role_name)
        return bot_role['Role']['Arn']

    def _create_bot(self):
        try:
            logger.info('Create Lex bot : ' + self._current_bot_name)
            bot_role_arn = self._get_role_arn()
            logger.info("Retrieved Bot role ARN from Role name.")
            self._create_bot_response = self._lex_client.create_bot(
                botName=self._current_bot_name,
                description=self._current_bot_name,
                roleArn=bot_role_arn,
                dataPrivacy={
                    'childDirected': False
                },
                idleSessionTTLInSeconds=300,
                botType='Bot'
            )
            logger.info('Created Lex bot : ' + self._current_bot_name)
            bot_create_waiter = self._lex_client.get_waiter('bot_available')
            bot_create_waiter.wait(
                botId=self._create_bot_response['botId'],
                WaiterConfig={
                    'Delay': 20,
                    'MaxAttempts': 15
                }
            )
            create_bot_alias_response = self._lex_client.create_bot_alias(
                botAliasName=self._environment+"-"+self._bot_alias_name,
                description=self._current_bot_name,
                botId=self._create_bot_response['botId']
            )
            logger.info('Created Lex bot alias: ' + self._environment+"-"+self._bot_alias_name)


        except Exception as e:
            logger.warning(e)
            logger.warning('Lex create_bot call failed')
            raise

        return self._create_bot_response

    def create_bot(self):
        """ Performs a Lex get_bot API call

        :returns: the response of Lex get_bot with immutable/unneeded fields
            filtered out so that it can be fed to create/update calls
            returned object contains the exported resources in this structure:
            {bot:  {}, intents: [], slot-types: []}
        :rtype: dict
        """

        logger.info('Creating bot {}'.format(self._current_bot_name))
        self._get_bot = self._create_bot()

        return dict(
            bot=self._get_bot
        )

class LexBotDeleter(LexBotExporter):
    """Class to delete a Lex bot and associated resources
    """

    def __init__(
            self,
            bot_name,
            environment,
            ticket,
            profile_name='',
            logging_level=DEFAULT_LOGGING_LEVEL
        ):
        self._bot_name = bot_name
        self._environment = environment
        self._ticket = ticket

        self._delete_bot_response = {}

        logger.setLevel(logging_level)
        logging.getLogger('botocore').setLevel(logging_level)

        self._lex_client = LexClient(profile_name=profile_name).client
        get_lex_bot = LexBotGetter(bot_name=bot_name,ticket=ticket,environment=environment,profile_name=profile_name)
        self._bot_id, self._bot_latest_version = get_lex_bot.bot_id_version
        self._current_bot_name = get_lex_bot.current_bot_name

    @property
    def bot_name(self):
        return self._bot_name
    
    @property
    def environment(self):
        return self._environment

    @property
    def ticket(self):
        return self._ticket

    def _delete_bot(self):
        ''' delete bot
        '''
        try:
            self._delete_bot_response = self._lex_client.delete_bot(
                botId=self._bot_id,
                skipResourceInUseCheck=True
            )

            logger.info('Deleted Lex bot : ' + self._current_bot_name)

        except Exception as e:
            logger.warning(e)
            logger.warning('Lex delete_bot call failed')
            raise

        return self._delete_bot_response

    def delete_bot(self):
        logger.info('Deleting bot {}'.format(self._current_bot_name))
        self._delete_bot = self._delete_bot()
        logger.info('successfully deleted bot and associated resources')
        return dict(
            bot=self._delete_bot
        )
        