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

class LexMgmtCrossaccountRoleStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        repo_name = "lex-bot-mgmt"

        devops_account_id = self.node.try_get_context("devops-account-id")
        devops_lex_mgmt_role = iam.Role.from_role_arn(self, "Role", f"arn:aws:iam::{devops_account_id}:role/lex_pipeline_role",
            mutable=False
        )

        lex_deploy_role = iam.Role(
            self,
            id='lex_deploy_role',
            role_name='lex_deploy_role',
            assumed_by=
                iam.CompositePrincipal(
                    iam.ServicePrincipal('codebuild.amazonaws.com'),
                    iam.ServicePrincipal('cloudformation.amazonaws.com'),
                )
        )

        lex_mgmt_role = iam.Role(
            self,
            id='lex_mgmt_role',
            role_name='lex_mgmt_role',
            assumed_by=iam.CompositePrincipal(
                    devops_lex_mgmt_role,
                    lex_deploy_role,
                )
        )

        """#add statement and conditions to the trust policy
        lex_mgmt_role.assume_role_policy.add_statements(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.AccountPrincipal(devops_account_id)],
                actions=["sts:AssumeRole"],
                conditions={
                    "ArnEquals": {
                        "aws:PrincipalArn": devops_lex_mgmt_role.role_arn
                    }
                }
            )
        ) """

        #lex_mgmt_role.grant_assume_role(devops_lex_mgmt_role.role_arn)

        cwl_statement = iam.PolicyStatement(
            actions=[
                "logs:DescribeLogGroups",
                "logs:CreateLogGroup",
                "logs:DeleteLogGroup",
                "logs:CreateLogStream",
                "logs:DeleteLogStream",
                "logs:GetLogEvents",
                "logs:GetLogRecord",
                "logs:GetLogGroupFields",
                "logs:PutDestination",
                "logs:DescribeDestinations",
                "logs:DeleteDestination",
                "logs:ListTagsLogGroup",
                "logs:TagLogGroup",
                "logs:UntagLogGroup",
                "logs:PutLogEvents",
                "logs:PutRetentionPolicy",
                "logs:DescribeLogGroups"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:logs:{self.region}:{self.account}:log-group:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group:*:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group::log-stream:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lex/*:*"
            ]
        )

        lex_mgmt_role.add_to_policy(
            statement=cwl_statement
        )
        lex_deploy_role.add_to_policy(
            statement=cwl_statement
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
        
        lex_mgmt_role.add_to_policy(
            statement=ssm_statement
        )
        lex_deploy_role.add_to_policy(
            statement=ssm_statement
        )

        deploy_iam_statement = iam.PolicyStatement(
            actions=[
                "iam:GetRole",
                "iam:PutRolePolicy",
                "iam:GetRolePolicy",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
                "iam:CreateRole",
                "iam:DeleteRolePolicy",
                "iam:DeleteRole"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:iam::{self.account}:role/*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_iam_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_iam_statement
        )

        deploy_role_statement = iam.PolicyStatement(
            actions=[
                "iam:PassRole"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:iam::{self.account}:role/*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_role_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_role_statement
        )

        deploy_kms_statement = iam.PolicyStatement(
            actions=[
                "kms:ListAliases",
                "kms:DescribeKey",
                "kms:CreateAlias",
                "kms:ListResourceTags",
                "kms:GetKeyPolicy",
                "kms:GetKeyRotationStatus",
                "kms:EnableKeyRotation",
                "kms:CreateKey",
                "kms:ScheduleKeyDeletion",
                "kms:DeleteAlias",
                "kms:Decrypt",
                "kms:Encrypt"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:kms:{self.region}:{self.account}:key/*",
                f"arn:aws:kms:{self.region}:{self.account}:alias/*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_kms_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_kms_statement
        )

        deploy_kmscreate_statement = iam.PolicyStatement(
            actions=[
                "kms:CreateKey"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                "*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_kmscreate_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_kmscreate_statement
        )

        deploy_assume_statement = iam.PolicyStatement(
            actions=[
                "sts:AssumeRole"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                lex_mgmt_role.role_arn
            ]
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_assume_statement
        )

        deploy_cfn_statement = iam.PolicyStatement(
            actions=[
                "cloudformation:DescribeChangeSet",
                "cloudformation:CreateChangeSet",
                "cloudformation:GetTemplateSummary",
                "cloudformation:DescribeStacks",
                "cloudformation:DescribeStackEvents",
                "cloudformation:ExecuteChangeSet"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/*/*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:changeSet/*/*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:changeSet/*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:stackset/*:*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:stackset/*",
                f"arn:aws:cloudformation:{self.region}:aws:transform/Serverless-*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_cfn_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_cfn_statement
        )

        deploy_s3_statement = iam.PolicyStatement(
            actions=[
                "s3:CreateBucket",
				"s3:DeleteBucket",
				"s3:GetAccelerateConfiguration",
				"s3:GetBucketCors",
				"s3:GetBucketLogging",
				"s3:GetBucketNotification",
				"s3:GetBucketObjectLockConfiguration",
				"s3:GetBucketOwnershipControls",
				"s3:GetBucketPolicy",
				"s3:GetBucketPublicAccessBlock",
				"s3:GetBucketTagging",
				"s3:GetBucketVersioning",
				"s3:GetBucketWebsite",
				"s3:PutBucketPolicy",
				"s3:PutBucketPublicAccessBlock",
				"s3:PutBucketTagging",
				"s3:PutBucketVersioning",
				"s3:PutObject",
				"s3:GetObject",
				"s3:PutEncryptionConfiguration",
				"s3:GetEncryptionConfiguration"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                "arn:aws:s3:::aws-sam-cli-managed-default-samclisourcebucket*",
                "arn:aws:s3:::aws-sam-cli-managed-default-samclisourcebucket*/*",
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_s3_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_s3_statement
        )

        deploy_lex_statement = iam.PolicyStatement(
            actions=[
                "lex:DescribeBotVersion",
                "lex:UpdateBotAlias",
                "lex:DescribeBotAlias",
                "lex:CreateBotVersion",
                "lex:DescribeBotLocale",
                "lex:ListBots",
                "lex:ListBotAliases",
                "lex:DeleteImport",
                "lex:DescribeImport",
                "lex:BuildBotLocale",
                "lex:DescribeBot",
                "lex:StartImport",
                "lex:CreateUploadUrl",
                "lex:DeleteBot",
                "lex:DeleteExport",
                "lex:DescribeExport",
                "lex:CreateExport",
                "lex:CreateBotAlias",
                "lex:CreateBot",
                "lex:CreateResourcePolicy",
                "lex:DescribeResourcePolicy",
                "lex:ListTagsForResource",
                "lex:ListBotLocales",
                "lex:CreateBotLocale",
                "lex:DeleteBotAlias",
                "lex:UpdateBot",
                "lex:DeleteBotLocale",
				"lex:CreateIntent",
				"lex:DescribeIntent",
				"lex:DeleteIntent",
				"lex:UpdateIntent",
				"lex:CreateSlot",
				"lex:DescribeSlot",
				"lex:DescribeSlotType",
				"lex:CreateSlotType",
				"lex:DeleteSlot",
				"lex:DeleteSlotType",
				"lex:UpdateSlot",
				"lex:UpdateSlotType",
				"lex:BuildBotLocale",
				"lex:UpdateExport",
				"lex:DescribeExport",
				"lex:CreateExport",
				"lex:DeleteExport",
				"lex:DescribeImport",
				"lex:DeleteImport",
				"lex:StartImport",
                "lex:DeleteBot",
                "lex:CreateCustomVocabulary",
                "lex:UpdateBotLocale",
                "lex:UpdateCustomVocabulary",
                "lex:DeleteCustomVocabulary",
                "lex:DescribeCustomVocabulary",
                "lex:DeleteBotVersion",
                "lex:DeleteBotChannel"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:lex:{self.region}:{self.account}:*",
                f"arn:aws:lex:{self.region}:{self.account}:slottype:*:*",
                f"arn:aws:lex:{self.region}:{self.account}:intent:*:*",
                f"arn:aws:lex:{self.region}:{self.account}:bot/*",
                f"arn:aws:lex:{self.region}:{self.account}:bot-alias/*",
                f"arn:aws:lex:{self.region}:{self.account}:bot-channel:*:*:*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_lex_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_lex_statement
        )

        deploy_lexlist_statement = iam.PolicyStatement(
            actions=[
                "lex:ListBots",
                "lex:ListBotAliases",
                "lex:ListTagsForResource",
                "lex:ListBotLocales",
                "lex:ListIntents",
                "lex:ListSlotTypes",
                "lex:ListSlots"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                "*"
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_lexlist_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_lexlist_statement
        )

        deploy_lambda_statement = iam.PolicyStatement(
            actions=[
                "lambda:AddPermission",
                "lambda:GetFunction",
                "lambda:GetFunctionCodeSigningConfig",
                "lambda:GetRuntimeManagementConfig",
                "lambda:CreateFunction",
                "lambda:RemovePermission",
                "lambda:ListTags",
                "lambda:UpdateFunctionConfiguration",
                "lambda:DeleteFunction",
                "lambda:TagResource",
                "lambda:UntagResource",
                "events:ListTargetsByRule",
                "events:DescribeRule",
                "events:PutTargets",
                "events:PutRule",
                "events:RemoveTargets"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:lambda:{self.region}:{self.account}:function:*:*",
                f"arn:aws:events:{self.region}:{self.account}:rule/*",
                f"arn:aws:events:{self.region}:{self.account}:target/*",
                f"arn:aws:lambda:{self.region}:{self.account}:layer:*:*",
                f"arn:aws:lambda:{self.region}:{self.account}:function:*",
                f"arn:aws:lambda:{self.region}:{self.account}:layer:*"            
            ]
        )
        lex_mgmt_role.add_to_policy(
            statement=deploy_lambda_statement
        )
        lex_deploy_role.add_to_policy(
            statement=deploy_lambda_statement
        )

        NagSuppressions.add_resource_suppressions_by_path(
            self,
            '/LexMgmtCrossaccountRoleStack/lex_mgmt_role/DefaultPolicy/Resource',
            [NagPackSuppression(id="AwsSolutions-IAM5", reason="This is a reference implementation and the wildcard is required to allow access to resources with dynamically generated names. Where wildcards are used, these are prefixed with resources partial or complete ARNs within the same account and region. Make sure to include the complete resource ARNs in the actual implementation")],
            True
        )
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            '/LexMgmtCrossaccountRoleStack/lex_deploy_role/DefaultPolicy/Resource',
            [NagPackSuppression(id="AwsSolutions-IAM5", reason="This is a reference implementation and the wildcard is required to allow access to resources with dynamically generated names. Where wildcards are used, these are prefixed with resources partial or complete ARNs within the same account and region. Make sure to include the complete resource ARNs in the actual implementation")],
            True
        )