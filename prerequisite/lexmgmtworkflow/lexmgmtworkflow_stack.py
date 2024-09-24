from aws_cdk import (
    Stack,
    # aws_sqs as sqs,
    pipelines as pipelines,
    aws_iam as iam,
    aws_kms as kms,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codecommit as codecommit,
    aws_codebuild as codebuild,
    aws_s3 as s3,
    CfnParameter,
    RemovalPolicy
)
from cdk_nag import (
    NagPackSuppression,
    NagSuppressions
)
from constructs import Construct
import json

class LexMgmtWorkflowStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        repo_name = "lex-bot-mgmt"

        repo = codecommit.Repository(self, "LexBotManagementRepo", repository_name=repo_name,
            code=codecommit.Code.from_directory('../src', 'main'),
            description="Lex Bot Management Repository"
        )

        devops_account_id = self.node.try_get_context("devops-account-id")
        devops_pipeline_role = iam.Role.from_role_arn(self, "DevopsPipelineRole", f"arn:aws:iam::{devops_account_id}:role/lex_pipeline_role",
            mutable=False
        )

        dev_account_id = self.node.try_get_context("dev-account-id")
        dev_lex_mgmt_role = iam.Role.from_role_arn(self, "DevMgmtRole", f"arn:aws:iam::{dev_account_id}:role/lex_mgmt_role",
            mutable=False
        )
        dev_lex_deploy_role = iam.Role.from_role_arn(self, "DevDeployRole", f"arn:aws:iam::{dev_account_id}:role/lex_deploy_role",
            mutable=False
        )

        prod_account_id = self.node.try_get_context("prod-account-id")
        prod_lex_mgmt_role = iam.Role.from_role_arn(self, "ProdMgmtRole", f"arn:aws:iam::{prod_account_id}:role/lex_mgmt_role",
            mutable=False
        )
        prod_lex_deploy_role = iam.Role.from_role_arn(self, "ProdDeployRole", f"arn:aws:iam::{prod_account_id}:role/lex_deploy_role",
            mutable=False
        )

        ssm_statement = iam.PolicyStatement(
            actions=[
                "ssm:GetParameters"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/*"
            ]
        )

        pipeline_artifact_store_encryption_key = kms.Key(
            self,
            id='pipeline_artifact_store_encryption_key',
            removal_policy=RemovalPolicy.DESTROY,
            enable_key_rotation=True
        )

        pipeline_artifact_store_encryption_key.add_to_resource_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:Encrypt",
                    "kms:ReEncryptFrom",
                    "kms:ReEncryptTo",
                    "kms:GenerateDataKey",
                    "kms:GenerateDataKeyPair",
                    "kms:GenerateDataKeyPairWithoutPlaintext",
                    "kms:GenerateDataKeyWithoutPlaintext"
                ],
                effect=iam.Effect.ALLOW,
                resources=["*"],
                principals=[
                    iam.ArnPrincipal(
                        arn=devops_pipeline_role.role_arn
                    ),
                    iam.ArnPrincipal(
                        arn=dev_lex_mgmt_role.role_arn
                    ),
                    iam.ArnPrincipal(
                        arn=prod_lex_mgmt_role.role_arn
                    )
                ]
            )
        )

        pipeline_artifact_store_bucket = s3.Bucket(
            self,
            id='pipeline_artifact_store_bucket',
            encryption=s3.BucketEncryption.KMS,
            encryption_key=pipeline_artifact_store_encryption_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=False,
            removal_policy=RemovalPolicy.DESTROY,
            server_access_logs_prefix='access_log',
            enforce_ssl=True
        )

        s3bucketPolicy = s3.BucketPolicy(self, "artifact_bucket_policy",
            bucket=pipeline_artifact_store_bucket
        )

        s3bucketPolicy.document.add_statements(
            iam.PolicyStatement(
                sid="AllowProdDeployRole",
                actions=["s3:Get*","s3:Put*","s3:ListBucket"],
                principals=[iam.ArnPrincipal(
                        arn=devops_pipeline_role.role_arn
                    ),
                    iam.ArnPrincipal(
                        arn=dev_lex_mgmt_role.role_arn
                    ),
                    iam.ArnPrincipal(
                        arn=prod_lex_mgmt_role.role_arn
                    )],
                effect=iam.Effect.ALLOW,
                resources=[
                    pipeline_artifact_store_bucket.bucket_arn,
                    f"{pipeline_artifact_store_bucket.bucket_arn}/*"
                ]
            )
        )

        NagSuppressions.add_resource_suppressions_by_path(
            self,
            '/LexMgmtWorkflowStack/artifact_bucket_policy/Resource',
            [NagPackSuppression(id="AwsSolutions-S10", reason="enforce_ssl is enabled in s3_bucket construct")],
            True
        )

        pipeline_artifact_store_encryption_key_props = codepipeline.CfnPipeline.EncryptionKeyProperty(
            id=pipeline_artifact_store_encryption_key.key_id,
            type='KMS'
        )

        pipeline_artifact_store = codepipeline.CfnPipeline.ArtifactStoreProperty(
            location=pipeline_artifact_store_bucket.bucket_name,
            type='S3',
            encryption_key=pipeline_artifact_store_encryption_key_props
        )

        cdk_source_output = codepipeline.Artifact()


        # synthesize the CDK template, using CodeBuild
        # adjust the build environment and/or commands accordingly
        cdk_samdeploy_project = codebuild.Project(self, "SamDeployBot",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "install": {
                        "runtime-versions": {"python": "3.10"}
                    },
                    "build": {
                        "commands": [
                            "TEMP_ROLE=$(aws sts assume-role --role-arn ${botmgmtrole} --role-session-name lex-mgmt)",
                            "export AWS_ACCESS_KEY_ID=$(echo ${TEMP_ROLE} | jq -r '.Credentials.AccessKeyId')",
                            "export AWS_SECRET_ACCESS_KEY=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SecretAccessKey')",
                            "export AWS_SESSION_TOKEN=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SessionToken')",
                            "sam build",
                            "sam deploy --no-confirm-changeset --no-fail-on-empty-changeset --resolve-s3 --stack-name $botname --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BotName=$botname Environment=$account"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_exportbot_project = codebuild.Project(self, "ExportBot",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "install": {
                        "commands": [f"pip install -r requirements.txt"]
                    },
                    "build": {
                        "commands": [
                            "TEMP_ROLE=$(aws sts assume-role --role-arn ${botmgmtrole} --role-session-name lex-mgmt)",
                            "export AWS_ACCESS_KEY_ID=$(echo ${TEMP_ROLE} | jq -r '.Credentials.AccessKeyId')",
                            "export AWS_SECRET_ACCESS_KEY=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SecretAccessKey')",
                            "export AWS_SESSION_TOKEN=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SessionToken')",
                            "python lex_manager.py -e $botname -v $botversion -n $account -t \"${ticket}\""
                        ]
                    }
                },
                "artifacts": {
                    "base-directory": "$CODEBUILD_SRC_DIR",
                    "files": ["lex_bots/**/*"
                    ]
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_importbot_project = codebuild.Project(self, "ImportBot",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "install": {
                        "commands": [f"pip install -r requirements.txt"]
                    },
                    "build": {
                        "commands": [
                            "git config --global --unset-all credential.helper",
                            "git config --global credential.helper '!aws codecommit credential-helper $@'",
                            "git config --global credential.UseHttpPath true",
                            "git config --global user.name 'AWS CodeCommit'",
                            "git config --global user.email 'noreply-awscodecommit@amazon.com'",
                            f"git clone --single-branch --branch $ticket https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name} {repo_name}",
                            f"cd {repo_name}",
                            f"git remote set-url --push origin https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name}",
                            "TEMP_ROLE=$(aws sts assume-role --role-arn ${botmgmtrole} --role-session-name lex-mgmt)",
                            "export AWS_ACCESS_KEY_ID=$(echo ${TEMP_ROLE} | jq -r '.Credentials.AccessKeyId')",
                            "export AWS_SECRET_ACCESS_KEY=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SecretAccessKey')",
                            "export AWS_SESSION_TOKEN=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SessionToken')",
                            #if value of variable ticket is equal to main or matches pattern like semantic version example v0.0.0 then set variable ticket to empty string
                            "if [ \"$ticket\" = \"main\" ] || [[ \"$ticket\" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then ticket=\"\"; fi",
                            "python lex_manager.py -i $botname -n $account -t \"${ticket}\" -s $botversion -a $botname-alias"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )
        
        cdk_pushtorepo_project = codebuild.Project(self, "PushToRepo",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "build": {
                        "commands": [
                            "git config --global --unset-all credential.helper",
                            "git config --global credential.helper '!aws codecommit credential-helper $@'",
                            "git config --global credential.UseHttpPath true",
                            "git config --global user.name 'AWS CodeCommit'",
                            "git config --global user.email 'noreply-awscodecommit@amazon.com'",
                            f"git clone --single-branch --branch $ticket https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name} {repo_name}",
                            f"cd {repo_name}",
                            f"git remote set-url --push origin https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name}",
                            "git fetch -p origin",
                            f"git checkout $ticket",
                            f"cp -r ../lex_bots .",
                            "git add lex_bots",
                            "git commit -m 'bot export'",
                            "git push --set-upstream origin $ticket"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_createticketbranch_project = codebuild.Project(self, "CreateTicketBranch",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "build": {
                        "commands": [
                            "git config --global --unset-all credential.helper",
                            "git config --global credential.helper '!aws codecommit credential-helper $@'",
                            "git config --global credential.UseHttpPath true",
                            "git config --global user.name 'AWS CodeCommit'",
                            "git config --global user.email 'noreply-awscodecommit@amazon.com'",
                            f"git clone --single-branch --branch main https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name} {repo_name}",
                            f"cd {repo_name}",
                            f"git remote set-url --push origin https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name}",
                            "git fetch -p origin",
                            f"git checkout -b $ticket",
                            "git push --set-upstream origin $ticket"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_createtag_project = codebuild.Project(self, "CreateTag",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "build": {
                        "commands": [
                            "git config --global --unset-all credential.helper",
                            "git config --global credential.helper '!aws codecommit credential-helper $@'",
                            "git config --global credential.UseHttpPath true",
                            "git config --global user.name 'AWS CodeCommit'",
                            "git config --global user.email 'noreply-awscodecommit@amazon.com'",
                            f"git clone --single-branch --branch main https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name} {repo_name}",
                            f"cd {repo_name}",
                            f"git remote set-url --push origin https://git-codecommit.{self.region}.amazonaws.com/v1/repos/{repo_name}",
                            "git fetch -p origin",
                            f"git tag $tag",
                            "git push origin $tag"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_createticketbot_project = codebuild.Project(self, "CreateTicketBot",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "install": {
                        "commands": [f"pip install -r requirements.txt"]
                    },
                    "build": {
                        "commands": [
                            "TEMP_ROLE=$(aws sts assume-role --role-arn ${botmgmtrole} --role-session-name lex-mgmt)",
                            "export AWS_ACCESS_KEY_ID=$(echo ${TEMP_ROLE} | jq -r '.Credentials.AccessKeyId')",
                            "export AWS_SECRET_ACCESS_KEY=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SecretAccessKey')",
                            "export AWS_SESSION_TOKEN=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SessionToken')",
                            "MAIN_BOT_ID=$(aws lexv2-models list-bots --filters name=BotName,values=${account}-${botname},operator=EQ --query 'botSummaries[0].botId' --output text)",
                            "MAIN_BOT_ROLEARN=$(aws lexv2-models describe-bot --bot-id ${MAIN_BOT_ID} --query 'roleArn' --output text)",
                            "MAIN_BOT_ROLENAME=$(echo ${MAIN_BOT_ROLEARN} | sed 's/.*\///g')",
                            "python lex_manager.py -c $botname -n $account -t $ticket -r $MAIN_BOT_ROLENAME -a $botname-alias",
                            "python lex_manager.py -i $botname -n $account -t $ticket -r $MAIN_BOT_ROLENAME -s DRAFT -a $botname-alias"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        cdk_deletebot_project = codebuild.Project(self, "DeleteBot",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "env": {
                    "git-credential-helper":  "yes"
                },
                "phases": {
                    "install": {
                        "commands": [f"pip install -r requirements.txt"]
                    },
                    "build": {
                        "commands": [
                            "TEMP_ROLE=$(aws sts assume-role --role-arn ${botmgmtrole} --role-session-name lex-mgmt)",
                            "export AWS_ACCESS_KEY_ID=$(echo ${TEMP_ROLE} | jq -r '.Credentials.AccessKeyId')",
                            "export AWS_SECRET_ACCESS_KEY=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SecretAccessKey')",
                            "export AWS_SESSION_TOKEN=$(echo ${TEMP_ROLE} | jq -r '.Credentials.SessionToken')",
                            "python lex_manager.py -d $botname -n $account -t $ticket"
                        ]
                    }
                }
            }),
            role=devops_pipeline_role,
            encryption_key=pipeline_artifact_store_encryption_key
        )

        environment_pipeline_var = codepipeline.CfnPipeline.VariableDeclarationProperty(
            name="environment",
            description="Environment"
        )

        botname_pipeline_var = codepipeline.CfnPipeline.VariableDeclarationProperty(
            name="botname",
            description="Bot name"
        )

        botversion_pipeline_var = codepipeline.CfnPipeline.VariableDeclarationProperty(
            name="botversion",
            default_value="DRAFT",
            description="Bot version"
        )

        ticket_pipeline_var = codepipeline.CfnPipeline.VariableDeclarationProperty(
            name="ticket",
            description="Ticket reference"
        )

        tag_pipeline_var = codepipeline.CfnPipeline.VariableDeclarationProperty(
            name="tag",
            default_value="v0.0.1",
            description="Tag reference"
        )

        pipeline_vars = [environment_pipeline_var,botname_pipeline_var,botversion_pipeline_var,ticket_pipeline_var]

        cfn_pipeline = codepipeline.CfnPipeline(self, "BaselineBotPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,botversion_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="SamDeployBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_samdeploy_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                        output_artifacts=[],
                    )],
                    name="SamDeployBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="ExportBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_exportbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "botversion", "value" : "#{{variables.botversion}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="export"
                        )],
                    )],
                    name="ExportBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="PushToRepo",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_pushtorepo_project.project_name, "EnvironmentVariables":f'[{{"name" : "ticket", "value" : "main","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="export"
                        )]
                    )],
                    name="PushToRepo",
                ),
            ],
            name="BaselineBotPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "CreateTicketBotPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,ticket_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="CreateTicketBranch",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_createticketbranch_project.project_name, "EnvironmentVariables":f'[{{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="CreateTicketBranch",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="CreateTicketBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_createticketbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="CreateTicketBot",
                ),
            ],
            name="CreateTicketBotPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "ExportTicketBotPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,botversion_pipeline_var,ticket_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="ExportTicketBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_exportbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "botversion", "value" : "#{{variables.botversion}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="export"
                        )],
                    )],
                    name="ExportTicketBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="PushToRepo",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_pushtorepo_project.project_name, "EnvironmentVariables":f'[{{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="export"
                        )]
                    )],
                    name="PushToRepo",
                ),
            ],
            name="ExportTicketBotPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "ImportTicketBotPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,ticket_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="ImportTicketBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_importbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "botversion", "value" : "DRAFT","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="ImportTicketBot",
                ),
            ],
            name="ImportTicketBotPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "DeleteTicketBotPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,ticket_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="DeleteTicketBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_deletebot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "#{{variables.ticket}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="DeleteTicketBot",
                ),
            ],
            name="DeleteTicketBotPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "DeployBotDevPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,tag_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="SamDeployBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_samdeploy_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                        output_artifacts=[],
                    )],
                    name="SamDeployBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="ImportMainBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_importbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "botversion", "value" : "DRAFT","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "main","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="ImportMainBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="CreateTag",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_createtag_project.project_name, "EnvironmentVariables":f'[{{"name" : "tag", "value" : "#{{variables.tag}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{dev_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="CreateTag",
                )
            ],
            name="DeployBotDevPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )

        cfn_pipeline = codepipeline.CfnPipeline(self, "DeployBotProdPipeline",
            role_arn=devops_pipeline_role.role_arn,
            artifact_store=pipeline_artifact_store,
            variables=[environment_pipeline_var,botname_pipeline_var,tag_pipeline_var],
            stages=[codepipeline.CfnPipeline.StageDeclarationProperty(
                actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Source",
                            owner="AWS",
                            provider="CodeCommit",
                            version="1"
                        ),
                        name="PipelineSourceProject",

                        # the properties below are optional
                        configuration={
                            "RepositoryName": repo_name,
                            "BranchName": "main",
                            "PollForSourceChanges": "false"
                        },
                        output_artifacts=[codepipeline.CfnPipeline.OutputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="Source",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="SamDeployBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_samdeploy_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{prod_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                        output_artifacts=[],
                    )],
                    name="SamDeployBot",
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    actions=[codepipeline.CfnPipeline.ActionDeclarationProperty(
                        action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                            category="Build",
                            owner="AWS",
                            provider="CodeBuild",
                            version="1"
                        ),
                        name="ImportMainBot",

                        # the properties below are optional
                        configuration={"ProjectName": cdk_importbot_project.project_name, "EnvironmentVariables":f'[{{"name" : "botname", "value" : "#{{variables.botname}}","type" : "PLAINTEXT"}}, {{"name" : "botversion", "value" : "DRAFT","type" : "PLAINTEXT"}}, {{"name" : "account", "value" : "#{{variables.environment}}","type" : "PLAINTEXT"}}, {{"name" : "ticket", "value" : "#{{variables.tag}}","type" : "PLAINTEXT"}}, {{"name" : "botmgmtrole", "value" : "{prod_lex_mgmt_role.role_arn}","type" : "PLAINTEXT"}}]'},
                        input_artifacts=[codepipeline.CfnPipeline.InputArtifactProperty(
                            name="source"
                        )],
                    )],
                    name="ImportMainBot",
                ),
            ],
            name="DeployBotProdPipeline",
            pipeline_type="V2",
            restart_execution_on_update=False,
        )