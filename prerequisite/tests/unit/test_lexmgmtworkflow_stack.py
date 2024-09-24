import aws_cdk as core
import aws_cdk.assertions as assertions

from lexmgmtworkflow.lexmgmtworkflow_stack import LexMgmtWorkflowStack

# example tests. To run these tests, uncomment this file along with the example
# resource in lexmgmtworkflow.lexmgmtworkflow_stack.py
def test_codecommit_repo_created():
    app = core.App()
    stack = LexMgmtWorkflowStack(app, "lexmgmtworkflow")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::CodeCommit::Repository", {
#         "RepositoryName": "lex-bot-mgmt"
#     })
