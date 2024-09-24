#!/usr/bin/env python3
import os

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from lexmgmtworkflow.lexmgmtworkflow_stack import LexMgmtWorkflowStack
from lexmgmtworkflow.lexmgmtcrossaccountrole_stack import LexMgmtCrossaccountRoleStack
from lexmgmtworkflow.lexmgmtdevopsrole_stack import LexMgmtDevopsRoleStack

app = cdk.App()
LexMgmtWorkflowStack(app, "LexMgmtWorkflowStack")
LexMgmtCrossaccountRoleStack(app, "LexMgmtCrossaccountRoleStack")
LexMgmtDevopsRoleStack(app, "LexMgmtDevopsRoleStack")
cdk.Aspects.of(app).add(AwsSolutionsChecks())
app.synth()
