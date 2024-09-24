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

class LexMgmtDevopsRoleStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        repo_name = "lex-bot-mgmt"
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
        pipeline_role = iam.Role(
            self,
            id='lex_pipeline_role',
            role_name='lex_pipeline_role',
            assumed_by=
                iam.CompositePrincipal(
                    iam.ServicePrincipal('codebuild.amazonaws.com'),
                    iam.ServicePrincipal('codepipeline.amazonaws.com')
                )
        )

        codecommit_statement = iam.PolicyStatement(
            actions=[
				"codecommit:GetBranch",
                "codecommit:GetCommit",
                "codecommit:UploadArchive",
                "codecommit:GetUploadArchiveStatus",
                "codecommit:CancelUploadArchive",
                "codecommit:GitPull",
                "codecommit:GitPush"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:codecommit:{self.region}:{self.account}:{repo_name}"
            ]
        )

        pipeline_role.add_to_policy(
            statement=codecommit_statement
        )

        codebuild_statement = iam.PolicyStatement(
            actions=[
                "codebuild:BatchGetBuilds",
                "codebuild:StartBuild",
                "codebuild:StopBuild",
                #"codebuild:BatchPutCodeCoverages",
                #"codebuild:BatchPutTestCases",
                #"codebuild:CreateReport",
                #"codebuild:CreateReportGroup",
                #"codebuild:UpdateReport"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:codebuild:{self.region}:{self.account}:project/PushToRepo*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/SamDeployBot*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/CreateTag*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/ExportBot*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/CreateTicketBot*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/CreateTicketBranch*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/ImportBot*",
                f"arn:aws:codebuild:{self.region}:{self.account}:project/DeleteBot*"
                #f"arn:aws:codebuild:{self.region}:{self.account}:report-group/*"
            ]
        )

        NagSuppressions.add_resource_suppressions_by_path(
            self,
            '/LexMgmtDevopsRoleStack/lex_pipeline_role/DefaultPolicy/Resource',
            [NagPackSuppression(id="AwsSolutions-IAM5", reason="This is a reference implementation and the wildcard is required to allow access to resources with dynamically generated names. Where wildcards are used, these are prefixed with resources partial or complete ARNs within the same account and region. Make sure to include the complete resource ARNs in the actual implementation")],
            True
        )

        pipeline_role.add_to_policy(
            statement=codebuild_statement
        )

        cfn_statement = iam.PolicyStatement(
            actions=[
                "cloudformation:CreateStack",
                "cloudformation:DeleteStack",
                "cloudformation:DescribeStacks",
                "cloudformation:UpdateStack",
                "cloudformation:DescribeChangeSet",
                "cloudformation:ExecuteChangeSet",
                "cloudformation:CreateChangeSet"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/LexMgmtDevopsRoleStack/*",
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/LexMgmtDevopsRoleStack"
            ]
        )
        pipeline_role.add_to_policy(
            statement=cfn_statement
        )

        cwl_statement = iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:logs:{self.region}:{self.account}:log-group:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group:*:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group::log-stream:*",
                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lex/*:*"
            ]
        )
        pipeline_role.add_to_policy(
            statement=cwl_statement
        )


        iam_statement = iam.PolicyStatement(
            actions=[
                "iam:PassRole",
                "sts:AssumeRole"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                dev_lex_mgmt_role.role_arn,
                dev_lex_deploy_role.role_arn,
                prod_lex_mgmt_role.role_arn,
                prod_lex_deploy_role.role_arn
            ]
        )
        pipeline_role.add_to_policy(
            statement=iam_statement
        )

        s3_statement = iam.PolicyStatement(
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            effect=iam.Effect.ALLOW,
            resources=[
                f'arn:aws:s3:::*pipelineartifactstorebucket*',
                f'arn:aws:s3:::*pipelineartifactstorebucket*/*'
            ]
        )

        pipeline_role.add_to_policy(
            statement=s3_statement
        )